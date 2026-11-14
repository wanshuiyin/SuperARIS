"""Herdr installation and existing-server checks without real system mutation."""

import json
import subprocess

import pytest

from superaris import client as transport


def test_missing_herdr_no_install_never_invokes_installer_or_server(tmp_path, monkeypatch):
    monkeypatch.setattr(transport.shutil, "which", lambda name: None)

    def forbidden(*args, **kwargs):
        pytest.fail("--no-install must not run Homebrew, a server, or another process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    log = tmp_path / "generated" / "server.log"
    with pytest.raises(transport.HerdrError, match="--no-install"):
        transport.Herdr("isolated-test").ensure(log, install=False)
    assert not log.parent.exists()


def test_installer_uses_existing_homebrew_and_exact_package_argv(monkeypatch):
    monkeypatch.setattr(transport, "WINDOWS", False)
    monkeypatch.setattr(transport.shutil, "which", lambda name: "/existing/brew" if name == "brew" else None)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    transport.install_herdr()
    assert calls == [(["/existing/brew", "install", "herdr"], {"check": False})]


@pytest.mark.parametrize("stale", [False, True])
def test_existing_session_socket_is_probed_without_server_restart(tmp_path, monkeypatch, stale):
    socket = tmp_path / "existing-session.sock"
    socket.touch()
    monkeypatch.setattr(transport.shutil, "which", lambda name: "/existing/herdr" if name == "herdr" else None)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert argv[:3] == ["herdr", "--session", "isolated-test"]
        assert not kwargs.get("shell", False)
        if argv[3:] == ["status"]:
            return subprocess.CompletedProcess(argv, 0, f"socket: {socket}\n", "")
        assert argv[3:] == ["api", "snapshot"]
        if stale:
            return subprocess.CompletedProcess(argv, 1, "", "existing socket is unavailable")
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": {"snapshot": {"agents": []}}}), "")

    def forbidden(*args, **kwargs):
        pytest.fail("an existing session socket is not permission to restart its server")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    log = tmp_path / "generated" / "server.log"
    if stale:
        with pytest.raises(transport.HerdrError, match="socket is unavailable"):
            transport.Herdr("isolated-test").ensure(log)
    else:
        transport.Herdr("isolated-test").ensure(log)
    assert calls == [
        ["herdr", "--session", "isolated-test", "status"],
        ["herdr", "--session", "isolated-test", "api", "snapshot"],
    ]
    assert socket.exists()
    assert not log.parent.exists()


def test_windows_installer_uses_official_command_and_process_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "WINDOWS", True)
    monkeypatch.setattr(transport.shutil, "which", lambda name: "powershell.exe" if name == "powershell" else None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", "original-path")
    alias = tmp_path / "Programs/Herdr/bin"
    alias.mkdir(parents=True)
    (alias / "herdr.exe").write_bytes(b"fake installed executable")
    calls = []
    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    transport.install_herdr()
    assert calls == [["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                      "irm https://herdr.dev/install.ps1 | iex"]]
    assert transport.os.environ["PATH"].startswith(str(alias) + transport.os.pathsep)


class MainTransport:
    """Official-shaped responses; no native program or model is invoked."""
    session = "main-exit-test"

    def __init__(self, project, mode):
        self.project, self.mode, self.calls = project, mode, []

    def json(self, *args):
        self.calls.append(args)
        if self.mode == "transport-error":
            raise transport.HerdrError("Permission denied while reading host API")
        if args[:2] == ("notification", "show"):
            return {}
        if args[:2] == ("agent", "get"):
            status = "busy" if self.mode == "busy-shell" else "idle" if self.mode in {"shell", "changed", "unrecognized"} else self.mode
            return {"agent": {"pane_id": args[2], "agent": "claude", "agent_status": status,
                              "agent_session": {"value": "original-native"}}}
        if args[:2] == ("pane", "process-info"):
            return {"process_info": {"foreground_processes": [{
                "argv": ["powershell.exe" if self.mode in {"shell", "busy-shell"} else "unrecognized.exe" if self.mode == "unrecognized" else "claude.exe"],
                "cwd": str(self.project), "pid": 99 if self.mode == "changed" else 41,
            }]}}
        raise AssertionError(f"Unexpected mutation: {args}")

    def snapshot(self):
        return {"agents": [{"pane_id": "w1:p1"}]}

    def events(self, subscriptions, timeout):
        self.mode = "shell"
        yield {"type": "pane.agent_status_changed"}


@pytest.fixture
def main_exit_project(tmp_path):
    from superaris import receiver
    from superaris.runtime import save_binding
    from superaris.state import directory, write
    project = tmp_path / "project with spaces"
    project.mkdir()
    bound = {"project": str(project), "session": "main-exit-test", "ui_language": "en", "roles": {
        "main": {"pane_id": "w1:p1", "harness": "claude", "pid": 41, "native_session_id": "original-native",
                 "automation_owned": False, "inputs": {"task": "Original task"},
                 "delivery": {"phase": "unknown", "packet": "original-packet"}},
        "writer": {"pane_id": "w1:p3", "harness": "agy", "inputs": {"task": "Original research assignment"}},
    }}
    save_binding(project, bound)
    write(directory(project) / "receiver.json", {"generation": "original", "owner": receiver.signature(bound)})
    write(directory(project) / "receiver-control.json", {"enabled": True, "generation": "original"})
    return project


@pytest.mark.parametrize("mode,expected,language", [
    ("shell", "back at a shell", "en"), ("changed", "identity changed", "en"),
    ("unrecognized", "cannot currently be verified", "en"), ("transport-error", "cannot currently be verified", "en"),
    ("busy-shell", "cannot currently be verified", "en"),
    ("event-exit", "back at a shell", "en"), ("shell", "主控窗格已回到 Shell", "zh"),
])
def test_main_loss_notifies_once_and_preserves_original_records(main_exit_project, monkeypatch, mode, expected, language):
    from superaris import receiver, bridge
    from superaris.state import directory, read, write
    project = main_exit_project
    root = directory(project)
    bound = read(root / "launch.json")
    bound["ui_language"] = language
    write(root / "launch.json", bound)
    before = (root / "launch.json").read_bytes()
    fake = MainTransport(project, "idle" if mode == "event-exit" else mode)
    monkeypatch.setattr(receiver, "client_for_binding", lambda *a, **k: fake)
    monkeypatch.setattr(bridge, "client_for_binding", lambda *a, **k: fake)
    result = receiver.run(project, "original")
    assert result["status"] == "stopped"
    assert result["outcome"]["reason"] == "owner_or_server_unavailable"
    assert (root / "launch.json").read_bytes() == before
    assert not receiver.held(root / "receiver-owner.lock")
    assert not receiver.held(root / "listen.lock")
    notices = [a for a in fake.calls if a[:2] == ("notification", "show")]
    assert len(notices) == 1
    assert notices[0][2] == ("SuperARIS receiving paused" if language == "en" else "SuperARIS 收件已暂停")
    assert expected in notices[0][notices[0].index("--body") + 1]
    assert str(root / "receiver.json") in notices[0][notices[0].index("--body") + 1]
    assert result["owner_notice"]["delivery"] == ("unknown" if mode == "transport-error" else "visible_notice")
    if mode == "event-exit":
        assert result["outcome"]["owner_state"] == "shell"
    receiver.run(project, "original")
    assert sum(a[:2] == ("notification", "show") for a in fake.calls) == 1
    assert (root / "launch.json").read_bytes() == before
    assert read(root / "receiver.json")["owner"] == result["owner"]
    assert all(a[:2] not in {("agent", "start"), ("agent", "prompt"), ("agent", "focus")} for a in fake.calls)


@pytest.mark.parametrize("mode", ["busy", "blocked"])
def test_verified_busy_or_blocked_main_does_not_trigger_exit_notice(main_exit_project, monkeypatch, mode):
    from superaris import receiver, bridge
    from superaris.state import directory
    fake = MainTransport(main_exit_project, mode)
    before = (directory(main_exit_project) / "launch.json").read_bytes()
    monkeypatch.setattr(receiver, "client_for_binding", lambda *a, **k: fake)
    monkeypatch.setattr(bridge, "listen", lambda *a, **k: {"reason": "stopped"})
    result = receiver.run(main_exit_project, "original")
    assert result["outcome"]["reason"] == "stopped"
    assert "owner_notice" not in result
    assert not any(a[:2] == ("notification", "show") for a in fake.calls)
    assert (directory(main_exit_project) / "launch.json").read_bytes() == before
