"""Explicit local Rex transport over its structured API, preserving native failures.

Terminal blocks only. Ownership pins the local server instance, block host,
foreground agent process and project cwd. OSC 7501 program status counts only
when Rex attributes it to that same process. Mutations are never retried here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

from .client import HerdrError
from .rex_exec import abandon, execute, lifeline, spawn

TERMINAL = "com.superlogical.terminal.shell"
MIN_API_REVISION = 18  # Tested Rex 0.1.0-preview.21; older servers lack the methods used here.
STATUS_APPS = {"codex": "codex", "claude-code": "claude", "antigravity": "agy"}
STATES = {"idle", "working", "done", "blocked", "error"}
WAKE_EVENTS = {"program_status_changed", "program_status_removed", "child_exited"}
NOTIFY = ("import sys\nsys.stdout.write('\\x1b]777;notify;' + sys.argv[1] + ';' + sys.argv[2] + '\\x07')\n"
          "sys.stdout.flush()\n")
class RexError(HerdrError):
    def __init__(self, message: str, code: str | None = None, output: str = ""):
        super().__init__(message)
        self.code, self.output = code, output


def discover_rex(explicit: str | None = None) -> dict:
    """Find the Rex CLI without installing it or changing PATH.

    The macOS app bundles its CLI under Application Support; the Versions/Current
    link is kept unresolved so an app update does not strand a recorded path.
    """
    if explicit:
        path = Path(explicit).expanduser()
        candidate = shutil.which(explicit) or (str(path) if path.is_file() else None)
        return {"cli": os.path.abspath(candidate) if candidate else None, "source": "explicit", "requested": explicit}
    command = shutil.which("rex")
    if command:
        return {"cli": os.path.abspath(command), "source": "PATH"}
    if sys.platform == "darwin":
        bundled = (Path.home() / "Library/Application Support/com.superlogical.rex/RexServer/Versions/Current"
                   / "Rex Server.app/Contents/MacOS/rex")
        if bundled.is_file():
            return {"cli": str(bundled), "source": "bundled"}
    return {"cli": None, "source": "missing"}


def rex_missing_action(found: dict) -> str:
    if found.get("requested"):
        return f"The recorded Rex CLI is unavailable: {found['requested']}. Select a working CLI with --rex-bin, then resume this project."
    return "Install and open Rex from https://www.superlogical.com/rex/, then resume this project."


def _names(process: dict) -> set[str]:
    names = set()
    for value in (process.get("argv0"), process.get("name"), process.get("path"), process.get("invoked_path")):
        if value:
            # A self-updating CLI can keep running from a renamed file such as
            # agy.<stamp>.old; its pid, not its current file name, is the identity.
            stem = Path(value).name.lower().removesuffix(".exe").removesuffix(".cmd").split(".")[0]
            names.add(stem)
    return names


class Rex:
    host = "rex"

    input_turn_fd: int | None = None  # Set by delivery.input_turn while this client holds it.

    def __init__(self, project: Path, binary: str | None = None, bound: dict | None = None):
        self.project = Path(project).expanduser().resolve()
        self.bound = bound or {}
        if self.bound.get("execution_environment", "local") != "local":
            raise RexError("This Rex version supports the original local runtime only; no remote target was inferred")
        self.session = self.bound.get("session", "default")
        self.found = discover_rex(binary or self.bound.get("rex_bin"))
        if not self.found["cli"]:
            raise RexError(rex_missing_action(self.found))
        self.binary = self.found["cli"]
        self.server = self.bound.get("rex_server")
        self._ready = (0.0, None)

    def bind(self, current: dict) -> None:
        self.bound, self.server = current, current.get("rex_server")
        if current.get("rex_bin") and current["rex_bin"] != self.binary:
            # A recovery confirmed a new CLI entry for this same team.
            self.binary = discover_rex(current["rex_bin"])["cli"] or self.binary

    def run(self, *arguments: str, stdin: str | None = None, timeout: float = 30, tail: int | None = None,
            supervise: bool = False) -> str:
        argv = [self.binary]
        if self.server:
            # A recorded team never starts a fresh server that lacks its blocks.
            argv += ["--server", self.server, "--autostart=false"]
        argv += list(map(str, arguments))
        environment = dict(os.environ)
        environment.pop("REX_SERVER", None)  # Never follow an inherited remote route.
        try:
            returncode, stdout, stderr = execute(argv, environment, stdin, timeout, tail, pinned=bool(self.server),
                                              supervise=supervise, hold=self.input_turn_fd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RexError(f"Rex result unknown; inspect the original session before retrying: {exc}") from exc
        if returncode:
            message = (stderr or stdout).strip() or f"Rex exit {returncode}"
            code = re.search(r"\bcode=([a-z_]+)", message)
            # API errors carry Rex's own code; only plain CLI commands report a bare "not found".
            raise RexError(message, code.group(1) if code else (
                "not_found" if arguments[0] != "api" and "not found" in message else None), stdout)
        return stdout

    def api(self, method: str, args: dict | None = None, timeout: float = 30, supervise: bool = False) -> dict:
        output = self.run("api", "call", method, "-", stdin=json.dumps(args or {}), timeout=timeout, supervise=supervise)
        try:
            return json.loads(output) if output.strip() else {}
        except json.JSONDecodeError as exc:
            raise RexError(f"Rex {method} did not return JSON; use the official Rex CLI") from exc

    def block(self, method: str, handle: str, session: str, args: dict | None = None) -> dict:
        return self.api("block.method", {"session_id": session, "block_id": handle, "method": method, "args": args or {}})

    def ensure_ready(self, *, new: bool = False) -> dict:
        observed, info = self._ready
        if new or info is None or time.monotonic() - observed > 1:
            # One identity read per reconciliation; a restarted server also loses the blocks themselves.
            try:
                info = json.loads(self.run("whoami", "--json"))
            except json.JSONDecodeError as exc:
                raise RexError("The selected command did not return Rex JSON. Use the official Rex CLI; no fallback host was started.") from exc
            self._ready = (time.monotonic(), info)
        if (info.get("api_revision") or 0) < MIN_API_REVISION:
            raise RexError(f"Rex API revision {info.get('api_revision')} predates the tested revision {MIN_API_REVISION}; update Rex, then resume")
        if not info.get("instance_id") or not info.get("host_id") or not info.get("endpoint"):
            raise RexError("Rex did not report its server identity; no team was started")
        if not new and self.bound.get("rex_instance") and self.bound["rex_instance"] != info["instance_id"]:
            raise RexError("Original Rex server instance changed; its blocks are gone. Inspect the original team before rebinding")
        return info

    def session_of(self, handle: str) -> str:
        for role in self.bound.get("roles", {}).values():
            if role.get("pane_id") == handle and role.get("rex_session"):
                return role["rex_session"]
        result = self.api("target.resolve", {"kinds": ["block"], "queries": [handle]})["results"][0]
        target = result.get("target") or {}
        if result.get("status") != "resolved" or target.get("block_id") != handle:
            raise RexError(f"Rex block {handle} is not an exact existing block ID")
        return target["session_id"]

    def _records(self, handle: str, session: str) -> list[dict]:
        return self.block("program_status", handle, session).get("records", [])

    def _agent(self, process: dict, records: list[dict]) -> dict:
        """The one recognizable agent among the foreground process and its ancestors."""
        reported = {(record.get("owner") or {}).get("pid"): STATUS_APPS.get(record.get("effective_app"))
                    for record in records if not record.get("id")}
        foreground = process.get("foreground")
        matches = []
        for item in [foreground, *process.get("ancestors", [])] if foreground else []:
            kinds = _names(item) & set(STATUS_APPS.values())
            kind = next(iter(kinds)) if len(kinds) == 1 else reported.get(item.get("pid"))
            if kind and item.get("pid") and item.get("cwd"):
                matches.append({"kind": kind, "pid": item["pid"], "cwd": str(Path(item["cwd"]).resolve())})
        if len(matches) != 1:
            raise RexError("Expected one recognizable foreground agent; inspect the actual block before sending input",
                           "agent_not_observed")
        return matches[0]

    @staticmethod
    def _state(records: list[dict], pid: int) -> tuple[str, dict | None]:
        root = next((record for record in records if not record.get("id")), None)
        if not root or (root.get("owner") or {}).get("pid") != pid:
            return "unknown", None  # No report, or one left by an earlier process.
        return (root["state"] if root.get("state") in STATES else "unknown"), root

    def describe(self, handle: str, session: str | None = None) -> dict:
        session = session or self.session_of(handle)
        process = self.block("process", handle, session)
        return {"pane_id": handle, "rex_session": session, **self._agent(process, self._records(handle, session))}

    def snapshot(self) -> dict:
        """Agents in this team's sessions. Recorded role blocks keep their recorded
        harness here; every caller verifies ownership before using one. Other
        blocks are probed only while no main owner is bound."""
        self.ensure_ready()
        roles = self.bound.get("roles", {})
        recorded = {role.get("pane_id"): role.get("harness") for role in roles.values()}
        sessions = [self.bound.get("rex_session"), *(role.get("rex_session") for role in self.bound.get("roles", {}).values())]
        agents = []
        for session in dict.fromkeys(value for value in sessions if value):
            try:
                blocks = self.api("session.list_blocks", {"session_id": session})["blocks"]
            except RexError as exc:
                if exc.code in {"session_not_found", "not_found"}:
                    continue
                raise
            for block in blocks:
                if block.get("creator_name") != "com.superlogical.terminal":
                    continue
                kind = recorded.get(block["block_id"])
                if not kind and roles.get("main"):
                    continue
                if not kind:
                    try:
                        kind = self.describe(block["block_id"], session)["kind"]
                    except RexError:
                        continue
                agents.append({"pane_id": block["block_id"], "agent": kind, "name": block.get("label"),
                               "rex_session": session})
        return {"agents": agents}

    def verify_owner(self, role: dict, project: Path) -> dict:
        if not role.get("pane_id"):
            raise RexError("Original Rex launch outcome is unknown; inspect its session before recovering this role")
        info = self.ensure_ready()
        if role.get("runtime_id") and role["runtime_id"] != info["instance_id"]:
            raise RexError("Original Rex server instance changed; inspect the original owner before rebinding")
        handle = role["pane_id"]
        session = role.get("rex_session") or self.session_of(handle)
        try:
            blocks = self.api("session.list_blocks", {"session_id": session})["blocks"]
        except RexError as exc:
            raise RexError(f"Original Rex session is unavailable: {exc}", exc.code) from exc
        block = next((item for item in blocks if item.get("block_id") == handle), None)
        if not block:
            raise RexError("Recorded Rex block is absent from its original session")
        if block.get("host_id") != info["host_id"] or role.get("execution_host") not in (None, block["host_id"]):
            raise RexError("Rex block is not on the original local host; no remote target was inferred")
        records = self._records(handle, session)
        process = self.block("process", handle, session)
        agent = self._agent(process, records)
        if agent["kind"] != role["harness"]:
            raise RexError("Recorded block occupant changed; explicit owner handoff is required")
        if Path(agent["cwd"]) != Path(project).resolve():
            raise RexError(f"Owner effective cwd mismatch: {agent['cwd']} != {project}")
        if role.get("pid") and role["pid"] != agent["pid"]:
            raise RexError("Foreground process changed; inspect ownership before rebinding")
        # An ancestor match keeps the identity alive while the agent runs a child,
        # but only the agent itself holding the foreground may receive input.
        holds_input = (process.get("foreground") or {}).get("pid") == agent["pid"]
        status = self._state(records, agent["pid"])[0] if holds_input else "unknown"
        return {**role, **agent, "host": "rex", "rex_session": session, "runtime_id": info["instance_id"],
                "execution_host": block["host_id"], "status": status, "name": block.get("label", role.get("name"))}

    def wait_owner(self, role: dict, project: Path, timeout: float = 30) -> dict:
        """Wait only for a new block's agent to appear; never launch or send again."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.verify_owner(role, project)
            except RexError as exc:
                if exc.code != "agent_not_observed" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)

    def launch_agent(self, current: dict, placement, command: list[str], label: str, *,
                     session_label: str, window_label: str) -> dict:
        """One atomic create call. A lost reply is an unknown outcome, not a retry.
        Supervised: the command may carry a role's first packet, so it never starts after the launcher dies."""
        options = {"command": command, "cwd": str(self.project)}
        if Path(command[0]).is_absolute():
            # Node-based CLIs find their interpreter beside the resolved entry.
            options["path_prepend"] = [str(Path(command[0]).parent)]
        layout = {"block": {"flavor": TERMINAL, "label": label, "options": options}}
        if placement is None:
            created = self.api("session.create", {"label": session_label,
                                                  "initial_windows": [{"window_label": window_label, "layout": layout}]},
                               supervise=True)
            window = created["initial_windows"][0]
            current.update(rex_session=created["session_id"], rex_window=window["window_id"])
            return {"pane_id": window["block_ids"][0], "rex_session": created["session_id"]}
        session = current["rex_session"]
        if placement == "tab":
            created = self.api("session.new_window", {"session_id": session, "window_label": label,
                                                      "layout": layout, "focus": False}, supervise=True)
        else:
            anchor, direction = placement
            try:
                created = self.api("session.new_split", {"session_id": session, "anchor_id": anchor, "side": "after",
                                                         "direction": "vertical" if direction == "down" else "horizontal",
                                                         "layout": layout, "focus": False}, supervise=True)
            except RexError as exc:
                main = (current["roles"].get("main") or {}).get("pane_id")
                if exc.code != "not_found" or exc.output.strip() or not main or anchor == main:
                    raise
                # Rex's own not_found with no creation receipt: the closed anchor created nothing.
                return self.launch_agent(current, (main, "right"), command, label,
                                         session_label=session_label, window_label=window_label)
        return {"pane_id": created["block_ids"][0], "rex_session": session}

    def read_screen(self, handle: str) -> str:
        session = self.session_of(handle)
        rows = self.block("size", handle, session).get("rows") or 24
        # Capture includes all scrollback; the composer guard needs only the visible rows.
        return "\n".join(self.run("capture", "-s", session, "-b", handle, tail=rows).splitlines())

    def _holds_input(self, handle: str, session: str, owner: dict) -> list[dict]:
        # Status brackets the foreground read: a child taking the terminal during the first
        # status query, or a prompt opening during the process query, is seen either way.
        records = self._records(handle, session)
        process = self.block("process", handle, session)
        agent = self._agent(process, records)
        if (agent["pid"] != owner["pid"] or agent["kind"] != owner["harness"]
                or owner.get("cwd") and agent["cwd"] != owner["cwd"]):
            raise RexError("The verified agent no longer holds this block's input; inspect it before any resend",
                           "owner_changed")
        if (process.get("foreground") or {}).get("pid") != agent["pid"]:
            # The same agent handed its terminal to a child (an editor, a pager) for now.
            raise RexError("The verified agent does not hold this block's input right now", "not_ready")
        records = self._records(handle, session)
        state, _ = self._state(records, agent["pid"])
        if state not in {"idle", "done"}:
            # A permission prompt may have opened since verification; Enter would answer it.
            raise RexError(f"The verified agent is {state}, not waiting for a prompt; inspect it before any resend",
                           "not_ready")
        return records

    def send_prompt(self, handle: str, text: str, owner: dict, settle: float = 0.3, timeout: float = 10) -> dict:
        """Paste, press Enter, then require the verified agent to report a new turn.
        The caller holds delivery.input_turn from its composer read through this return."""
        session = owner.get("rex_session") or self.session_of(handle)
        try:
            self._holds_input(handle, session, owner)
        except RexError as exc:
            if exc.code != "not_ready":
                raise
            raise RexError(f"{exc}; no input was sent", "not_sent") from exc
        pid = owner["pid"]
        # Input runs supervised: it cannot land after this caller dies with the lock released.
        self.api("block.event", {"session_id": session, "block_id": handle,
                                 "event": {"type": "paste", "payload": {"text": text}}}, supervise=True)
        time.sleep(settle)  # Let the bracketed paste land before its separate Enter.
        try:
            records = self._holds_input(handle, session, owner)
        except RexError as exc:
            raise RexError(f"{exc}. The prompt was pasted but Enter was not sent.", "unconfirmed") from exc
        _, before = self._state(records, pid)
        self.run("send-key", "-s", session, "-b", handle, "enter", supervise=True)
        deadline = time.monotonic() + timeout
        while True:
            state, record = self._state(self._records(handle, session), pid)
            if record and record.get("updated_at") != (before or {}).get("updated_at"):
                if state in {"working", "done"}:
                    return {"accepted": True, "pid": pid, "state": state, "updated_at": record["updated_at"],
                            "block_id": handle, "rex_session": session}
                if state in {"blocked", "error"}:
                    # Enter may have answered a prompt rather than submitted this turn.
                    raise RexError(f"The agent reported {state} right after Enter; inspect its block before any resend",
                                   "unconfirmed")
            if time.monotonic() >= deadline:
                raise RexError("Rex did not observe the agent start the submitted turn; inspect its block before any resend",
                               "unconfirmed")
            time.sleep(0.2)

    def notice(self, title: str, text: str) -> dict:
        from .context import _within
        from .state import directory
        main = self.bound.get("roles", {}).get("main", {})
        session = main.get("rex_session") or self.bound.get("rex_session")
        if not session:
            raise RexError("Original Rex session is unavailable; no notification target was inferred")
        path = directory(self.project) / "NOTICES.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path = _within(path, self.project, "Notice file")
        except ValueError as exc:
            raise RexError(f"{exc}; no notice was written") from exc
        receipt = {"notice_file": str(path), "rex_session": session}
        # The file is the durable notice; the desktop alert only points to it.
        with path.open("a", encoding="utf-8") as output:
            output.write(f"\n## {title}\n\n{text}\n")
        try:
            return {**receipt, "notifier_block": self._alert(session, title, text)}
        except RexError as exc:  # The notice is already durable; no input was sent.
            return {**receipt, "alert_error": str(exc)}

    def _alert(self, session: str, title: str, text: str) -> str:
        def clean(value: str, limit: int) -> str:
            return " ".join(re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value).split())[:limit]

        created = self.api("session.new_block", {"session_id": session, "flavor": TERMINAL, "label": "SuperARIS notice",
                                                 "options": {"shell": "none", "cwd": str(self.project),
                                                             "command": [sys.executable, "-I", "-c", NOTIFY,
                                                                         clean(title, 80).replace(";", ","),
                                                                         clean(text, 240)]}})
        notifier = created["block_id"]
        deadline, ended = time.monotonic() + 5, None
        try:
            while time.monotonic() < deadline and (ended := self.block("process", notifier, session).get("last_exit")) is None:
                time.sleep(0.1)
        finally:
            try:
                # A detached block can outlive its program; close this one-shot alert in any case.
                self.run("block", "close", "-s", session, notifier)
            except RexError as exc:
                if exc.code != "not_found" and ended is not None:
                    raise
        if (ended or {}).get("exit_code") != 0:
            raise RexError(f"Desktop alert did not complete: {ended or 'no exit within 5 s'}")
        return notifier

    def open_ui(self, handle: str | None = None) -> dict:
        self.ensure_ready()
        main = self.bound.get("roles", {}).get("main", {})
        session = self.session_of(handle) if handle else main.get("rex_session") or self.bound.get("rex_session")
        if handle:
            self.api("session.focus_block", {"session_id": session, "block_id": handle})
        apps = [item for item in self.api("client.list").get("clients", []) if (item.get("info") or {}).get("kind") == "app"]
        if len(apps) != 1:
            return {"selected": False, "rex_session": session, "reason": f"{len(apps)} Rex apps are connected"}
        try:
            self.run("-C", apps[0]["client_id"], "do", "session.select", f"session_id={session}")
        except RexError as exc:  # Remote Control may be off; the user's setting is respected.
            return {"selected": False, "rex_session": session, "reason": str(exc)}
        return {"selected": True, "rex_session": session}

    def events(self, subscriptions: list[dict], timeout: float = 5):
        """Translate Rex block events into the bridge's existing wake-up signal."""
        panes = {item["pane_id"] for item in subscriptions}
        if not panes:
            time.sleep(max(0, timeout))
            return
        lines: queue.Queue = queue.Queue()
        processes = []
        argv = [self.binary, *(["--server", self.server, "--autostart=false"] if self.server else [])]
        environment = {key: value for key, value in os.environ.items() if key != "REX_SERVER"}
        try:
            for session in dict.fromkeys(self.session_of(pane) for pane in panes):
                # Supervised in its own session: a terminal hangup cannot kill it before it ends the stream.
                process, cli = spawn([*argv, "events", "-s", session, "--json"], environment, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
                processes.append((process, cli))
                process.stdin.write(lifeline(None))
                process.stdin.flush()
                threading.Thread(target=lambda stream=process.stdout: [*map(lines.put, stream), lines.put(None)],
                                 daemon=True).start()
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    line = lines.get(timeout=remaining)
                except queue.Empty:
                    return
                if line is None:
                    raise RexError("Rex event stream closed; refresh the snapshot before resubscribing")
                event = (json.loads(line).get("payload") or {}).get("event") or {}
                payload = event.get("payload") or {}
                if (event.get("type") == "block_event" and payload.get("block_id") in panes
                        and payload.get("name") in WAKE_EVENTS):
                    yield {"type": "pane.agent_status_changed", "pane_id": payload["block_id"]}
        finally:
            for process, cli in processes:
                abandon(process, cli)  # Closing the lifeline stops the stream.
