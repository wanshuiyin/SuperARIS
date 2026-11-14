"""Real installed Git upgrades in private environments; no native/model calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv

import pytest

from tests.test_windows_platform import native_receiver_project  # noqa: F401
from tests import test_workbench_receiver as receiver_cases


REPO = Path(__file__).resolve().parents[1]


class GitInstallation:
    def __init__(self, root, manager):
        self.root, self.manager = root, manager
        root.mkdir()
        home = root / "home"; home.mkdir()
        temporary = root / "tmp"; temporary.mkdir()
        self.source = root / "source"; self.source.mkdir()
        for name in ("README.md", "LICENSE", "NOTICE", "pyproject.toml"):
            shutil.copyfile(REPO / name, self.source / name)
        shutil.copytree(REPO / "src", self.source / "src",
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        self.env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
                    "XDG_CACHE_HOME": str(root / "cache"), "PIP_CACHE_DIR": str(root / "pip-cache"),
                    "PIP_CONFIG_FILE": os.devnull, "PIP_INDEX_URL": "https://pypi.org/simple",
                    "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
                    "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "TEMP": str(temporary), "TMP": str(temporary), "TMPDIR": str(temporary),
                    "PIPX_HOME": str(root / "pipx"), "PIPX_BIN_DIR": str(root / "bin"),
                    "PIPX_MAN_DIR": str(root / "man"), "PIPX_DEFAULT_PYTHON": sys.executable}
        for key in ("PYTHONPATH", "PIP_EXTRA_INDEX_URL", "GIT_DIR", "GIT_WORK_TREE"):
            self.env.pop(key, None)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Update Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.marker = self.source / "src/superaris/__init__.py"
        self.marker.write_text(self.marker.read_text() + '\nUPDATE_FIXTURE = "old"\n', encoding="utf-8")
        self.git("add", "."); self.git("commit", "-m", "Old same-version installation")
        self.old = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("config", "--global", f"url.{self.source.as_uri()}.insteadOf",
                 "https://github.com/wanshuiyin/SuperARIS.git")
        spec = f"git+https://github.com/wanshuiyin/SuperARIS.git@{self.old}"
        if manager == "pipx":
            self.run([shutil.which("pipx"), "install", "--python", sys.executable, spec], "install-old")
            self.prefix = root / "pipx/venvs/superaris"
            self.entry = root / "bin" / ("superaris.exe" if os.name == "nt" else "superaris")
        else:
            self.prefix = root / "venv"
            venv.EnvBuilder(with_pip=True).create(self.prefix)
            python = self.prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self.run([python, "-m", "pip", "install", spec], "install-old")
            self.entry = self.prefix / ("Scripts/superaris.exe" if os.name == "nt" else "bin/superaris")
        self.python = self.prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if os.name == "nt" and manager == "pipx":
            # pipx supports copied launchers when Windows symlinks are unavailable.
            self.entry.unlink()
            shutil.copyfile(self.prefix / "Scripts/superaris.exe", self.entry)

    def run(self, argv, name, cwd=None, success=True):
        response = subprocess.run(list(map(str, argv)), cwd=cwd or self.root, env=self.env,
                                  capture_output=True, text=True, encoding="utf-8", timeout=240)
        (self.root / (name + ".txt")).write_text(response.stdout + response.stderr, encoding="utf-8")
        if success:
            assert response.returncode == 0, response.stderr
        return response

    def git(self, *argv):
        return self.run(["git", *argv], "git-last", cwd=self.source)

    def advance(self):
        self.marker.write_text(self.marker.read_text().replace('UPDATE_FIXTURE = "old"', 'UPDATE_FIXTURE = "new"'), encoding="utf-8")
        self.git("add", "."); self.git("commit", "-m", "New commit without version bump")
        self.new = self.git("rev-parse", "HEAD").stdout.strip()

    def update(self):
        response = self.run([self.entry, "update"], "update")
        if os.name != "nt":
            assert f"Updated: SuperARIS 0.1.0 @ {self.new}" in response.stdout
            return {"status": "updated", "target": self.new}
        assert "installation is not complete yet" in response.stdout
        path = Path(next(line.removeprefix("Result: ") for line in response.stdout.splitlines() if line.startswith("Result: ")))
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if path.is_file():
                report = json.loads(path.read_text(encoding="utf-8"))
                shutil.copytree(path.parent, self.root / "handoff-evidence", dirs_exist_ok=True)
                assert report["status"] == "updated", report
                return report
            time.sleep(.1)
        pytest.fail(f"Update worker did not finish; inspect {path.parent}")


@pytest.mark.parametrize("manager", ["pip", "pipx"])
def test_same_version_update_check_and_original_receiver_refresh(tmp_path, monkeypatch, native_receiver_project, manager):
    if manager == "pipx" and not shutil.which("pipx"):
        pytest.skip("pipx is a CI/test tool, not a SuperARIS runtime dependency")
    installed = GitInstallation(tmp_path / "installed 中文 with spaces", manager)
    monkeypatch.setattr(receiver_cases, "ARIS", [str(installed.python), "-m", "superaris"])
    fixture = native_receiver_project
    fixture.env.update(installed.env)
    fixture.launch()
    before = receiver_cases.wait_until(lambda: receiver_cases.receiver.status(fixture.project)
                                      if receiver_cases.receiver.status(fixture.project)["receiving"] else None)
    assert before["implementation"]["revision"] == installed.old
    original = {path: path.read_bytes() for path in
                [fixture.project / "CURRENT.md", fixture.project / ".aris/workbench/launch.json"]}
    installed.advance()
    files = {str(p.relative_to(installed.prefix)): p.read_bytes() for p in installed.prefix.rglob("*") if p.is_file()}
    checked = installed.run([installed.entry, "update", "--check"], "check")
    assert installed.old in checked.stdout and installed.new in checked.stdout
    assert files == {str(p.relative_to(installed.prefix)): p.read_bytes() for p in installed.prefix.rglob("*") if p.is_file()}
    assert all(path.read_bytes() == content for path, content in original.items())
    report = installed.update()
    assert report["target"] == installed.new
    stopped = receiver_cases.wait_until(lambda: receiver_cases.receiver.status(fixture.project)
                                       if not receiver_cases.receiver.status(fixture.project)["managed_process_alive"] else None)
    assert stopped["outcome"]["reason"] == "installation_changed"
    assert stopped["implementation"]["revision"] == installed.old
    assert stopped["owner"] == before["owner"] and stopped["generation"] == before["generation"]
    assert all(path.read_bytes() == content for path, content in original.items())
    actual = installed.run([installed.python, "-c", "import superaris; print(superaris.__version__, superaris.UPDATE_FIXTURE)"], "new-code")
    assert actual.stdout.strip() == "0.1.0 new"
    refreshed = fixture.invoke("receiver", "--action", "start", "--herdr-bin", fixture.binary)
    assert refreshed["implementation"]["revision"] == installed.new and refreshed["owner"] == before["owner"]
    fixture.invoke("receiver", "--action", "stop")
    receiver_cases.wait_until(lambda: not receiver_cases.receiver.status(fixture.project)["managed_process_alive"])
    assert not any(command[:2] in (["agent", "start"], ["agent", "prompt"]) for command in fixture.commands())
    (installed.root / "RESULT.json").write_text(json.dumps({"manager": manager, "old": installed.old,
        "new": installed.new, "version": "0.1.0", "check_read_only": True,
        "original_binding_notes_preserved": True, "old_receiver": before, "stopped": stopped,
        "refreshed": refreshed, "handoff": report, "native_or_model_calls": 0}, indent=2) + "\n", encoding="utf-8")
