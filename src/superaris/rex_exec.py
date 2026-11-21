"""Process handling for Rex CLI calls and the event-stream supervisor."""
from __future__ import annotations

from collections import deque
import os
import signal
import subprocess
import sys
import threading
import time

GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}

# A caller that dies outright (a closed terminal's SIGHUP, SIGKILL) cannot clean up.
# Input calls and `rex events` (which streams until interrupted) therefore run under
# this supervisor in its own session. It reads one sized stdin payload for the CLI and
# runs nothing if the caller is already gone. It then ends the CLI's whole group (a
# --rex-bin wrapper included) once the caller's lifeline pipe closes or the CLI exits.
# A wrapper that exits while its group still runs exits 125: its status is not the CLI's.
SUPERVISE = (
    "import os, signal, subprocess, sys, threading\n"
    "group = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}\n"
    "def take(size):\n"  # Unbuffered fd reads: a blocked buffered stdin would abort interpreter exit.
    "    data = b''\n"
    "    while len(data) < size and (chunk := os.read(0, size - len(data))):\n"
    "        data += chunk\n"
    "    return data\n"
    "header = b''\n"
    "while not header.endswith(b'\\n') and (byte := os.read(0, 1)):\n"
    "    header += byte\n"
    "payload = take(int(header)) if header.endswith(b'\\n') else None\n"
    "if payload is None or len(payload) < int(header):\n"
    "    os._exit(125)\n"  # The caller is gone: run nothing.
    "guard, children = threading.Lock(), []\n"
    "def alive():\n"
    "    try:\n"
    "        os.killpg(child.pid, 0)\n"
    "        return True\n"
    "    except ProcessLookupError:\n"
    "        return False\n"
    "def stop():\n"
    "    if not children:\n"
    "        return\n"
    "    if os.name == 'nt':\n"
    "        subprocess.call(['taskkill', '/T', '/F', '/PID', str(child.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    "        return\n"
    "    try:\n"
    "        os.killpg(child.pid, signal.SIGKILL)\n"
    "    except ProcessLookupError:\n"
    "        pass\n"
    "def watch():\n"
    "    while os.read(0, 65536):\n"
    "        pass\n"
    "    with guard:\n"
    "        if children:\n"
    "            stop()\n"
    "        else:\n"
    "            children.append(None)\n"  # The caller left before launch: never start the CLI.
    "threading.Thread(target=watch, daemon=True).start()\n"
    "with guard:\n"  # A key in argv needs no stdin: launch only while the lifeline is open.
    "    if children or os.name != 'nt' and __import__('select').select([0], [], [], 0)[0] and not os.read(0, 1):\n"
    "        os._exit(125)\n"
    "    report = os.environ.pop('SUPERARIS_REX_REPORT_FD', None)\n"
    "    child = subprocess.Popen(sys.argv[1:], stdin=subprocess.PIPE, **group)\n"
    "    children.append(child)\n"
    "    if report:\n"  # Lets the caller end this CLI's group even if this supervisor hangs.
    "        os.write(int(report), str(child.pid).encode())\n"
    "        os.close(int(report))\n"
    "def feed():\n"  # After the watcher starts: a slow reader must not delay cleanup.
    "    try:\n"
    "        child.stdin.write(payload)\n"
    "        child.stdin.close()\n"
    "    except OSError:\n"
    "        pass\n"
    "threading.Thread(target=feed, daemon=True).start()\n"
    "code = child.wait()\n"
    "if os.name != 'nt' and alive():\n"
    "    sys.stderr.write('Error: the --rex-bin launcher exited before the Rex CLI it started; use the CLI or a wrapper that execs it\\n')\n"
    "    code = 125\n"
    "stop()\n"
    "sys.stderr.flush()\n"
    "os._exit(code)\n")


def supervised(argv: list[str]) -> list[str]:
    return [sys.executable, "-I", "-c", SUPERVISE, *argv]


def spawn(argv: list[str], environment: dict, hold: int | None = None, **options) -> tuple[subprocess.Popen, list]:
    """Start argv under SUPERVISE in its own session. The returned list learns the
    CLI's pid; `hold` (the caller's input-turn lock) is inherited by the supervisor."""
    cli, keep, environment = [], [], dict(environment)
    if os.name != "nt":
        report, sink = os.pipe()
        keep = [sink, *([hold] if hold is not None else [])]
        environment["SUPERARIS_REX_REPORT_FD"] = str(sink)
    process = subprocess.Popen(supervised(argv), env=environment, stdin=subprocess.PIPE, **GROUP,
                               **({"pass_fds": tuple(keep)} if keep else {}), **options)
    if os.name != "nt":
        os.close(sink)

        def learn():
            data = os.read(report, 32)
            os.close(report)
            if data:
                cli.append(int(data))
        threading.Thread(target=learn, daemon=True).start()
    return process, cli


def abandon(process: subprocess.Popen, cli: list) -> None:
    """End a supervised call: closing the lifeline makes the supervisor end its CLI.
    If the supervisor does not exit, end the CLI's group first; its still-live parent
    keeps that pid from being reused, so the lock is never released ahead of it."""
    # A writer blocked on a hung supervisor holds the stream; closing must not stall the timer.
    threading.Thread(target=_close, args=(process.stdin,), daemon=True).start()
    try:
        process.wait(2)
        return
    except subprocess.TimeoutExpired:
        pass
    if cli and os.name != "nt":
        try:
            os.killpg(cli[0], signal.SIGKILL)
        except ProcessLookupError:
            pass
    _kill_group(process)
    process.wait()


def lifeline(payload: str | None) -> str:
    """The sized payload that opens a supervisor's lifeline; keep the pipe open afterwards."""
    data = payload or ""
    return f"{len(data.encode('utf-8'))}\n{data}"


def _close(stream) -> None:
    try:
        stream.close()
    except OSError:
        pass


def _kill_group(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.call(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _group_alive(leader: int) -> bool:
    try:
        os.killpg(leader, 0)
        return True
    except ProcessLookupError:
        return False


def execute(argv: list[str], environment: dict, stdin: str | None, timeout: float,
            tail: int | None, pinned: bool = False, supervise: bool = False, hold: int | None = None) -> tuple[int, str, str]:
    """Run one CLI call in its own process group, so a timeout or an interrupt also
    ends a --rex-bin wrapper's children; `supervise` also covers the caller's own death.
    Both pipes drain concurrently; `tail` keeps only the last stdout lines (capture
    includes all scrollback), stderr a bounded tail. A pinned call cannot start a
    server, so anything left in its group after the leader exits is a wrapper's CLI
    whose real result the leader did not report. `hold` is the caller's input-turn lock
    descriptor: a supervisor inherits it, so the lock outlives a dead caller until the
    CLI it launched is gone."""
    pipes = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True, "encoding": "utf-8", "errors": "replace"}
    if supervise:
        process, cli = spawn(argv, environment, hold, **pipes)
    else:
        process, cli = subprocess.Popen(argv, env=environment, stdin=subprocess.PIPE, **GROUP, **pipes), []
    stdout, stderr = deque(maxlen=tail), [""]

    def diagnose():
        for chunk in iter(lambda: process.stderr.read(8192), ""):
            stderr[0] = (stderr[0] + chunk)[-65536:]

    def feed():
        try:
            process.stdin.write(lifeline(stdin) if supervise else stdin or "")
            process.stdin.flush()
            if not supervise:
                process.stdin.close()
        except OSError:
            pass  # The CLI exited without reading its input; its exit status reports why.
    deadline = time.monotonic() + timeout
    try:
        workers = [threading.Thread(target=target, daemon=True) for target in
                   (feed, lambda: stdout.extend(process.stdout), diagnose)]
        for worker in workers:
            worker.start()
        returncode = process.wait(timeout)
        if pinned and not supervise and os.name != "nt" and _group_alive(process.pid):
            raise OSError("the --rex-bin launcher exited before the Rex CLI it started; use the CLI or a wrapper that execs it")
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in workers):
            raise subprocess.TimeoutExpired(argv, timeout)  # A leftover child still holds the pipes.
    except BaseException:
        # Includes Ctrl-C: no paste or Enter may land after the caller stops.
        if supervise:
            abandon(process, cli)
        else:
            _kill_group(process)
            process.wait()
        raise
    _close(process.stdin)
    return returncode, "".join(stdout), stderr[0]
