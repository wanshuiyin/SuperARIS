"""Rex ownership, draft-safe delivery and events against the file-backed fake CLI."""
import _thread
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import pytest

from superaris import delivery, rex_exec
from superaris.platform import FileLock, LockBusy
from superaris.rex import Rex, RexError, discover_rex
from superaris.state import directory, write
from tests.rex_support import FAKE_REX, FakeRex, install
from tests.test_windows_runtime import executable


@pytest.fixture
def team(tmp_path, monkeypatch):
    project = tmp_path / "research project 中文"
    project.mkdir()
    fake = FakeRex(tmp_path, project)
    install(monkeypatch, fake)
    monkeypatch.setenv("REX_SERVER", "tcp://inherited-remote:7501")
    client = Rex(project, str(fake.binary), {"host": "rex", "session": "aris"})
    server = client.ensure_ready(new=True)
    current = {"host": "rex", "session": "aris", "roles": {}, "execution_environment": "local",
               "rex_server": server["endpoint"], "rex_instance": server["instance_id"], "rex_host": server["host_id"]}
    client.bind(current)
    codex = str(tmp_path / "agents" / "codex")
    launched = client.launch_agent(current, None, [codex, "--cd", str(project)], "Main · Codex",
                                   session_label="SuperARIS · demo", window_label="SuperARIS · Workbench")
    role = client.wait_owner({"pane_id": launched["pane_id"], "harness": "codex", "rex_session": launched["rex_session"],
                              "automation_owned": True, "created": True}, project)
    current["roles"]["main"] = role
    write(directory(project) / "launch.json", current)
    return project, fake, client, current, role


def block(fake, role):
    return fake.read()["blocks"][role["pane_id"]]


def test_launch_pins_local_server_and_never_follows_inherited_route(team):
    project, fake, client, current, role = team
    created = fake.calls("session.create")[0]
    options = created["initial_windows"][0]["layout"]["block"]["options"]
    assert options["cwd"] == str(project) and options["command"][1:] == ["--cd", str(project)]
    assert options["path_prepend"] == [str(Path(options["command"][0]).parent)]
    assert created["label"] == "SuperARIS · demo"
    assert current["rex_session"] == role["rex_session"] and current["rex_window"]
    assert role["pid"] == block(fake, role)["process"]["foreground"]["pid"]
    assert role["runtime_id"] == "instance-original" and role["execution_host"] == "host-local"
    assert role["status"] == "idle" and role["host"] == "rex"
    commands = fake.commands()
    assert all(entry["rex_server_env"] is None for entry in commands)
    pinned = [entry["argv"] for entry in commands if entry["argv"][:1] == ["--server"]]
    assert pinned and all(argv[:3] == ["--server", "unix:///fake/rex.sock", "--autostart=false"] for argv in pinned)
    assert commands[0]["argv"] == ["whoami", "--json"]  # Only the unstarted team may use the default local server.


@pytest.mark.parametrize("placement,method,direction", [
    ("tab", "session.new_window", None), (("anchor", "right"), "session.new_split", "horizontal"),
    (("anchor", "down"), "session.new_split", "vertical")])
def test_collaborator_placement_never_takes_focus(team, placement, method, direction):
    project, fake, client, current, role = team
    if placement != "tab":
        placement = (role["pane_id"], placement[1])
    client.launch_agent(current, placement, ["claude", "Read packet"], "Engineer · Claude Code",
                        session_label="unused", window_label="unused")
    request = fake.calls(method)[-1]
    assert request["focus"] is False and request["session_id"] == current["rex_session"]
    if direction:
        assert request["direction"] == direction and request["side"] == "after"
        assert request["anchor_id"] == role["pane_id"]
    assert "path_prepend" not in request["layout"]["block"]["options"]


def test_self_updated_process_keeps_identity_but_replaced_process_does_not(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state["blocks"][role["pane_id"]]["process"]["foreground"].update(
        name="codex.1795233718824789000.old", path="/opt/codex.1795233718824789000.old"))
    assert client.verify_owner(role, project)["pid"] == role["pid"]
    fake.update(lambda state: state["blocks"][role["pane_id"]]["process"]["foreground"].update(pid=4242))
    with pytest.raises(RexError, match="Foreground process changed"):
        client.verify_owner(role, project)


@pytest.mark.parametrize("change,message", [
    (lambda b, s: b["process"]["foreground"].update(cwd="/elsewhere"), "cwd mismatch"),
    (lambda b, s: b["process"]["foreground"].update(name="claude", argv0="claude", path="/bin/claude"), "occupant changed"),
    (lambda b, s: b.update(host_id="host-remote"), "original local host"),
    (lambda b, s: s["server"].update(instance_id="instance-restarted"), "instance changed"),
    (lambda b, s: b["process"].update(foreground=None), "recognizable foreground agent"),
])
def test_changed_owner_is_rejected_before_any_input(team, change, message):
    project, fake, client, current, role = team
    fake.update(lambda state: change(state["blocks"][role["pane_id"]], state))
    client._ready = (0.0, None)  # The next reconciliation rereads the server identity.
    with pytest.raises(RexError, match=message):
        client.verify_owner(role, project)
    assert not fake.calls("block.event") and not fake.argv("send-key")


def test_closed_block_is_absent_not_rebound(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state["blocks"].pop(role["pane_id"]))
    with pytest.raises(RexError, match="absent from its original session"):
        client.verify_owner(role, project)


@pytest.mark.parametrize("record,expected", [
    (None, "unknown"),
    ({"state": "done", "owner": {"pid": 1}}, "unknown"),  # Left by an earlier process.
    ({"state": "paused-for-review"}, "unknown"),
    ({"state": "blocked", "kind": "permission"}, "blocked"),
    ({"state": "done"}, "done"),
])
def test_status_counts_only_reports_from_the_owner_process(team, record, expected):
    project, fake, client, current, role = team

    def change(state):
        records = state["blocks"][role["pane_id"]]["records"]
        if record is None:
            records.clear()
        else:
            records[0].update(record)
    fake.update(change)
    assert client.verify_owner(role, project)["status"] == expected


def test_node_launched_agent_is_identified_by_its_own_status_report(team):
    project, fake, client, current, role = team

    def change(state):
        target = state["blocks"][role["pane_id"]]
        target["process"]["foreground"].update(name="node", argv0="node", path="/usr/bin/node")
        target["records"][0].update(app="claude-code", effective_app="claude-code")
    fake.update(change)
    described = client.describe(role["pane_id"])
    assert described["kind"] == "claude" and described["pid"] == role["pid"]


def test_prompt_is_pasted_once_then_confirmed_by_a_new_turn(team):
    project, fake, client, current, role = team
    text = "Read the packet.\nThen wait for `main`; $HOME stays literal."
    receipt = client.send_prompt(role["pane_id"], text, role, settle=0)
    assert receipt["accepted"] and receipt["state"] == "working" and receipt["pid"] == role["pid"]
    pastes = fake.calls("block.event")
    assert [paste["event"] for paste in pastes] == [{"type": "paste", "payload": {"text": text}}]
    assert block(fake, role)["submitted"] == [text]
    assert len(fake.argv("send-key")) == 1


def test_unconfirmed_turn_is_unknown_and_never_resent(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(turns=False))
    with pytest.raises(RexError, match="inspect its block before any resend") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0, timeout=0.5)
    assert error.value.code == "unconfirmed"
    assert len(fake.calls("block.event")) == 1 and len(fake.argv("send-key")) == 1


@pytest.mark.parametrize("when", ["before_paste", "after_paste"])
def test_input_stops_once_the_verified_process_loses_the_block(team, when):
    project, fake, client, current, role = team
    if when == "before_paste":
        fake.update(lambda state: state["blocks"][role["pane_id"]]["process"]["foreground"].update(pid=4242))
    else:
        fake.update(lambda state: state.update(replace_on_paste=4242))
    with pytest.raises(RexError, match="no longer holds") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0)
    assert error.value.code == ("owner_changed" if when == "before_paste" else "unconfirmed")
    assert len(fake.calls("block.event")) == (when == "after_paste") and not fake.argv("send-key")


def test_prompt_opening_after_the_paste_is_never_answered_by_enter(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(state_on_paste="blocked"))
    with pytest.raises(RexError, match="Enter was not sent") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0)
    assert error.value.code == "unconfirmed"
    assert len(fake.calls("block.event")) == 1 and not fake.argv("send-key")


def test_prompt_opening_during_the_process_check_is_never_answered_by_enter(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(prompt_during_process=True))
    with pytest.raises(RexError, match="Enter was not sent") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0)
    assert error.value.code == "unconfirmed" and not fake.argv("send-key")


def test_prompt_reported_right_after_enter_is_not_a_turn_receipt(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(after_enter="blocked"))
    with pytest.raises(RexError, match="reported blocked right after Enter") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0, timeout=2)
    assert error.value.code == "unconfirmed" and len(fake.argv("send-key")) == 1


def test_concurrent_senders_never_share_one_composer(team):
    project, fake, client, current, role = team
    receipts = {}

    def send(name):
        receipts[name] = delivery.deliver(client, project, role, f"packet {name}")
    senders = [threading.Thread(target=send, args=(name,)) for name in ("context", "report")]
    for sender in senders:
        sender.start()
    for sender in senders:
        sender.join(30)
    # The second sender finds the first turn running and only notifies; nothing is merged,
    # and the first sender's pasted text is never read as a human draft.
    assert sorted(receipt["delivery"] for receipt in receipts.values()) == ["submitted", "visible_notice"]
    assert not any(receipt.get("revoke_automation") for receipt in receipts.values())
    submitted = next(name for name, receipt in receipts.items() if receipt["delivery"] == "submitted")
    assert block(fake, role)["submitted"] == [f"packet {submitted}"]
    assert len(fake.calls("block.event")) == 1 and len(fake.argv("send-key")) == 1


def test_handoff_while_waiting_for_the_input_turn_is_honored(team):
    project, fake, client, current, role = team
    turn = FileLock(directory(project) / "rex-input.lock").acquire()  # Another sender is mid-turn.
    receipts = []
    sender = threading.Thread(target=lambda: receipts.append(delivery.deliver(client, project, role, "Read the packet")))
    sender.start()
    time.sleep(1)
    current["roles"]["main"] = {**role, "automation_owned": False}  # control --mode human completed meanwhile.
    write(directory(project) / "launch.json", current)
    turn.release()
    sender.join(30)
    assert receipts[0]["delivery"] == "visible_notice" and not fake.calls("block.event")


def test_enter_never_follows_a_child_that_took_the_foreground_during_a_slow_check(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(child_during_status=True))
    with pytest.raises(RexError, match="Enter was not sent") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0)
    assert error.value.code == "unconfirmed" and not fake.argv("send-key")


def test_sender_that_waited_for_the_turn_never_reads_the_last_submission_as_a_draft(team):
    project, fake, client, current, role = team
    turn = FileLock(directory(project) / "rex-input.lock").acquire()  # The first sender is mid-turn.
    receipts = []
    sender = threading.Thread(target=lambda: receipts.append(delivery.deliver(client, project, role, "Read packet B")))
    sender.start()
    time.sleep(1)

    def first_submitted(state):
        target = state["blocks"][role["pane_id"]]
        target["records"][0].update(state="working", updated_at="2026-11-21T12:59:00.000000+08:00")
        target["screen"] = ["› Read packet A", "• Working (3s • esc to interrupt)"]
    fake.update(first_submitted)
    turn.release()
    sender.join(30)
    assert receipts[0]["delivery"] == "visible_notice" and not receipts[0]["revoke_automation"]


def test_agent_that_left_the_project_gets_no_input(team, tmp_path):
    project, fake, client, current, role = team
    fake.update(lambda state: state["blocks"][role["pane_id"]]["process"]["foreground"].update(cwd=str(tmp_path)))
    with pytest.raises(RexError, match="no longer holds") as error:
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0)
    assert error.value.code == "owner_changed" and not fake.calls("block.event")


def test_recheck_never_renotifies_but_a_new_delivery_does_and_alert_failure_is_not_unknown(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state["blocks"][role["pane_id"]].update(screen=["Starting Codex…"]))
    first = delivery.deliver(client, project, role, "Read the packet")
    again = delivery.deliver(client, project, role, "Read the packet", renotify=False)  # The bridge's recheck.
    assert first["delivery"] == again["delivery"] == "visible_notice" and again["notice"]["repeated"]
    # A distinct delivery with the same wording (e.g. a second watch update) is notified again.
    delivery.deliver(client, project, role, "Read the packet")
    assert (directory(project) / "NOTICES.md").read_text(encoding="utf-8").count("Read the packet") == 2
    assert len(fake.calls("session.new_block")) == 2
    for change, reason in ((dict(fail_method="session.new_block"), "lost reply"), (dict(alert_exit=1), "did not complete"),
                           (dict(fail_notifier_query=True), "lost reply")):
        fake.update(lambda state: state.update(change))
        failed = delivery.deliver(client, project, role, "Read the other packet")
        assert failed["delivery"] == "visible_notice" and reason in failed["notice"]["alert_error"]
        fake.update(lambda state: [state.pop(key) for key in change])
    alerts = {call["label"] for call in fake.calls("session.new_block")}
    assert alerts == {"SuperARIS notice"} and not any(  # Every created alert block was closed, even after a failed query.
        record["placement"] == "detached" for record in fake.read()["blocks"].values())


def test_rebinding_adopts_the_cli_a_recovery_confirmed(team, tmp_path):
    project, fake, client, current, role = team
    (tmp_path / "moved").mkdir()
    moved = executable(tmp_path / "moved" / "rex", FAKE_REX)
    client.bind({**current, "rex_bin": str(moved)})
    assert client.binary == os.path.abspath(moved) and client.verify_owner(role, project)["pid"] == role["pid"]


def test_child_program_in_front_of_the_agent_gets_only_a_notice(team):
    project, fake, client, current, role = team

    def change(state):
        process = state["blocks"][role["pane_id"]]["process"]
        process["ancestors"].insert(0, process["foreground"])
        process["foreground"] = {"pid": 7777, "name": "vim", "argv0": "vim", "path": "/usr/bin/vim", "cwd": str(project)}
    fake.update(change)
    live = client.verify_owner(role, project)
    assert live["pid"] == role["pid"] and live["status"] == "unknown"  # Its idle report covers the agent, not vim.
    receipt = delivery.deliver(client, project, role, "Read the packet")
    assert receipt["delivery"] == "visible_notice" and not receipt["revoke_automation"]
    with pytest.raises(RexError, match="no input was sent") as error:  # Not unknown: it may resume later.
        client.send_prompt(role["pane_id"], "Read the packet", role, settle=0)
    assert error.value.code == "not_sent"
    assert not fake.calls("block.event") and not fake.argv("send-key")


def test_empty_codex_composer_submits_with_native_receipt(team):
    project, fake, client, current, role = team
    receipt = delivery.deliver(client, project, role, "Read the packet")
    assert receipt["delivery"] == "submitted" and receipt["native_receipt"]["accepted"]


def test_human_draft_revokes_automation_with_durable_notice_and_no_keys(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state["blocks"][role["pane_id"]].update(
        screen=["• earlier answer", "› my unfinished human draft", "  GPT · Context 6% used"]))
    receipt = delivery.deliver(client, project, role, "Packet; with \x1b]9;spoof\x07 bytes")
    assert receipt["delivery"] == "visible_notice" and receipt["revoke_automation"]
    assert not fake.calls("block.event") and not fake.argv("send-key")
    notices = (directory(project) / "NOTICES.md").read_text(encoding="utf-8")
    assert "ARIS work packet ready" in notices
    alert = fake.calls("session.new_block")[0]
    assert alert["session_id"] == current["rex_session"] and alert["options"]["shell"] == "none"
    title, body = alert["options"]["command"][-2:]
    assert ";" not in title and "\x1b" not in body and "\x07" not in body
    assert receipt["notice"]["notifier_block"] not in fake.read()["blocks"]  # One-shot alert closed.


def test_visible_rows_exclude_scrollback_prompts(team):
    project, fake, client, current, role = team
    history = [f"› old prompt {number}" for number in range(100)]
    fake.update(lambda state: state["blocks"][role["pane_id"]].update(screen=[*history, "› Ask Codex to do anything"]))
    fake.update(lambda state: state.update(rows=10))
    screen = client.read_screen(role["pane_id"])
    assert len(screen.splitlines()) == 10 and screen.splitlines()[-1] == "› Ask Codex to do anything"


def test_events_wake_only_for_bound_blocks_and_stop_their_stream(team):
    project, fake, client, current, role = team

    def event(block, name):
        return {"type": "session_event", "payload": {"session_id": current["rex_session"], "event": {
            "type": "block_event", "payload": {"block_id": block, "creator_name": "com.superlogical.terminal",
                                               "name": name, "payload": {}}}}}
    fake.update(lambda state: state.update(events={current["rex_session"]: [
        event("block:other", "program_status_changed"), event(role["pane_id"], "desktop_notification"),
        event(role["pane_id"], "program_status_changed"), event(role["pane_id"], "child_exited")]}))
    stream = client.events([{"type": "pane.agent_status_changed", "pane_id": role["pane_id"]}], timeout=3)
    assert list(stream) == [{"type": "pane.agent_status_changed", "pane_id": role["pane_id"]}] * 2
    assert fake.argv("events") == [["events", "-s", current["rex_session"], "--json"]]


@pytest.mark.skipif(os.name == "nt", reason="POSIX liveness probe; Rex tests are not in the Windows list")
@pytest.mark.parametrize("wrapped", [False, True, "exits"], ids=["direct", "wrapper", "wrapper-exits-first"])
@pytest.mark.parametrize("ending", ["timeout", "receiver_killed", "terminal_hangup"])
def test_event_subscription_never_outlives_its_receiver(team, tmp_path, ending, wrapped):
    project, fake, client, current, role = team
    marker = tmp_path / "events.pid"
    fake.update(lambda state: state.update(events_pid=str(marker)))
    binary = str(fake.binary)
    if wrapped:  # A --rex-bin launcher that runs the real CLI as its own child.
        handoff = ("import time\nfrom pathlib import Path\nwhile not Path({marker!r}).exists():\n    time.sleep(0.05)\n"
                   if wrapped == "exits" else "child.wait()\n").format(marker=str(marker))
        binary = str(executable(tmp_path / "rex-wrapper", f"import subprocess, sys\nchild = subprocess.Popen([{binary!r}, *sys.argv[1:]])\n{handoff}"))
        client = Rex(project, binary, current)
    if wrapped == "exits":  # The relay itself ends the stream the launcher left behind.
        with pytest.raises(RexError, match="event stream closed"):
            list(client.events([{"pane_id": role["pane_id"]}], timeout=10))
    elif ending == "timeout":
        assert list(client.events([{"pane_id": role["pane_id"]}], timeout=0.5)) == []
    else:
        script = ("import json, sys\nfrom pathlib import Path\nfrom superaris.rex import Rex\n"
                  "client = Rex(Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]))\n"
                  "list(client.events([{'pane_id': sys.argv[4]}], timeout=60))\n")
        # A closed terminal hangs up the receiver's whole foreground process group.
        parent = subprocess.Popen([sys.executable, "-c", script, str(project), binary, json.dumps(current), role["pane_id"]],
                                  start_new_session=ending == "terminal_hangup")
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if ending == "terminal_hangup":
            os.killpg(parent.pid, signal.SIGHUP)
        else:
            parent.kill()
        parent.wait()
    stream = int(marker.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(stream, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(stream, signal.SIGKILL)
    pytest.fail("rex events outlived the receiver that subscribed")


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
@pytest.mark.parametrize("ending", ["timeout", "interrupt", "wrapper_exits_first"])
def test_cli_call_never_leaves_a_wrappers_child_running(tmp_path, ending):
    marker = tmp_path / "child.pid"
    wrapper = ("import subprocess, sys\nfrom pathlib import Path\n"
               "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
               f"Path({str(marker)!r}).write_text(str(child.pid))\n" + ("" if ending == "wrapper_exits_first" else "child.wait()\n"))
    call = lambda: rex_exec.execute([sys.executable, "-c", wrapper], dict(os.environ), None,
                                    1 if ending == "timeout" else 20, None, pinned=True)
    began = time.monotonic()
    if ending == "interrupt":  # Ctrl-C in a foreground start or listen.
        threading.Timer(0.8, _thread.interrupt_main).start()
    with pytest.raises({"timeout": subprocess.TimeoutExpired, "interrupt": KeyboardInterrupt,
                        "wrapper_exits_first": OSError}[ending]):
        call()
    assert time.monotonic() - began < 3
    while not marker.exists():
        time.sleep(0.05)
    child = int(marker.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(child, signal.SIGKILL)
    pytest.fail("the wrapper's child outlived the timed-out CLI call")


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_input_call_dies_with_a_caller_that_could_not_clean_up(tmp_path):
    marker = tmp_path / "input.pid"
    cli = f"import os, time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    caller = ("import os, sys\nfrom superaris import rex_exec\n"
              "rex_exec.execute([sys.executable, '-c', sys.argv[1]], dict(os.environ), '{}', 60, None, supervise=True)\n")
    parent = subprocess.Popen([sys.executable, "-c", caller, cli], start_new_session=True)
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    os.killpg(parent.pid, signal.SIGHUP)  # The terminal closed mid-paste; no exception handler runs.
    parent.wait()
    pending = int(marker.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pending, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(pending, signal.SIGKILL)
    pytest.fail("a supervised input call outlived its caller")


@pytest.mark.skipif(os.name == "nt", reason="POSIX pipe EOF check")
def test_input_never_starts_once_its_caller_has_gone(tmp_path):
    marker = tmp_path / "started"
    frame = tmp_path / "frame"
    frame.write_text("0\n")  # A complete Enter frame whose writer already closed the lifeline.
    with frame.open("rb") as lifeline:
        code = subprocess.call(rex_exec.supervised([sys.executable, "-c", f"open({str(marker)!r}, 'w')"]), stdin=lifeline)
    assert code == 125 and not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_large_paste_to_a_slow_reader_still_ends_with_its_caller(tmp_path):
    marker = tmp_path / "read"
    cli = f"import sys, time\ntime.sleep(3)\nopen({str(marker)!r}, 'w').write(str(len(sys.stdin.buffer.read())))\n"
    supervisor = subprocess.Popen(rex_exec.supervised([sys.executable, "-c", cli]), stdin=subprocess.PIPE)
    supervisor.stdin.write(rex_exec.lifeline("x" * 524288).encode())
    supervisor.stdin.flush()
    time.sleep(0.5)
    supervisor.stdin.close()  # The caller died while the paste was still being handed over.
    assert supervisor.wait(5) is not None
    time.sleep(3.5)
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock inheritance")
def test_input_turn_stays_locked_until_a_dead_callers_input_is_gone(tmp_path):
    marker, lock_path = tmp_path / "input.pid", tmp_path / "rex-input.lock"
    cli = f"import os, time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    caller = ("import os, sys\nfrom pathlib import Path\nfrom superaris import rex_exec\nfrom superaris.platform import FileLock\n"
              "lock = FileLock(Path(sys.argv[2])).acquire()\n"
              "rex_exec.execute([sys.executable, '-c', sys.argv[1]], dict(os.environ), '', 60, None, supervise=True, hold=lock.stream.fileno())\n")
    parent = subprocess.Popen([sys.executable, "-c", caller, cli, str(lock_path)], start_new_session=True)
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    pending = int(marker.read_text())
    supervisor = int(subprocess.run(["pgrep", "-P", str(parent.pid)], capture_output=True, text=True).stdout.split()[0])
    os.kill(supervisor, signal.SIGSTOP)  # Hold the supervisor still while its caller dies.
    os.kill(parent.pid, signal.SIGKILL)
    parent.wait()
    with pytest.raises(LockBusy):  # Another sender or a handoff must still wait.
        FileLock(lock_path, blocking=False).acquire()
    os.kill(supervisor, signal.SIGCONT)
    FileLock(lock_path).acquire().release()
    with pytest.raises(ProcessLookupError):
        os.kill(pending, 0)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_timeout_ends_the_cli_even_when_its_supervisor_hangs(tmp_path):
    marker = tmp_path / "input.pid"
    cli = f"import os, time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"

    def freeze_supervisor():
        while not marker.exists():
            time.sleep(0.05)
        pending = marker.read_text()
        parent = subprocess.run(["ps", "-o", "ppid=", "-p", pending], capture_output=True, text=True).stdout.strip()
        os.kill(int(parent), signal.SIGSTOP)
    threading.Thread(target=freeze_supervisor, daemon=True).start()
    with pytest.raises(subprocess.TimeoutExpired):
        rex_exec.execute([sys.executable, "-c", cli], dict(os.environ), "", 2, None, supervise=True)
    pending, deadline = int(marker.read_text()), time.monotonic() + 5
    while time.monotonic() < deadline:  # Killed first, then reaped once its frozen parent is gone.
        try:
            os.kill(pending, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(pending, signal.SIGKILL)
    pytest.fail("the CLI outlived its timed-out, hung supervisor")


@pytest.mark.skipif(os.name == "nt", reason="POSIX job control")
def test_timeout_cleanup_is_not_held_up_by_a_blocked_large_paste(monkeypatch):
    real = rex_exec.spawn

    def frozen(*args, **kwargs):
        process, cli = real(*args, **kwargs)
        os.kill(process.pid, signal.SIGSTOP)  # Hung before it reads the frame; the writer blocks.
        return process, cli
    monkeypatch.setattr(rex_exec, "spawn", frozen)
    outcome = []
    call = threading.Thread(target=lambda: outcome.append(pytest.raises(subprocess.TimeoutExpired, rex_exec.execute,
                            [sys.executable, "-c", "pass"], dict(os.environ), "x" * 1048576, 1, None, supervise=True)),
                            daemon=True)
    call.start()
    call.join(8)
    assert not call.is_alive() and outcome


def test_cli_diagnostics_never_stall_the_visible_rows():
    noisy = "import sys\nsys.stderr.write('x' * 2_000_000)\nprint('history')\nprint('› Ask Codex to do anything')\n"
    returncode, stdout, stderr = rex_exec.execute([sys.executable, "-c", noisy], dict(os.environ), None, 10, 1)
    assert (returncode, stdout) == (0, "› Ask Codex to do anything\n") and len(stderr) < 2_000_000


def test_closed_event_stream_requires_reconciliation(team):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(events_hold=0))
    with pytest.raises(RexError, match="event stream closed"):
        list(client.events([{"pane_id": role["pane_id"]}], timeout=5))


@pytest.mark.parametrize("remote_control,selected", [(True, True), (False, False)])
def test_open_ui_focuses_block_and_respects_remote_control(team, remote_control, selected):
    project, fake, client, current, role = team
    fake.update(lambda state: state.update(remote_control=remote_control, clients=[
        {"client_id": "client:app", "info": {"kind": "app"}}, {"client_id": "client:cli"}]))
    opened = client.open_ui(role["pane_id"])
    assert opened["selected"] is selected and opened["rex_session"] == current["rex_session"]
    assert fake.read()["focused"] == role["pane_id"]
    if selected:
        assert fake.read()["selected"] == ["client:app", f"session_id={current['rex_session']}"]
    else:
        assert "Remote Control" in opened["reason"]


@pytest.mark.parametrize("update,message", [
    ({"server": {"endpoint": "unix:///fake/rex.sock", "instance_id": "i", "host_id": "h", "api_revision": 17}}, "predates"),
    ({"json": False}, "did not return Rex JSON"),
    ({"available": False}, "unavailable"),
])
def test_unusable_server_starts_nothing(tmp_path, monkeypatch, update, message):
    fake = FakeRex(tmp_path, tmp_path, **update)
    install(monkeypatch, fake)
    with pytest.raises(RexError, match=message):
        Rex(tmp_path, str(fake.binary), {"host": "rex"}).ensure_ready(new=True)
    assert not fake.calls("session.create")


def test_missing_recorded_cli_names_explicit_option(tmp_path):
    with pytest.raises(RexError, match="--rex-bin"):
        Rex(tmp_path, None, {"host": "rex", "rex_bin": str(tmp_path / "removed/rex")})
    assert discover_rex(str(tmp_path / "removed/rex"))["cli"] is None
