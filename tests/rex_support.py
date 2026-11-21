"""File-backed fake Rex CLI shaped like 0.1.0-preview.21 (API revision 18).

Blocks started with an agent command get a foreground process named after that
command and, unless disabled, an OSC 7501 status record owned by that process.
No native Rex server, terminal or model is involved.
"""
from contextlib import contextmanager
import inspect
import json
import os
from pathlib import Path
import threading
import time

from tests.test_windows_runtime import executable


def acquire(lock: str) -> None:
    """A directory lock serializes state changes across fake CLI and test processes."""
    deadline = time.monotonic() + 10
    while True:
        try:
            os.mkdir(lock)
            return
        except FileExistsError:
            if time.monotonic() > deadline:
                raise SystemExit("fake Rex state lock timed out")
            time.sleep(0.005)


FAKE_REX = r'''
import atexit, json, os, sys, time
from pathlib import Path

''' + inspect.getsource(acquire) + r'''
state_path = Path(os.environ["SUPERARIS_REX_STATE"])
args = sys.argv[1:]
entry = {"argv": args, "rex_server_env": os.environ.get("REX_SERVER")}
if args[-1:] == ["-"]:
    entry["input"] = json.loads(sys.stdin.read())
with open(os.environ["SUPERARIS_REX_COMMANDS"], "a", encoding="utf-8") as log:
    log.write(json.dumps(entry) + "\n")
server = client = None
while args and args[0] in ("--server", "--autostart=false", "-C"):
    if args[0] == "--server":
        server = args[1]; args = args[2:]
    elif args[0] == "-C":
        client = args[1]; args = args[2:]
    else:
        args = args[1:]
MUTATING = {"session.create", "session.new_split", "session.new_window", "session.new_block", "block.event", "session.focus_block"}
if args[:1] in (["send-key"], ["do"]) or args[:2] == ["block", "close"] or args[:2] == ["api", "call"] and args[2] in MUTATING:
    lock = str(state_path) + ".lock"
    acquire(lock)
    atexit.register(os.rmdir, lock)
state = json.loads(state_path.read_text(encoding="utf-8"))  # Reads never write a snapshot back.
if server is not None and server != state["server"]["endpoint"]:
    sys.exit("Error: connect: no such server " + server)
if not state.get("available", True):
    sys.exit("Error: server is not running (status=503 code=unavailable)")

def save():
    temporary = state_path.with_name(f".{state_path.name}.{os.getpid()}.replacement")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(state_path)

def fail(message, code):
    sys.exit(f"Error: {message} (status=404 code={code})")

def tick():
    state["clock"] += 1
    return "2026-11-21T12:00:%02d.000000+08:00" % state["clock"]

def start_block(session, label, options, placement="placed"):
    state["counter"] += 1
    block = f"block:{state['counter']:04d}"
    command = options.get("command") or []
    record = {"session": session, "label": label, "host_id": state["server"]["host_id"], "placement": placement,
              "options": options, "records": [], "draft": "", "submitted": []}
    kind = Path(command[0]).name.split(".")[0] if command else "zsh"
    pid = 1000 + state["counter"]
    record["process"] = {"last_exit": {"exit_code": state.get("alert_exit", 0)} if placement == "detached" else None,
        "foreground": {"pid": pid, "name": kind, "argv0": command[0] if command else "-zsh",
                       "path": command[0] if command else "/bin/zsh", "cwd": options.get("cwd") or state["home"]},
        "ancestors": [{"pid": pid - 500, "name": "zsh", "argv0": "-zsh", "path": "/bin/zsh", "cwd": options.get("cwd")}]}
    app = {"codex": "codex", "claude": "claude-code", "agy": "antigravity"}.get(kind)
    if app and state.get("report_status", True):
        record["records"] = [{"state": "idle", "app": app, "effective_app": app, "updated_at": tick(),
                              "owner": {"pid": pid, "name": kind}}]
    state["blocks"][block] = record
    state["sessions"].setdefault(session, {"label": session})
    return block

def node_layout(layout):
    node = layout["block"]
    return node["label"], node.get("options", {})

def find(session, block):
    if session not in state["sessions"]:
        fail(f'session "{session}" not found', "session_not_found")
    record = state["blocks"].get(block)
    if not record or record["session"] != session:
        fail(f'block target "{block}" not found', "not_found")
    return record

def report(record, value, **extra):
    owner = record["process"]["foreground"]
    app = {"codex": "codex", "claude": "claude-code", "agy": "antigravity"}.get(owner["name"].split(".")[0])
    record["records"] = [{"state": value, "app": app, "effective_app": app, "updated_at": tick(),
                          "owner": {"pid": owner["pid"], "name": owner["name"]}, **extra}]

def output(value):
    print(json.dumps(value))

if args == ["whoami", "--json"]:
    if state.get("json", True):
        output({**state["server"], "rex_version": "0.1.0-preview.21"})
    else:
        print("plain text")
elif args[:2] == ["api", "call"]:
    method, value = args[2], entry.get("input", {})
    if state.get("fail_method") == method:
        sys.exit("Error: stream response failed: lost reply (status=500 code=internal)")
    if method == "session.create":
        state["counter"] += 1
        session = f"session:{state['counter']:04d}"
        state["sessions"][session] = {"label": value["label"]}
        window = value["initial_windows"][0]
        block = start_block(session, *node_layout(window["layout"]))
        output({"session_id": session, "initial_windows": [{"window_id": f"window:{session}", "block_ids": [block], "revision": 1}]})
    elif method in ("session.new_split", "session.new_window"):
        if method == "session.new_split":
            find(value["session_id"], value["anchor_id"])
        block = start_block(value["session_id"], *node_layout(value["layout"]))
        output({"block_ids": [block], "revision": 2})
        if state.get("wrapper_fails_after_create"):
            save()  # A --rex-bin wrapper's own later step fails after Rex created the block.
            sys.exit(state["wrapper_fails_after_create"])
    elif method == "session.new_block":
        block = start_block(value["session_id"], value["label"], value["options"], "detached")
        output({"block_id": block, "revision": 3})
    elif method == "session.list_blocks":
        if value["session_id"] not in state["sessions"]:
            fail(f'session "{value["session_id"]}" not found', "session_not_found")
        output({"blocks": [{"block_id": block, "label": record["label"], "creator_name": "com.superlogical.terminal",
                            "flavor": "com.superlogical.terminal.shell", "host_id": record["host_id"],
                            "placement": record["placement"]}
                           for block, record in sorted(state["blocks"].items()) if record["session"] == value["session_id"]]})
    elif method == "block.method":
        record = find(value["session_id"], value["block_id"])
        if record["placement"] == "detached" and state.get("fail_notifier_query"):
            sys.exit("Error: stream response failed: lost reply (status=500 code=internal)")
        if value["method"] == "process":
            output(record["process"])
            if state.get("prompt_during_process") and record["draft"]:
                report(record, "blocked")  # A slow process query: a permission prompt opens meanwhile.
                state.pop("prompt_during_process")
                save()
        elif value["method"] == "program_status":
            output({"records": record["records"]})
            if state.get("child_during_status") and record["draft"]:
                # A slow status query: the agent hands its terminal to a pager meanwhile.
                process = record["process"]
                process["ancestors"].insert(0, process["foreground"])
                process["foreground"] = {"pid": 8888, "name": "less", "argv0": "less", "path": "/usr/bin/less",
                                         "cwd": process["foreground"]["cwd"]}
                state.pop("child_during_status")
                save()
        elif value["method"] == "size":
            output({"columns": 80, "rows": state.get("rows", 24)})
        else:
            sys.exit("Unexpected block method " + value["method"])
    elif method == "block.event":
        record = find(value["session_id"], value["block_id"])
        assert value["event"]["type"] == "paste", value
        record["draft"] += value["event"]["payload"]["text"]
        if state.get("replace_on_paste"):
            record["process"]["foreground"]["pid"] = state["replace_on_paste"]
        if record["process"]["foreground"]["name"] == "codex" and record["records"]:
            report(record, "idle")  # Codex reports its composer becoming active.
        if state.get("state_on_paste"):
            report(record, state["state_on_paste"])  # e.g. a permission prompt opening meanwhile.
    elif method == "target.resolve":
        block = value["queries"][0]
        record = state["blocks"].get(block)
        output({"results": [{"query": block, "status": "resolved", "target": {
            "kind": "block", "session_id": record["session"], "block_id": block}} if record else
            {"query": block, "status": "not_found"}]})
    elif method == "session.focus_block":
        find(value["session_id"], value["block_id"])
        state["focused"] = value["block_id"]
        output({})
    elif method == "client.list":
        output({"clients": state.get("clients", [])})
    else:
        sys.exit("Unexpected fake Rex method: " + method)
    if method in MUTATING:
        save()
elif args[0] == "send-key":
    record = find(args[2], args[4])
    assert args[5:] == ["enter"], args
    if state.get("fail_method") == "send-key":
        sys.exit("Error: stream response failed: lost reply (status=500 code=internal)")
    record["submitted"].append(record["draft"])
    record["draft"] = ""
    if state.get("turns", True):
        report(record, state.get("after_enter", "working"))
    save()
elif args[0] == "capture":
    record = find(args[2], args[4])
    composer = "› " + record["draft"].splitlines()[0] if record["draft"] else "› Ask Codex to do anything"
    screen = record.get("screen") or state.get("screen") or ["", composer, ""]  # A pasted draft shows until Enter.
    print("\n".join(screen))
elif args[:2] == ["block", "close"]:
    find(args[3], args[4])
    del state["blocks"][args[4]]
    save()
elif args[0] == "do":
    if not state.get("remote_control", True):
        sys.exit("Error: client refused: Remote Control is off (status=403 code=forbidden)")
    state["selected"] = [client, args[2]]
    save()
elif args[0] == "events":
    if state.get("events_pid"):
        Path(state["events_pid"]).write_text(str(os.getpid()), encoding="utf-8")
    for line in state.get("events", {}).get(args[2], []):
        print(json.dumps(line), flush=True)
    time.sleep(float(state.get("events_hold", 30)))
else:
    sys.exit("Unexpected fake Rex command: " + repr(args))
'''


class FakeRex:
    def __init__(self, folder: Path, project: Path, **state):
        self.folder, self.project = folder, project
        self.state_path = folder / "rex-state.json"
        self.commands_path = folder / "rex-commands.jsonl"
        self.binary = executable(folder / "rex", FAKE_REX)
        self.write({"server": {"endpoint": "unix:///fake/rex.sock", "instance_id": "instance-original",
                               "host_id": "host-local", "api_revision": 18},
                    "home": str(folder), "clock": 0, "counter": 0, "sessions": {}, "blocks": {}, **state})
        self.env = {"SUPERARIS_REX_STATE": str(self.state_path), "SUPERARIS_REX_COMMANDS": str(self.commands_path)}

    def read(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    @contextmanager
    def locked(self):
        lock = str(self.state_path) + ".lock"
        acquire(lock)
        try:
            yield
        finally:
            os.rmdir(lock)

    def _replace(self, value: dict) -> None:
        temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.{threading.get_ident()}.replacement")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(self.state_path)

    def write(self, value: dict) -> None:
        with self.locked():
            self._replace(value)

    def update(self, change) -> None:
        with self.locked():
            value = self.read()
            change(value)
            self._replace(value)

    def commands(self) -> list[dict]:
        if not self.commands_path.exists():
            return []
        return [json.loads(line) for line in self.commands_path.read_text(encoding="utf-8").splitlines()]

    def calls(self, method: str) -> list[dict]:
        return [entry["input"] for entry in self.commands() if entry["argv"][-3:-1] == ["call", method]]

    def argv(self, command: str) -> list[list[str]]:
        stripped = []
        for entry in self.commands():
            argv = entry["argv"]
            while argv and argv[0] in ("--server", "--autostart=false", "-C"):
                argv = argv[2:] if argv[0] in ("--server", "-C") else argv[1:]
            if argv and argv[0] == command:
                stripped.append(argv)
        return stripped


def agent_bin(folder: Path) -> Path:
    """Fake native CLIs on PATH; Rex runs them only in the fake server's state."""
    directory = folder / "agents"
    directory.mkdir(exist_ok=True)
    for kind in ("codex", "claude", "agy"):
        executable(directory / kind, "raise SystemExit('a fake Rex block never executes this agent')\n")
    return directory


def install(monkeypatch, fake: FakeRex) -> None:
    for key, value in fake.env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PATH", str(agent_bin(fake.folder)) + os.pathsep + os.environ.get("PATH", ""))
