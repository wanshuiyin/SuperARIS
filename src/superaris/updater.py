"""Update this installed environment through its package manager, not project state."""
from __future__ import annotations

from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


REPOSITORY = "https://github.com/wanshuiyin/SuperARIS.git"
_PROBE = """import importlib.metadata as m,json,sys
d=m.distribution('superaris')
u=json.loads(d.read_text('direct_url.json') or '{}')
print(json.dumps({'version':d.version,'revision':u.get('vcs_info',{}).get('commit_id'),
                  'prefix':sys.prefix,'source':u.get('url')}))
"""


def installed_revision() -> str | None:
    try:
        direct = json.loads(metadata.distribution("superaris").read_text("direct_url.json") or "{}")
        return direct.get("vcs_info", {}).get("commit_id")
    except (metadata.PackageNotFoundError, ValueError, OSError):
        return None


def installation() -> dict:
    try:
        dist = metadata.distribution("superaris")
    except metadata.PackageNotFoundError as exc:
        raise ValueError("This is a source launcher, not an installed SuperARIS. Use the documented pipx or venv Git installation; source files were not changed.") from exc
    prefix = Path(sys.prefix).resolve()
    module = Path(__file__).resolve().parent
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    if (sys.prefix == sys.base_prefix or not module.is_relative_to(prefix)
            or module != Path(dist.locate_file("superaris")).resolve() or "dir_info" in direct):
        raise ValueError("Source/editable or global installations are not self-updated. Keep local changes and update with the original installer in its own virtual environment.")
    source = direct.get("url")
    if direct.get("vcs_info") and str(source).rstrip("/").removesuffix(".git").lower() != REPOSITORY.removesuffix(".git").lower():
        raise ValueError("This installation uses a different Git source; use its original installer. No source was switched.")
    if not direct.get("vcs_info") and not any(
            value.partition(",")[2].strip().rstrip("/").removesuffix(".git").lower() == REPOSITORY.removesuffix(".git").lower()
            for value in dist.metadata.get_all("Project-URL", [])):
        raise ValueError("Cannot identify this package as the official SuperARIS distribution; use its original installer.")
    pipx_file = prefix / "pipx_metadata.json"
    manager = "pipx" if pipx_file.is_file() else "pip"
    if pipx_file.is_file():
        record = json.loads(pipx_file.read_text(encoding="utf-8"))
        main = record.get("main_package", {})
        if main.get("package") != "superaris" or prefix.name != "superaris" or prefix.parent.name != "venvs":
            raise ValueError("This is an injected or custom-named pipx environment; manage it with its original pipx command. No other environment was selected.")
        if main.get("pinned") or record.get("pinned"):
            raise ValueError("This pipx installation is pinned. Explicitly unpin it with pipx before updating.")
        if main.get("lock_file"):
            raise ValueError("This pipx installation uses a lock file; update it through its original lock workflow.")
    return {"manager": manager, "prefix": str(prefix), "python": sys.executable,
            "version": dist.version, "revision": direct.get("vcs_info", {}).get("commit_id")}


def latest_revision() -> str:
    try:
        result = subprocess.run(["git", "ls-remote", REPOSITORY, "refs/heads/main"],
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                                capture_output=True, text=True, encoding="utf-8", timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Official SuperARIS check timed out; no update attempted") from exc
    if result.returncode:
        raise RuntimeError("Cannot check official SuperARIS main: " + result.stderr.strip())
    fields = result.stdout.split()
    if len(fields) != 2 or fields[1] != "refs/heads/main" or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise RuntimeError("Official Git source did not return a main commit; no update attempted")
    return fields[0]


def invoked_entry() -> Path:
    entry = Path(sys.argv[0]).absolute()
    # distlib's Windows console script strips .exe from argv[0].
    if os.name == "nt" and entry.name.lower() == "superaris" and entry.with_suffix(".exe").is_file():
        return entry.with_suffix(".exe")
    return entry


def install_command(current: dict, target: str) -> tuple[list[str], dict]:
    spec = f"superaris @ git+{REPOSITORY}@{target}"
    if current["manager"] == "pip":
        return [current["python"], "-m", "pip", "install", "--upgrade", "--force-reinstall", spec], {}
    executable = shutil.which("pipx")
    if not executable:
        raise ValueError("pipx manages this installation but is not on PATH. Make the original pipx command available, then retry; no environment was changed.")
    prefix = Path(current["prefix"])
    entry_name = "superaris.exe" if os.name == "nt" else "superaris"
    expected = prefix / ("Scripts" if os.name == "nt" else "bin") / entry_name
    invoked = invoked_entry()
    paths = [invoked, Path(shutil.which("superaris") or sys.argv[0]).absolute()]
    entry = next((path for path in paths if path.name.lower() == entry_name and path.is_file()
                  and not path.parent.resolve().is_relative_to(prefix) and
                  (path.resolve() == expected.resolve() or (os.name == "nt" and path == invoked))), None)
    if entry is None:
        raise ValueError("Run update through this installation's original pipx-exposed superaris entry so its command directory can be preserved.")
    environment = {"PIPX_HOME": str(prefix.parent.parent), "PIPX_BIN_DIR": str(entry.parent)}
    try:
        help_result = subprocess.run([executable, "install", "--help"], capture_output=True,
                                     text=True, encoding="utf-8", timeout=15,
                                     env={**os.environ, **environment})
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Cannot inspect the original pipx command; no update attempted") from exc
    if help_result.returncode or not re.search(r"--upgrade(?=[\s\]])", help_result.stdout):
        raise ValueError("This updater needs pipx install --upgrade. Update pipx with its original installer, or stop receiving and use the documented one-time bootstrap command.")
    return [executable, "install", "--upgrade", "--pip-args=--force-reinstall", spec], environment


def update(check: bool = False) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    current = installation()
    target = latest_revision()
    print(f"SuperARIS {current['version']} @ {current['revision'] or 'unknown revision'}", flush=True)
    print(f"Installation: {current['manager']} — {current['prefix']}", flush=True)
    print(f"Official main: {target}", flush=True)
    if current["revision"] == target:
        print("Already current.", flush=True)
        return 0
    if check:
        print("Update available. Run superaris update to install it.", flush=True)
        return 0
    command, environment = install_command(current, target)
    work = Path(tempfile.mkdtemp(prefix="superaris-update-"))
    worker = work / "update_worker.py"
    shutil.copyfile(__file__, worker)
    job = {"old": current, "target": target, "command": command, "environment": environment,
           "parent_pid": os.getpid(), "launcher_pid": os.getppid(),
           "launcher": str(invoked_entry()), "wait_for_exit": os.name == "nt"}
    (work / "job.json").write_text(json.dumps(job), encoding="utf-8")
    python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    argv = [python, "-X", "utf8", str(worker), "--worker", str(work / "job.json")]
    if os.name == "nt":
        with (work / "update.log").open("ab") as log:
            subprocess.Popen(argv, cwd=work, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        print("Update handed off; installation is not complete yet. The worker waits for this launcher to exit.")
        print(f"Result: {work / 'result.json'}\nLog: {work / 'update.log'}", flush=True)
        return 0
    # Move outside the environment being updated. The worker's real exit status
    # becomes the shell command's result, without importing replaced modules.
    os.execv(python, argv)
    return 1


def _wait_windows_exit(pid: int, expected_image: str | None = None) -> None:
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # Parent has already exited.
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if expected_image:
            kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            buffer, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            if Path(buffer.value).resolve() != Path(expected_image).resolve():
                return  # A shell/python -m caller is not the console launcher.
        if kernel.WaitForSingleObject(handle, 30000) != 0:
            raise RuntimeError("Original update launcher did not exit; no installation attempted")
    finally:
        kernel.CloseHandle(handle)


def _worker(job_path: Path) -> int:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    result = {"old": job["old"], "target": job["target"], "status": "failed", "exit_code": 1}
    try:
        if job["wait_for_exit"]:
            _wait_windows_exit(job["parent_pid"])
            if Path(job["launcher"]).name.lower() == "superaris.exe":
                _wait_windows_exit(job["launcher_pid"], job["launcher"])
        print(f"Installing official commit {job['target']}…", flush=True)
        installed = subprocess.run(job["command"], cwd=job_path.parent,
                                   env={**os.environ, **job["environment"], "GIT_TERMINAL_PROMPT": "0"})
        if installed.returncode:
            raise RuntimeError(f"Package manager exited {installed.returncode}; no successful upgrade claimed")
        probe = subprocess.run([job["old"]["python"], "-c", _PROBE], capture_output=True,
                               text=True, encoding="utf-8", check=True)
        after = json.loads(probe.stdout)
        result["installed"] = after
        if after["revision"] != job["target"] or Path(after["prefix"]).resolve() != Path(job["old"]["prefix"]).resolve():
            raise RuntimeError("Installed revision/environment did not match the requested update")
        result.update(status="updated", exit_code=0)
        print(f"Updated: SuperARIS {after['version']} @ {after['revision']}", flush=True)
        print("Existing agent sessions are unchanged. Refresh project receiving explicitly:", flush=True)
        print('  superaris receiver "PROJECT" --action stop\n  superaris receiver "PROJECT" --action status\n  # Once stopped:\n  superaris receiver "PROJECT" --action start', flush=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
        print(f"Update failed: {exc}", file=sys.stderr, flush=True)
    (job_path.parent / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(_worker(Path(sys.argv[2])))
