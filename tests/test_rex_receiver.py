"""Real receiver child processes with the file-backed fake Rex CLI.

These exercise subprocess/lock/event-stream lifetimes, not a native Rex server or LLM.
"""
import json
import os
import signal
import subprocess
import time

import pytest

from superaris import cli, receiver, runtime
from tests.rex_support import FakeRex, install
from tests.support import CLI
from tests.test_workbench_receiver import wait_until


class RexProject:
    def __init__(self, folder, monkeypatch, automation):
        self.project = folder / "project with spaces"
        self.project.mkdir()
        self.root = self.project / ".aris/workbench"
        (self.project / "CURRENT.md").write_text("Original acceptance remains authoritative.\n")
        self.fake = FakeRex(folder, self.project)
        install(monkeypatch, self.fake)
        options = ["start", str(self.project), "--host", "rex", "--rex-bin", str(self.fake.binary),
                   "--only-role", "main", "--task", "original task", *(["--automation-owned"] if automation else [])]
        args = cli.parser().parse_args(options)
        runtime.start(cli.make_plan(args), args)
        self.main = runtime.binding(self.project)["roles"]["main"]

    def run(self, command, *options):
        result = subprocess.run([*CLI, command, str(self.project), *map(str, options)], env=os.environ.copy(),
                                capture_output=True, text=True, timeout=30, check=False)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def start(self):
        result = self.run("receiver", "--action", "start")
        wait_until(lambda: receiver.status(self.project)["receiving"])
        return result

    def report(self, identifier):
        (self.project / "result.txt").write_text("Actual late test artifact.\n")
        self.run("watch", "--id", identifier, "--record", "CURRENT.md", "--deliverable", "result.txt",
                 "--wait-for", "actual artifact", "--query", "original worker query", "--next", "Apply original acceptance")
        return self.run("report", "--id", identifier, "--outcome", "completed", "--message", "Ready for verification")

    def bridge(self):
        path = self.root / "bridge.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def submitted(self):
        return self.fake.read()["blocks"][self.main["pane_id"]]["submitted"]


@pytest.fixture(params=[False, True], ids=["human", "automation"])
def rex_team(tmp_path, monkeypatch, request):
    fixture = RexProject(tmp_path, monkeypatch, request.param)
    yield fixture
    receiver.stop(fixture.project)
    deadline = time.monotonic() + 10
    while receiver.status(fixture.project)["managed_process_alive"] and time.monotonic() < deadline:
        time.sleep(.05)
    remaining = receiver.status(fixture.project)
    if remaining["managed_process_alive"] and remaining.get("pid"):
        os.kill(remaining["pid"], signal.SIGTERM)


def test_late_report_reaches_original_owner_once(rex_team):
    fixture = rex_team
    started = fixture.start()
    assert started["owner"]["host"] == "rex" and started["owner"]["pid"] == fixture.main["pid"]
    assert started["owner"]["runtime_id"] == "instance-original"
    before = list(fixture.submitted())
    reported = fixture.report("late")
    delivered = wait_until(lambda: fixture.bridge().get("delivered", {}).get("late"))
    # The bootstrap turn is still working: both owners first get a durable notice.
    assert delivered["delivery"] == "visible_notice" and fixture.submitted() == before
    assert (fixture.root / "NOTICES.md").read_text().count("ARIS registered task late") == 1
    if fixture.main["automation_owned"]:
        assert "late" in fixture.bridge()["deferred"]
        fixture.fake.update(lambda state: state["blocks"][fixture.main["pane_id"]]["records"][0].update(
            state="done", updated_at="2026-11-21T12:59:59.000000+08:00"))
        delivered = wait_until(lambda: (entry if (entry := fixture.bridge()["delivered"]["late"])["delivery"] == "submitted"
                                        else None))
        assert delivered["receipt"]["native_receipt"]["accepted"]
        assert fixture.bridge()["deferred"] == {}
        assert len(fixture.submitted()) == len(before) + 1
        assert "ARIS registered task late" in fixture.submitted()[-1]
    else:
        assert fixture.bridge().get("deferred", {}) == {}
    baseline = len(fixture.fake.argv("events"))
    wait_until(lambda: len(fixture.fake.argv("events")) >= baseline + 2)  # Stream re-armed without resending.
    assert len(fixture.submitted()) == len(before) + (1 if fixture.main["automation_owned"] else 0)
    assert reported["acceptance"] == "not_evaluated"
    assert (fixture.project / "CURRENT.md").read_text() == "Original acceptance remains authoritative.\n"


def test_replaced_owner_process_stops_receiver_without_input(rex_team):
    fixture = rex_team
    original = fixture.start()
    before = list(fixture.submitted())
    fixture.fake.update(lambda state: state["blocks"][fixture.main["pane_id"]]["process"]["foreground"].update(pid=31337))
    wait_until(lambda: not receiver.status(fixture.project)["managed_process_alive"])
    stopped = receiver.status(fixture.project)
    assert stopped["outcome"]["reason"] == "owner_or_server_unavailable"
    assert stopped["generation"] == original["generation"]
    assert fixture.submitted() == before
    assert runtime.binding(fixture.project)["roles"]["main"]["pid"] == fixture.main["pid"]
