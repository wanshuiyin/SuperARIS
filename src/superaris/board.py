"""Read existing project records without probing or controlling native owners."""
from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
import webbrowser

from .state import directory


def collect(project: Path) -> dict:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError("Selected project directory does not exist")
    root = directory(project)
    sources, warnings = [], []

    def read_object(path):
        name = str(path.relative_to(project))
        source = {"path": name, "modified_at": None, "status": "missing"}
        sources.append(source)
        try:
            if not path.resolve().is_relative_to(project):
                raise ValueError("Record is outside the selected project")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            source.update(status="read", modified_at=datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc).isoformat())
            return value
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            source["status"] = "unreadable"
            warnings.append(f"{name}: {exc}")
            return {}

    def records(folder):
        if not folder.resolve().is_relative_to(project):
            warnings.append(f"{folder.relative_to(project)}: outside selected project")
            return []
        try:
            return sorted(folder.glob("*.json"))
        except OSError as exc:
            warnings.append(f"{folder.relative_to(project)}: {exc}")
            return []

    bound = read_object(root / "launch.json")
    bridge = read_object(root / "bridge.json")
    receiver = read_object(root / "receiver.json")
    control = read_object(root / "receiver-control.json")
    roles, tasks = [], []
    attempts = bridge.get("attempts", {})
    delivered = bridge.get("delivered", {})
    for name, role in (bound.get("roles") or {}).items():
        if not isinstance(role, dict):
            continue
        inputs, context_delivery = role.get("inputs", {}), role.get("delivery", {})
        roles.append({"id": name, "harness": role.get("harness"),
                      "requested_model": role.get("requested_model"),
                      "recorded_status": role.get("status", "unknown"),
                      "automation_owned": bool(role.get("automation_owned")),
                      "task": inputs.get("task"), "write_scope": inputs.get("write_scope"),
                      "delivery": context_delivery.get("phase", "unknown"),
                      "pending_unknown": context_delivery.get("phase") in {"unknown", "attempting"}})
    for path in records(root / "handles"):
        handle = read_object(path)
        if not handle:
            continue
        # The existing filename is the lookup key; never use an arbitrary ID as
        # an additional filesystem path or follow a query/record pointer.
        identifier = path.stem
        reports = []
        for report_path in records(root / "reports" / identifier):
            report = read_object(report_path)
            if report:
                reports.append({"outcome": report.get("outcome"), "message": report.get("message"),
                                "time": report.get("time"), "acceptance": report.get("acceptance", "not_evaluated"),
                                "path": str(report_path.relative_to(project))})
        delivery = handle.get("last_delivery", {})
        if isinstance(delivered.get(identifier), dict):
            delivery = delivered[identifier]
        tasks.append({"id": identifier, "owner_role": handle.get("owner_role", "main"),
                      "worker_role": handle.get("worker_role"), "active": bool(handle.get("active")),
                      "wait_for": handle.get("wait_for"), "query": handle.get("query"),
                      "next_authorized": handle.get("next_authorized"), "record": handle.get("record"),
                      "deliverables": handle.get("deliverables", []), "receipt": handle.get("receipt"),
                      "acceptance": "consult_original_record", "delivery": delivery.get("delivery"),
                      "pending_unknown": identifier in attempts, "reports": reports})
    return {"schema_version": 1,
            "project": {"name": project.name, "path": str(project), "host": bound.get("host", "herdr"),
                        "ui_language": bound.get("ui_language", "zh")},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "roles": roles, "tasks": tasks,
            "receiver": {"recorded_status": receiver.get("status", "unknown"),
                         "enabled": control.get("enabled"),
                         "reason": receiver.get("outcome", {}).get("reason"),
                         "error": receiver.get("outcome", {}).get("error")},
            "sources": sources, "warnings": warnings}


def render(data: dict, language: str | None = None) -> str:
    en = (language or data["project"]["ui_language"]) == "en"
    lines = [f"SuperARIS · {data['project']['name']}",
             "Project records (not a live process probe)" if en else "项目记录（未探活进程）"]
    for role in data["roles"]:
        lines += [f"\n{role['id']} · {role['harness']} · {role['requested_model'] or ('native settings' if en else '原生设置')}",
                  str(role["task"] or "—"),
                  f"{'Recorded delivery' if en else '投递记录'}: {role['delivery']} · "
                  f"{'automation' if role['automation_owned'] else 'human'}"]
        if role["pending_unknown"]:
            lines.append("Delivery needs inspection" if en else "投递待核实")
    for task in data["tasks"]:
        state = ("waiting" if task["active"] else "wait closed") if en else ("等待中" if task["active"] else "等待已结束")
        lines += [f"\n[{task['id']}] {task['worker_role'] or 'external'} → {task['owner_role']} · {state}",
                  f"{'Waiting for' if en else '所等结果'}: {task['wait_for']}"]
        if task["reports"]:
            report = task["reports"][-1]
            lines.append(f"{report['time']} · {report['outcome']}: {report['message']}")
        if task["pending_unknown"]:
            lines.append("Delivery needs inspection" if en else "投递待核实")
        lines += [f"{'Next authorized' if en else '下一已授权动作'}: {task['next_authorized']}",
                  f"{'Acceptance: consult original record' if en else '验收见原记录'}: {task['receipt'] or task['record'] or '—'}"]
    lines += [f"\n{'Recorded receiver' if en else '收件记录'}: {data['receiver']['recorded_status']}"]
    lines.extend(data["warnings"])
    return "\n".join(lines)


def terminal_overview(data: dict, language: str | None = None) -> str:
    """Compact terminal layout; raw task text and original gates stay unchanged."""
    import shutil
    import unicodedata
    en = (language or data["project"]["ui_language"]) == "en"
    width = max(24, shutil.get_terminal_size((100, 30)).columns - 2)

    def short(value, limit=100):
        value = " ".join(str(value or "—").split())
        # Recorded text is not a terminal control channel.
        value = "".join(c for c in value if not unicodedata.category(c).startswith("C"))
        used, result = 0, ""
        for c in value:
            used += 2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1
            if used > min(width, limit) - 1:
                return result + "…"
            result += c
        return result

    active = [task for task in data["tasks"] if task["active"]]
    replies = sum(bool(t["reports"]) for t in active)
    unknown = sum(t["pending_unknown"] for t in active) + sum(r["pending_unknown"] for r in data["roles"])
    lines = [short("SuperARIS · " + data["project"]["name"]),
             (f"{len(data['roles'])} roles · {len(active)} waits · {replies} with replies · {unknown} unknown"
              if en else f"{len(data['roles'])} 角色 · {len(active)} 活跃等待 · {replies} 已回报 · {unknown} 投递待核"),
             "─" * min(width, 78)]
    for role in data["roles"]:
        lines.append(short(f"{role['id']} · {role['harness']} · {role['requested_model'] or 'native'}"))
        lines.append(short(f"  {role['delivery']} · {'automation' if role['automation_owned'] else 'human'}"))
    for task in active:
        lines += ["", short(f"{task['worker_role'] or 'external'} → {task['owner_role']}  [{task['id']}]"),
                  short(("Waiting: " if en else "所等：") + str(task["wait_for"] or "—"))]
        if task["reports"]:
            report = task["reports"][-1]
            lines.append(short(f"{report['outcome']} · {report['message']}"))
            lines.append(short(str(report["time"])))
        if task["pending_unknown"]:
            lines.append("! Inspect unknown delivery" if en else "! 投递待核实")
        lines.append(short(("Next: " if en else "下一步：") + str(task["next_authorized"] or "—")))
    lines += ["", ("Saved records · reports need original acceptance · Ctrl+C closes view"
                    if en else "项目记录 · 报告仍需原任务验收 · Ctrl+C 只退出视图")]
    lines.extend(short(warning) for warning in data["warnings"])
    return "\n".join(lines)


def watch(project: Path, language: str | None = None) -> int:
    """Foreground view only; refresh on material record changes, no project writes."""
    previous = None
    interactive = sys.stdout.isatty()
    try:
        while True:
            data = collect(project)
            material = {key: value for key, value in data.items() if key != "generated_at"}
            if material != previous:
                if interactive:
                    print("\033[2J\033[H", end="")
                print(terminal_overview(data, language), flush=True)
                previous = material
            time.sleep(2)
    except KeyboardInterrupt:
        return 0


def open_tab(project: Path, binary: str = "herdr", language: str | None = None) -> dict:
    """Create only a view tab, anchored to an existing verified project pane."""
    from .client import Herdr, HerdrError, verify_owner
    from .platform import command_line
    from .state import read
    project = project.expanduser().resolve()
    bound = read(directory(project) / "launch.json", {})
    if bound.get("host", "herdr") != "herdr":
        raise ValueError("--tab is for existing Herdr teams; use --watch or --open for Orca or Rex")
    main = bound.get("roles", {}).get("main", {})
    if not bound.get("session") or not main.get("pane_id") or not main.get("pid"):
        raise ValueError("No recorded project owner identity; use --watch or --open without starting a team")
    client = Herdr(bound["session"], binary)
    verify_owner(client, main, project)
    pane = client.json("pane", "get", main["pane_id"])["pane"]
    workspace = pane["workspace_id"]
    if bound.get("workspace_id") and workspace != bound["workspace_id"]:
        raise HerdrError("Recorded project workspace changed; inspect the original binding")
    client.json("workspace", "get", workspace)  # Existing only; never ensure/install/start.
    en = (language or bound.get("ui_language", "zh")) == "en"
    created = client.json("tab", "create", "--workspace", workspace, "--cwd", str(project),
                          "--label", "Collaboration progress" if en else "协作进度", "--no-focus")
    target, tab = created["root_pane"]["pane_id"], created["tab"]["tab_id"]
    argv = [sys.executable, "-m", "superaris", "board", str(project), "--watch"]
    if language:
        argv += ["--lang", language]
    command = command_line(argv)
    try:
        client.run("pane", "run", target, command)
    except HerdrError as exc:
        raise HerdrError(f"Progress tab {tab}, pane {target} was created; command delivery is unknown. Inspect it before retrying. {exc}") from exc
    return {"session": bound["session"], "workspace_id": workspace, "tab_id": tab,
            "pane_id": target, "command": command, "admitted": True,
            "note": "View command queued; original team and project records unchanged. Each --tab creates a new tab."}


def create_server(project: Path, port: int = 0) -> ThreadingHTTPServer:
    project = project.expanduser().resolve()
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    collect(project)  # Validate before binding; never creates project metadata.

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/board":
                    body, content_type = json.dumps(collect(project), ensure_ascii=False).encode(), "application/json"
                elif path == "/":
                    body = resources.files("superaris").joinpath("resources/board.html").read_bytes()
                    content_type = "text/html"
                else:
                    self.send_error(404)
                    return
            except (OSError, ValueError) as exc:
                self.send_error(503, "Project records unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(project: Path, port: int = 0, open_browser: bool = False, language: str | None = None) -> int:
    with create_server(project, port) as server:
        url = f"http://127.0.0.1:{server.server_port}/" + (f"?lang={language}" if language else "")
        print(f"SuperARIS board: {url}\nCtrl+C stops this read-only view; original team and receiver remain unchanged.", flush=True)
        if open_browser:
            if sys.platform == "darwin":
                opened = subprocess.run(["open", "-a", "Microsoft Edge", url],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if opened.returncode:
                    webbrowser.open(url)
            else:
                webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
