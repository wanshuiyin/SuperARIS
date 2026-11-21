"""Rex runtime startup, recovery and adoption through the real adapter and fake CLI."""
from contextlib import ExitStack
import os
import shutil
import threading
import time

import pytest

from superaris import bridge, cli, hosts, runtime, wizard
from superaris.client import HerdrError
from superaris.platform import FileLock
from superaris.state import directory, launch_lock, read, write
from tests.rex_support import FakeRex, install


@pytest.fixture
def rex_project(tmp_path, monkeypatch):
    project = tmp_path / "project with spaces"
    project.mkdir()
    fake = FakeRex(tmp_path, project)
    install(monkeypatch, fake)

    def start(*options):
        args = cli.parser().parse_args(["start", str(project), "--host", "rex", "--rex-bin", str(fake.binary),
                                        "--task", "original task", *options])
        return runtime.start(cli.make_plan(args), args), args

    return project, fake, start


def commands_of(fake, method):
    return [request["layout"]["block"]["options"]["command"] if "layout" in request else
            request["initial_windows"][0]["layout"]["block"]["options"]["command"] for request in fake.calls(method)]


def test_new_team_layout_bootstrap_and_reentry_reuse_original_blocks(rex_project):
    project, fake, start = rex_project
    result, _ = start("--automation-owned")
    assert result["host"] == "rex"
    saved = runtime.binding(project)
    assert saved["host"] == "rex" and saved["rex_instance"] == "instance-original"
    assert saved["rex_server"] == "unix:///fake/rex.sock" and saved["rex_host"] == "host-local"
    roles = saved["roles"]
    main, engineer, writer = roles["main"], roles["engineer"], roles["writer"]
    assert len(fake.calls("session.create")) == 1
    splits = fake.calls("session.new_split")
    assert [(split["anchor_id"], split["direction"]) for split in splits] == [
        (main["pane_id"], "horizontal"), (engineer["pane_id"], "vertical")]
    for role in roles.values():
        assert role["rex_session"] == saved["rex_session"] and role["pid"] and role["runtime_id"] == "instance-original"
        assert role["launch_phase"] == "launched" and role["delivery"]["phase"] == "submitted"
        assert role["delivery"]["receipt"]["native_receipt"]["accepted"]
    assert len(fake.calls("block.event")) == 3  # One initial packet per Codex role, no resend.
    assert "pending_start" not in saved
    again, _ = start("--automation-owned")
    assert {action["action"] for action in again["actions"]} == {"reused"}
    assert len(fake.calls("session.create")) == 1 and len(fake.calls("session.new_split")) == 2
    assert len(fake.calls("block.event")) == 3
    assert {name: role["pid"] for name, role in runtime.binding(project)["roles"].items()} == {
        name: role["pid"] for name, role in roles.items()}


def test_native_prompts_ride_their_own_cli_arguments(rex_project):
    project, fake, start = rex_project
    start("--preset", "cc-codex-agy", "--model", "writer=gemini-4-argon-high")
    claude, = commands_of(fake, "session.create")
    codex, agy = commands_of(fake, "session.new_split")
    saved = runtime.binding(project)["roles"]
    native = {kind: os.path.abspath(shutil.which(kind)) for kind in ("claude", "codex", "agy")}
    assert claude[0] == native["claude"] and claude[-1] == saved["main"]["context"]["prompt"]
    assert codex[0] == native["codex"] and codex[1:] == ["--cd", str(project)]
    assert agy[0] == native["agy"] and agy[1:3] == ["--model", "gemini-4-argon-high"]
    assert agy[3:] == ["--prompt-interactive", saved["writer"]["context"]["prompt"]]
    assert saved["main"]["delivery"]["phase"] == saved["writer"]["delivery"]["phase"] == "submitted"
    # The new Codex pane is bootstrapped once even though the team is human-owned.
    assert len(fake.calls("block.event")) == 1 and saved["engineer"]["automation_owned"] is False


def test_lost_create_reply_is_unknown_and_never_relaunched(rex_project):
    project, fake, start = rex_project
    fake.update(lambda state: state.update(fail_method="session.new_split"))
    with pytest.raises(HerdrError, match="lost reply"):
        start()
    saved = runtime.binding(project)
    assert saved["roles"]["engineer"]["launch_phase"] == "unknown"
    assert "lost reply" in saved["roles"]["engineer"]["launch_error"]
    assert saved["roles"]["engineer"]["pane_id"] is None
    assert len(saved["pending_start"]["roles"]) == 3 and saved["host"] == "rex"
    fake.update(lambda state: state.pop("fail_method"))
    with pytest.raises(HerdrError, match="Original Rex launch outcome is unknown"):
        start()
    assert len(fake.calls("session.new_split")) == 1


def test_restarted_server_is_never_rebound(rex_project):
    project, fake, start = rex_project
    start("--only-role", "main")
    fake.update(lambda state: state["server"].update(instance_id="instance-restarted"))
    with pytest.raises(HerdrError, match="instance changed"):
        start("--only-role", "main")
    assert len(fake.calls("session.create")) == 1


def test_explicit_owner_keeps_its_session_and_human_control(rex_project):
    project, fake, start = rex_project

    def user_block(state):
        state["sessions"]["session:user"] = {"label": "my work"}
        state["blocks"]["block:user"] = {
            "session": "session:user", "label": "shell", "host_id": "host-local", "placement": "placed",
            "draft": "", "submitted": [], "options": {},
            "process": {"last_exit": None, "foreground": {"pid": 77, "name": "claude", "argv0": "claude",
                                                          "path": "/bin/claude", "cwd": str(project)}, "ancestors": []},
            "records": [{"state": "idle", "app": "claude-code", "effective_app": "claude-code",
                         "updated_at": "2026-11-21T11:00:00+08:00", "owner": {"pid": 77, "name": "claude"}}]}
    fake.update(user_block)
    result, _ = start("--owner", "block:user", "--preset", "cc-codex")
    main = result["roles"]["main"]
    assert main["pane_id"] == "block:user" and main["rex_session"] == "session:user" and main["pid"] == 77
    assert main["created"] is False and main["automation_owned"] is False
    assert main["delivery"]["phase"] == "visible_notice"
    assert fake.read()["blocks"]["block:user"]["submitted"] == []  # Human input is never typed into.
    alert, = fake.calls("session.new_block")
    assert alert["session_id"] == "session:user"
    assert "ARIS work packet ready" in (directory(project) / "NOTICES.md").read_text(encoding="utf-8")
    saved = runtime.binding(project)
    assert saved["roles"]["engineer"]["rex_session"] == saved["rex_session"] != "session:user"
    assert len(fake.calls("session.create")) == 1 and len(fake.calls("session.new_window")) == 1
    assert not fake.calls("session.new_split")  # The adopted owner's own layout stays untouched.


def test_attach_reveals_verified_main_or_explains_remote_control(rex_project, capsys):
    project, fake, start = rex_project
    start("--only-role", "main")
    fake.update(lambda state: state.update(clients=[{"client_id": "client:app", "info": {"kind": "app"}}],
                                           remote_control=False))
    assert runtime.attach(project) == 0
    main = runtime.binding(project)["roles"]["main"]
    assert fake.read()["focused"] == main["pane_id"]
    assert main["rex_session"] in capsys.readouterr().err
    fake.update(lambda state: state["blocks"][main["pane_id"]]["process"]["foreground"].update(pid=9))
    with pytest.raises(HerdrError, match="Foreground process changed"):
        runtime.attach(project)


@pytest.mark.parametrize("by", ["handle", "role"])
def test_unknown_receiver_bootstrap_is_shared_with_reentry_and_never_resubmitted(rex_project, by):
    project, fake, start = rex_project
    fake.update(lambda state: state.update(screen=["Starting Codex…"]))  # No composer yet: notice only.
    start("--automation-owned", "--only-role", "main")
    main = runtime.binding(project)["roles"]["main"]
    assert main["bootstrap_pending"] and main["delivery"]["phase"] == "visible_notice"
    fake.update(lambda state: (state.pop("screen"), state.update(fail_method="send-key")))
    outcome = bridge.listen(project, duration=5, interval=0.2)
    assert outcome["reason"] == "unknown_requires_inspection" and len(fake.calls("block.event")) == 1
    assert runtime.binding(project)["roles"]["main"]["delivery"]["phase"] == "unknown"
    fake.update(lambda state: state.pop("fail_method"))
    began = time.monotonic()  # A restarted receiver stops on the attempt again instead of listening on.
    assert bridge.listen(project, duration=5, interval=0.2)["pending_unknown"] == outcome["pending_unknown"]
    assert time.monotonic() - began < 4
    again, _ = start("--automation-owned", "--only-role", "main")
    assert [action["action"] for action in again["actions"]] == ["pending_unknown"]
    assert len(fake.calls("block.event")) == 1 and len(fake.argv("send-key")) == 1
    evidence = project / "inspected.txt"
    evidence.write_text("The packet is visible in the Codex transcript.\n")
    target = ["--handle", outcome["pending_unknown"]] if by == "handle" else ["--role", "main"]
    args = cli.parser().parse_args(["resolve-delivery", str(project), *target,
                                    "--resolution", "received", "--evidence", str(evidence)])
    runtime.resolve_delivery(project, args)
    main = runtime.binding(project)["roles"]["main"]
    assert main["delivery"]["phase"] == "received" and main["pending_context"] is None
    assert not read(directory(project) / "bridge.json")["attempts"]  # Either way the receiver resumes.


def notice_only_bootstrap(fake, start):
    fake.update(lambda state: state.update(screen=["Starting Codex…"]))  # No composer yet: notice only.
    start("--automation-owned", "--only-role", "main")
    fake.update(lambda state: state.pop("screen"))


def test_resolution_waits_for_the_receiver_snapshot_it_would_overwrite(rex_project, monkeypatch):
    project, fake, start = rex_project
    notice_only_bootstrap(fake, start)
    fake.update(lambda state: state.update(fail_method="send-key"))
    handle = bridge.listen(project, duration=5, interval=0.2)["pending_unknown"]
    evidence = project / "inspected.txt"
    evidence.write_text("Inspected.\n")
    args = cli.parser().parse_args(["resolve-delivery", str(project), "--handle", handle,
                                    "--resolution", "not-delivered", "--evidence", str(evidence)])
    monkeypatch.setattr(bridge, "RESOLVE_WAIT", 1)
    listener = FileLock(directory(project) / "listen.lock", blocking=False).acquire()
    errors = []
    waiting = threading.Thread(target=lambda: errors.append(pytest.raises(ValueError, runtime.resolve_delivery, project, args)))
    try:
        waiting.start()
        time.sleep(0.3)
        with launch_lock(project):  # The waiting resolution leaves the receiver's launch lock free.
            pass
        waiting.join(5)
    finally:
        listener.release()
    assert "receiver is delivering" in str(errors[0].value)
    assert handle in read(directory(project) / "bridge.json")["attempts"]
    runtime.resolve_delivery(project, args)
    assert runtime.binding(project)["roles"]["main"]["delivery"]["phase"] == "prepared"


@pytest.mark.parametrize("composer_ready", [True, False], ids=["submitted", "notice-then-submitted"])
def test_outcome_reaches_the_role_after_a_launcher_releases_the_lock(rex_project, monkeypatch, composer_ready):
    project, fake, start = rex_project
    notice_only_bootstrap(fake, start)
    if not composer_ready:  # The receiver's own attempt also only notifies; it must stay deferred.
        fake.update(lambda state: state.update(screen=["Starting Codex…"]))
    launcher = ExitStack()
    original = bridge.deliver

    def deliver_while_a_start_begins(*args, **kwargs):
        receipt = original(*args, **kwargs)
        launcher.enter_context(launch_lock(project))
        return receipt
    monkeypatch.setattr(bridge, "deliver", deliver_while_a_start_begins)
    bridge.listen(project, duration=1, interval=0.2)  # Several cycles while the launcher holds the lock.
    assert runtime.binding(project)["roles"]["main"]["delivery"]["phase"] == "attempting"
    assert read(directory(project) / "bridge.json")["settles"]
    launcher.close()
    monkeypatch.setattr(bridge, "deliver", original)
    fake.update(lambda state: state.pop("screen", None))
    bridge.listen(project, duration=1, interval=0.2)
    main = runtime.binding(project)["roles"]["main"]
    assert main["delivery"]["phase"] == "submitted" and "bootstrap_pending" not in main
    assert not read(directory(project) / "bridge.json")["settles"] and len(fake.calls("block.event")) == 1


def test_receiver_subscribes_roles_added_after_it_started(rex_project, monkeypatch):
    project, fake, start = rex_project
    start("--only-role", "main")
    early = runtime.binding(project)
    start("--only-role", "main", "--only-role", "engineer")
    roles = runtime.binding(project)["roles"]
    seen = []

    def client_from_start_time(current, folder, binary, **kwargs):
        client = hosts.client_for_binding(early, folder, binary, **kwargs)
        client.events = lambda subscriptions, timeout: (seen.append(subscriptions), time.sleep(timeout), iter(()))[2]
        return client
    monkeypatch.setattr(bridge, "client_for_binding", client_from_start_time)
    bridge.listen(project, duration=0.3, interval=0.2)
    assert {item["pane_id"] for item in seen[0]} == {roles["main"]["pane_id"], roles["engineer"]["pane_id"]}


def test_wizard_submits_a_bootstrap_whose_composer_became_ready(rex_project, monkeypatch):
    project, fake, _ = rex_project
    fake.update(lambda state: state.update(screen=["Starting Codex…"]))
    options = ["start", str(project), "--host", "rex", "--rex-bin", str(fake.binary), "--only-role", "main",
               "--task", "original task", "--no-receiver"]
    args = cli.parser().parse_args(options)
    args.wizard_arguments, args.wizard_resume_existing, args.ui_language = options, False, "en"
    original = runtime.start

    def start_then_composer_appears(plan, arguments, *rest, **kwargs):
        result = original(plan, arguments, *rest, **kwargs)
        fake.update(lambda state: state.pop("screen", None))
        return result
    monkeypatch.setattr(runtime, "start", start_then_composer_appears)
    wizard._launch_gui(cli.make_plan(args), args, "rex")
    main = runtime.binding(project)["roles"]["main"]
    assert main["automation_owned"] is False and main["delivery"]["phase"] == "submitted"
    assert "bootstrap_pending" not in main and len(fake.calls("block.event")) == 1


def test_first_input_permission_ends_with_its_packet(rex_project):
    project, fake, start = rex_project
    fake.update(lambda state: state.update(screen=["Starting Codex…"]))
    start("--only-role", "main")
    fake.update(lambda state: state.pop("screen"))
    assert runtime.binding(project)["roles"]["main"]["bootstrap_pending"]
    evidence = project / "seen.txt"
    evidence.write_text("The user read the packet.\n")
    runtime.resolve_delivery(project, cli.parser().parse_args(
        ["resolve-delivery", str(project), "--role", "main", "--resolution", "received", "--evidence", str(evidence)]))
    assert "bootstrap_pending" not in runtime.binding(project)["roles"]["main"]
    start("--only-role", "main", "--task", "a new task")
    start("--only-role", "main", "--task", "a new task")
    main = runtime.binding(project)["roles"]["main"]
    assert main["automation_owned"] is False and main["delivery"]["phase"] == "visible_notice"
    assert not fake.calls("block.event")  # The human-owned role never gets the new task typed in.


def test_role_resolution_never_overrides_a_delivery_that_began_meanwhile(rex_project, monkeypatch):
    project, fake, start = rex_project
    notice_only_bootstrap(fake, start)
    fake.update(lambda state: state.update(fail_method="send-key"))
    bridge.listen(project, duration=5, interval=0.2)
    real, lookups = bridge.role_attempt, []

    def role_attempt(folder, role):
        lookups.append(role)  # The unlocked first lookup ran before the receiver recorded its attempt.
        return real(folder, role) if len(lookups) > 1 else None
    monkeypatch.setattr(bridge, "role_attempt", role_attempt)
    evidence = project / "inspected.txt"
    evidence.write_text("Inspected.\n")
    with pytest.raises(ValueError, match="receiver is delivering"):
        runtime.resolve_delivery(project, cli.parser().parse_args(
            ["resolve-delivery", str(project), "--role", "main", "--resolution", "not-delivered", "--evidence", str(evidence)]))
    assert runtime.binding(project)["roles"]["main"]["delivery"]["phase"] == "unknown"
    assert read(directory(project) / "bridge.json")["attempts"]


def test_received_evidence_confirms_a_packet_a_later_start_submitted(rex_project):
    project, fake, start = rex_project
    notice_only_bootstrap(fake, start)
    fake.update(lambda state: state.update(fail_method="send-key"))
    bridge.listen(project, duration=5, interval=0.2)
    current = runtime.binding(project)
    current["roles"]["main"]["delivery"]["phase"] = "submitted"  # e.g. recovery after a crash before the claim.
    runtime.save_binding(project, current)
    evidence = project / "seen.txt"
    evidence.write_text("The packet is in the transcript.\n")
    runtime.resolve_delivery(project, cli.parser().parse_args(
        ["resolve-delivery", str(project), "--role", "main", "--resolution", "received", "--evidence", str(evidence)]))
    main = runtime.binding(project)["roles"]["main"]
    assert main["delivery"]["phase"] == "received" and main["pending_context"] is None


def test_handoff_to_human_waits_for_a_rex_sender_mid_turn(rex_project):
    project, fake, start = rex_project
    start("--automation-owned", "--only-role", "main")
    turn = FileLock(directory(project) / "rex-input.lock").acquire()  # A sender between paste and Enter.
    returned = threading.Event()
    handoff = threading.Thread(target=lambda: (runtime.control(project, "main", "human", "herdr"), returned.set()))
    handoff.start()
    try:
        assert not returned.wait(1)
    finally:
        turn.release()
    handoff.join(30)
    assert returned.is_set() and runtime.binding(project)["roles"]["main"]["automation_owned"] is False


def test_role_resolution_waits_for_an_outcome_not_yet_written_back(rex_project, monkeypatch):
    project, fake, start = rex_project
    notice_only_bootstrap(fake, start)
    launcher = ExitStack()
    original = bridge.deliver

    def deliver_while_a_start_begins(*args, **kwargs):
        receipt = original(*args, **kwargs)
        launcher.enter_context(launch_lock(project))
        return receipt
    monkeypatch.setattr(bridge, "deliver", deliver_while_a_start_begins)
    bridge.listen(project, duration=1, interval=0.2)
    launcher.close()
    evidence = project / "inspected.txt"
    evidence.write_text("Inspected.\n")
    with pytest.raises(ValueError, match="receiver is delivering"):
        runtime.resolve_delivery(project, cli.parser().parse_args(
            ["resolve-delivery", str(project), "--role", "main", "--resolution", "not-delivered", "--evidence", str(evidence)]))
    monkeypatch.setattr(bridge, "deliver", original)
    bridge.listen(project, duration=0.5, interval=0.2)
    assert runtime.binding(project)["roles"]["main"]["delivery"]["phase"] == "submitted"
    assert len(fake.calls("block.event")) == 1


def test_deferred_packet_is_rechecked_without_new_notices(rex_project):
    project, fake, start = rex_project
    fake.update(lambda state: state.update(screen=["Starting Codex…"]))
    start("--automation-owned", "--only-role", "main")
    notices = (directory(project) / "NOTICES.md").read_text(encoding="utf-8")
    bridge.listen(project, duration=1.5, interval=0.2)  # Several idle cycles; the composer never appears.
    assert (directory(project) / "NOTICES.md").read_text(encoding="utf-8") == notices
    assert len(fake.calls("session.new_block")) == 1 and not fake.calls("block.event")
    path = directory(project) / "bridge.json"
    role_notice = runtime.binding(project)["roles"]["main"]["delivery"]["receipt"]["notice"]
    assert read(path)["delivered"]["context-main-0001"]["receipt"]["notice"] == role_notice
    state = read(path)
    original = {"notice_file": "NOTICES.md", "alert_error": "desktop alert failed"}
    state["delivered"]["context-main-0001"]["receipt"] = {"delivery": "visible_notice", "notice": original}
    write(path, state)
    bridge.listen(project, duration=0.5, interval=0.2)
    assert read(path)["delivered"]["context-main-0001"]["receipt"]["notice"] == original  # Rechecks keep it.


def test_wizard_that_cannot_select_the_rex_session_names_it_and_stays_detached(rex_project, monkeypatch, capsys):
    project, fake, _ = rex_project
    fake.update(lambda state: state.update(remote_control=False, clients=[{"client_id": "client:app", "info": {"kind": "app"}}]))
    options = ["start", str(project), "--host", "rex", "--rex-bin", str(fake.binary), "--only-role", "main",
               "--task", "original task", "--no-receiver"]
    args = cli.parser().parse_args(options)
    args.wizard_arguments, args.wizard_resume_existing, args.ui_language = options, False, "en"
    original = runtime.start

    def start_then_native_prompt(plan, arguments, *rest, **kwargs):
        result = original(plan, arguments, *rest, **kwargs)
        main = result["roles"]["main"]["pane_id"]
        fake.update(lambda state: state["blocks"][main]["records"][0].update(state="blocked"))
        return result
    monkeypatch.setattr(runtime, "start", start_then_native_prompt)
    from superaris import rex
    selections = iter([{"selected": True}, {"selected": False, "rex_session": "session-shown", "reason": "Remote Control is off"}])
    monkeypatch.setattr(rex.Rex, "open_ui", lambda self, handle=None: next(selections))
    answers = iter([1, 2])  # Continue after the first prompt; end at the second, unselectable one.
    monkeypatch.setattr(wizard, "choose", lambda prompt, options, default=1: next(answers))
    assert wizard._launch_gui(cli.make_plan(args), args, "rex") is None
    assert "Open Rex and select session session-shown" in capsys.readouterr().out and args.wizard_attached is False


def test_writer_added_after_its_engineer_closed_splits_from_main(rex_project):
    project, fake, start = rex_project
    start("--only-role", "main", "--only-role", "engineer")
    roles = runtime.binding(project)["roles"]
    fake.update(lambda state: state["blocks"].pop(roles["engineer"]["pane_id"]))
    start("--only-role", "writer")
    split = fake.calls("session.new_split")[-1]
    assert split["anchor_id"] == roles["main"]["pane_id"] and split["direction"] == "horizontal"
    writer = runtime.binding(project)["roles"]["writer"]
    assert writer["launch_phase"] == "launched" and writer["pane_id"]


def test_resuming_one_role_skips_an_unselected_closed_collaborator(rex_project):
    project, fake, start = rex_project
    start("--only-role", "main", "--only-role", "engineer")
    fake.update(lambda state: state["blocks"].pop(runtime.binding(project)["roles"]["engineer"]["pane_id"]))
    options = ["start", str(project), "--host", "rex", "--rex-bin", str(fake.binary), "--only-role", "writer",
               "--task", "original task", "--no-receiver"]
    args = cli.parser().parse_args(options)
    args.wizard_arguments, args.wizard_resume_existing, args.ui_language = options, False, "en"
    # Both the check before start and the one after it (pending_start is gone by then) skip the engineer.
    result = wizard._launch_gui(cli.make_plan(args), args, "rex")
    assert result["roles"]["writer"]["launch_phase"] == "launched"


@pytest.mark.parametrize("failure", ["wrapper: line 3: cleanup: command not found",
                                     'Error: block target "block:gone" not found (status=404 code=not_found)'])
def test_wrapper_failing_after_a_created_split_is_not_retried(rex_project, failure):
    project, fake, start = rex_project
    start("--only-role", "main", "--only-role", "engineer")
    fake.update(lambda state: state.update(wrapper_fails_after_create=failure))
    with pytest.raises(HerdrError, match="not found"):
        start("--only-role", "writer")
    assert len(fake.calls("session.new_split")) == 2  # The engineer's, then the writer's once.
    writer = runtime.binding(project)["roles"]["writer"]
    assert writer["launch_phase"] == "unknown" and not writer["pane_id"]
    assert '"block_ids"' in writer["launch_receipt"]  # Kept for inspection, never bound automatically.


def test_role_creation_never_outlives_the_launcher(rex_project, monkeypatch):
    project, fake, start = rex_project
    from superaris import rex
    real, flags = rex.execute, {}

    def record(argv, *rest, supervise=False, **options):
        if "api" in argv:
            flags.setdefault(argv[argv.index("api") + 2], set()).add(supervise)
        return real(argv, *rest, supervise=supervise, **options)
    monkeypatch.setattr(rex, "execute", record)
    start("--only-role", "main", "--only-role", "engineer")
    # Each create carries a role's command and may carry its first packet.
    assert flags["session.create"] == flags["session.new_split"] == {True}


def test_wizard_leaves_the_final_attach_to_main_after_a_collaborator_prompt(rex_project, monkeypatch):
    project, fake, _ = rex_project
    options = ["start", str(project), "--host", "rex", "--rex-bin", str(fake.binary), "--only-role", "main",
               "--only-role", "engineer", "--task", "original task", "--no-receiver"]
    args = cli.parser().parse_args(options)
    args.wizard_arguments, args.wizard_resume_existing, args.ui_language = options, False, "en"
    original, prompted = runtime.start, []

    def start_then_native_prompt(plan, arguments, *rest, **kwargs):
        result = original(plan, arguments, *rest, **kwargs)
        engineer = result["roles"]["engineer"]["pane_id"]
        if not prompted:
            fake.update(lambda state: state["blocks"][engineer]["records"][0].update(state="blocked"))
        return result

    def handled(prompt, options, default=1):
        prompted.append(True)  # The user answers the engineer's prompt in Rex, then continues.
        engineer = runtime.binding(project)["roles"]["engineer"]["pane_id"]
        fake.update(lambda state: state["blocks"][engineer]["records"][0].update(state="idle"))
        return 1
    monkeypatch.setattr(runtime, "start", start_then_native_prompt)
    from superaris import rex
    monkeypatch.setattr(rex.Rex, "open_ui", lambda self, handle=None: {"selected": True})
    monkeypatch.setattr(wizard, "choose", handled)
    assert wizard._launch_gui(cli.make_plan(args), args, "rex")["roles"].keys() == {"main", "engineer"}
    assert prompted and args.wizard_attached is False


def test_first_recheck_takes_the_receipt_of_the_packet_it_rechecks(rex_project, monkeypatch):
    project, fake, start = rex_project
    fake.update(lambda state: state.update(screen=["Starting Codex…"]))
    start("--automation-owned", "--only-role", "main")
    real, updated = bridge._pending_signals, []

    def start_task_meanwhile(folder, client):
        if not updated:  # A start --task lands after this cycle's reconciliation read the binding.
            current = runtime.binding(folder)
            main = current["roles"]["main"]
            main["context"] = {**main["context"], "packet": main["context"]["packet"].replace("0001", "0002")}
            main["delivery"] = {"phase": "visible_notice", "packet": main["context"]["packet"],
                                "receipt": {"delivery": "visible_notice", "notice": {"notice_file": "new packet"}}}
            runtime.save_binding(folder, current)
            updated.append(True)
        return real(folder, client)
    monkeypatch.setattr(bridge, "_pending_signals", start_task_meanwhile)
    bridge.listen(project, duration=0.5, interval=0.2)
    entry = read(directory(project) / "bridge.json")["delivered"]["context-main-0002"]
    assert entry["receipt"]["notice"] == {"notice_file": "new packet"}
