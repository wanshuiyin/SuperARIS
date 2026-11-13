"""AGY continuation uses the existing bound owner and receiver receipt ledger."""
from types import SimpleNamespace

import pytest

from superaris import bridge, runtime, tasks
from superaris.client import HerdrError
from superaris.delivery import agy_input, empty_agy_input
from superaris.state import directory, read, write
from .test_workbench_bridge import running, signal, _ACTUAL_PENDING_SIGNALS


PLACEHOLDER = "Auto mode: edits & safe commands auto-approved (shift+tab to cycle)"


def composer(text=PLACEHOLDER, footer="? for shortcuts  auto · Gemini 4 Carbon · medium"):
    return f"Previous response\n{'─' * 40}\n> {text}\n{'─' * 40}\n{footer}\n"


@pytest.fixture
def agy_running(running, monkeypatch):
    project, client, clock = running
    client.roles["main"].update(harness="agy", automation_owned=True, pid=7, native_session_id="original-agy")
    client.native = "original-agy"
    client.pid = 7
    client.kind = "agy"
    client.visible = composer()
    original = client.json

    def json(*args):
        if args[:2] == ("agent", "get") and args[2] == "w1:p1":
            return {"agent": {"pane_id": args[2], "agent": client.kind, "agent_status": client.status,
                              "agent_session": {"value": client.native}}}
        if args[:2] == ("pane", "process-info") and args[-1] == "w1:p1":
            return {"process_info": {"foreground_processes": [
                {"argv": [client.kind], "cwd": str(project), "pid": client.pid}]}}
        return original(*args)

    monkeypatch.setattr(client, "json", json)
    write(directory(project) / "launch.json", {"session": "test-only", "roles": client.roles})
    return project, client, clock


@pytest.mark.parametrize("text,expected", [(PLACEHOLDER, True), ("", True), ("my draft", False),
                                           ("\n  second draft line", False)])
def test_agy_composer_includes_all_draft_lines(text, expected):
    assert empty_agy_input(composer(text)) is expected
    assert agy_input(composer(text)) is not None


@pytest.mark.parametrize("screen", ["> Auto mode: edits & safe commands auto-approved (shift+tab to cycle)",
    "Do you trust the contents of this project?\n> Yes, I trust this folder",
    composer(footer="esc to cancel"), "Antigravity CLI loading..."])
def test_unverified_agy_surfaces_never_look_empty(screen):
    assert agy_input(screen) is None
    assert not empty_agy_input(screen)


def test_agy_ansi_composer_and_old_transcript_prompt():
    assert empty_agy_input("\x1b[31m" + composer() + "\x1b[0m")
    assert not empty_agy_input(composer() + "\n> pending unrelated input")


def test_agy_busy_idle_restart_and_duplicate_signal(agy_running):
    project, client, _ = agy_running
    client.status = "working"
    client.signals = [signal()]
    first = bridge.listen(project, duration=0)
    assert first["deliveries"][0]["delivery"] == "visible_notice"
    assert read(directory(project) / "bridge.json")["deferred"]
    client.signals = []
    client.status = "idle"
    second = bridge.listen(project, duration=0)
    assert second["deliveries"][0]["delivery"] == "submitted"
    assert client.actions[-1] == ("agent", "prompt", "w1:p1", "Read actual receipt")
    assert not read(directory(project) / "bridge.json")["deferred"]
    client.signals = [signal()]
    assert not bridge.listen(project, duration=0)["deliveries"]
    assert len(client.actions) == 2


@pytest.mark.parametrize("status", ["working", "blocked", "unknown"])
def test_agy_active_and_unclassified_states_never_receive_input(agy_running, status):
    project, client, _ = agy_running
    client.status = status
    client.signals = [signal()]
    bridge.listen(project, duration=0)
    assert client.actions[0][:2] == ("notification", "show")
    assert len(client.actions) == 1


def test_agy_draft_revokes_automation_and_clearing_it_does_not_resume(agy_running):
    project, client, _ = agy_running
    client.visible = composer("preserve my draft\n  and its second line")
    client.signals = [signal()]
    bridge.listen(project, duration=0)
    assert runtime.binding(project)["roles"]["main"]["automation_owned"] is False
    client.visible = composer()
    client.signals = []
    bridge.listen(project, duration=0)
    assert len(client.actions) == 1
    assert not read(directory(project) / "bridge.json")["deferred"]


def test_agy_human_control_cancels_deferred_input(agy_running):
    project, client, _ = agy_running
    client.status = "working"
    client.signals = [signal()]
    bridge.listen(project, duration=0)
    runtime.control(project, "main", "human", "fake")
    client.status = "idle"
    client.signals = []
    bridge.listen(project, duration=0)
    assert len(client.actions) == 1
    assert not read(directory(project) / "bridge.json")["deferred"]


@pytest.mark.parametrize("changed", ["native", "pid", "kind"])
def test_agy_second_identity_check_prevents_changed_owner(agy_running, monkeypatch, changed):
    project, client, _ = agy_running
    client.signals = [signal()]
    def screen(*args):
        setattr(client, changed, {"native": "different-session", "pid": 8, "kind": "claude"}[changed])
        return composer()
    monkeypatch.setattr(client, "run", screen)
    result = bridge.listen(project, duration=0)
    assert result["reason"] == "unknown_requires_inspection"
    assert not client.actions


def test_agy_unknown_send_is_not_resent_after_receiver_restart(agy_running, monkeypatch):
    project, client, _ = agy_running
    client.signals = [signal()]
    original = client.json
    def unknown(*args):
        if args[:2] == ("agent", "prompt"):
            client.actions.append(args)
            raise HerdrError("submission outcome unknown")
        return original(*args)
    monkeypatch.setattr(client, "json", unknown)
    assert bridge.listen(project, duration=0)["reason"] == "unknown_requires_inspection"
    assert bridge.listen(project, duration=0)["reason"] == "unknown_requires_inspection"
    assert len(client.actions) == 1


def test_agy_real_report_reconciliation_submits_once(agy_running, monkeypatch):
    project, client, _ = agy_running
    monkeypatch.setattr(bridge, "_pending_signals", _ACTUAL_PENDING_SIGNALS)
    (project / "TASK.md").write_text("Read the result and continue the authorized task.")
    tasks.register(project, SimpleNamespace(id="report", owner_role="main", worker_role=None,
        record="TASK.md", deliverable=["RESULT.md"], watch_file=[], wait_for="actual result", query="local files",
        next="Read RESULT.md and write CONTINUED.md"))
    (project / "RESULT.md").write_text("17 25")
    tasks.report(project, "report", "completed", "RESULT.md is ready")
    assert bridge.listen(project, duration=0)["deliveries"][0]["delivery"] == "submitted"
    assert not bridge.listen(project, duration=0)["deliveries"]
    assert len(client.actions) == 1
    assert "Read RESULT.md and write CONTINUED.md" in client.actions[0][-1]


def test_orca_agy_stays_notice_based(agy_running, monkeypatch):
    project, client, _ = agy_running
    client.host = "orca"
    monkeypatch.setattr(client, "verify_owner", lambda role, project: {**role, "status": "idle"}, raising=False)
    monkeypatch.setattr(client, "notice", lambda title, text: {}, raising=False)
    from superaris.delivery import deliver
    assert deliver(client, project, client.roles["main"], "Read result")["delivery"] == "visible_notice"
    assert not client.actions


def test_agy_wrapped_native_placeholder():
    assert empty_agy_input(composer("Auto mode: edits & safe commands auto-approved\n  (shift+tab to cycle)"))


def test_agy_human_control_during_input_read_prevents_submission(agy_running, monkeypatch):
    project, client, _ = agy_running
    client.signals = [signal()]
    def screen(*args):
        runtime.control(project, "main", "human", "fake")
        return composer()
    monkeypatch.setattr(client, "run", screen)
    result = bridge.listen(project, duration=0)
    assert result["deliveries"][0]["delivery"] == "visible_notice"
    assert len(client.actions) == 1 and client.actions[0][:2] == ("notification", "show")
