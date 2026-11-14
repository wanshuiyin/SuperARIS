"""Update failures and development installs never turn into reported success."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from superaris import cli, receiver, updater


def test_check_timeout_is_meaningful_and_never_installs(monkeypatch, capsys):
    monkeypatch.setattr(updater, "installation", lambda: {})
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 45)
    monkeypatch.setattr(updater.subprocess, "run", timeout)
    assert cli.main(["update", "--check"]) == 1
    assert "timed out; no update attempted" in capsys.readouterr().err


def test_source_entry_is_rejected_without_reset_or_network(monkeypatch, tmp_path):
    path = tmp_path / "dirty source" / "updater.py"
    path.parent.mkdir(); path.write_text("uncommitted source")
    monkeypatch.setattr(updater, "__file__", str(path))
    with pytest.raises(ValueError, match="Source/editable or global"):
        updater.installation()
    assert path.read_text() == "uncommitted source"


def test_foreign_git_source_is_not_redirected(monkeypatch):
    dist = SimpleNamespace(version="0.1.0", metadata={},
        read_text=lambda name: json.dumps({"url": "https://example.invalid/own-fork.git", "vcs_info": {"commit_id": "a" * 40}}),
        locate_file=lambda name: Path(updater.__file__).resolve().parent)
    monkeypatch.setattr(updater.metadata, "distribution", lambda name: dist)
    monkeypatch.setattr(sys, "base_prefix", "not-this-test-environment")
    with pytest.raises(ValueError, match="different Git source"):
        updater.installation()


def test_current_commit_never_reinstalls(monkeypatch, capsys):
    monkeypatch.setattr(updater, "installation", lambda: {"version": "0.1.0", "revision": "a" * 40,
                                                        "manager": "pip", "prefix": "test-only"})
    monkeypatch.setattr(updater, "latest_revision", lambda: "a" * 40)
    monkeypatch.setattr(updater, "install_command", lambda *args: pytest.fail("already-current update must not install"))
    assert cli.main(["update"]) == 0
    assert "Already current" in capsys.readouterr().out


@pytest.mark.parametrize("return_code", [0, 23])
def test_worker_reports_failure_for_manager_error_or_unverified_revision(tmp_path, return_code):
    job = {"old": {"python": sys.executable, "prefix": sys.prefix, "revision": "old"},
           "target": "f" * 40, "wait_for_exit": False,
           "command": [sys.executable, "-c", f"raise SystemExit({return_code})"], "environment": {}}
    path = tmp_path / "job.json"; path.write_text(json.dumps(job))
    assert updater._worker(path) == 1
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["status"] == "failed" and result["exit_code"] == 1
    assert ("Package manager exited 23" if return_code else "did not match") in result["error"]


def test_receiver_identity_does_not_become_new_code_when_metadata_changes(monkeypatch):
    monkeypatch.setattr(receiver, "_REVISION", "old-commit")
    monkeypatch.setattr(receiver, "installed_revision", lambda: "new-commit")
    assert receiver.implementation()["revision"] == "old-commit"
