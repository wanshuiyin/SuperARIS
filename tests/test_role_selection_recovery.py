"""Role selection keeps the recorded team during recovery."""
from copy import deepcopy
import json

from superaris import cli, runtime
from tests.test_orca_runtime import setup as orca_setup  # noqa: F401

TEAM = {"main": "agy", "engineer": "claude", "writer": "agy"}


def test_only_role_reopens_a_recorded_custom_role(orca_setup, capsys):
    project, client, _, _, calls, deliveries = orca_setup
    args = cli.parser().parse_args([
        "start", str(project), "--host", "orca", "--role", "main=claude",
        "--role", "figures=agy", "--only-role", "main", "--only-role", "figures",
        "--model", "figures=original-figures-model",
    ])
    runtime.start(cli.make_plan(args), args)
    saved = deepcopy(runtime.binding(project))
    prepared = len(calls)

    selected = cli.parser().parse_args(["start", str(project), "--only-role", "figures"])
    plan = cli.make_plan(selected)
    active = [role for role in plan["roles"] if role["active"]]
    assert [(role["role"], role["harness"], role["model"]) for role in active] == [
        ("figures", "agy", "original-figures-model")]
    assert cli.main(["start", str(project), "--only-role", "figures", "--plan"]) == 0
    assert json.loads(capsys.readouterr().out) == plan
    runtime.start(plan, selected)

    assert runtime.binding(project)["roles"] == saved["roles"]
    assert len(client.launches) == 2
    assert len(calls) == prepared
    assert not deliveries


def test_only_role_resumes_pending_custom_client_and_model(orca_setup, monkeypatch):
    import threading

    project, client, _, _, _, _ = orca_setup
    options = ["start", str(project), "--host", "orca"]
    for role, kind in TEAM.items():
        options += ["--role", f"{role}={kind}", "--model", f"{role}=original-{role}"]
    args = cli.parser().parse_args(options)
    stop = threading.Event()
    original_launch = client.launch_agent

    def launch_main_then_pause(*values):
        receipt = original_launch(*values)
        stop.set()
        return receipt

    monkeypatch.setattr(client, "launch_agent", launch_main_then_pause)
    runtime.start(cli.make_plan(args), args, stop_event=stop)
    saved = deepcopy(runtime.binding(project))
    assert set(saved["roles"]) == {"main"}
    assert len(saved["pending_start"]["roles"]) == 3
    monkeypatch.setattr(client, "launch_agent", original_launch)

    selected = cli.parser().parse_args(["start", str(project), "--only-role", "engineer"])
    runtime.start(cli.make_plan(selected), selected)
    assert [launch[:2] for launch in client.launches] == [
        ("agy", "original-main"), ("claude", "original-engineer")]
    main = runtime.binding(project)["roles"]["main"]
    for field in ("pane_id", "process_incarnation", "harness", "requested_model"):
        assert main[field] == saved["roles"]["main"][field]

    remaining = cli.parser().parse_args(["start", str(project)])
    runtime.start(cli.make_plan(remaining), remaining)
    assert [launch[:2] for launch in client.launches] == [
        (kind, f"original-{role}") for role, kind in TEAM.items()]
    assert "pending_start" not in runtime.binding(project)


def test_only_role_can_add_a_preset_member_to_a_custom_team(orca_setup):
    project, client, _, _, _, _ = orca_setup
    args = cli.parser().parse_args([
        "start", str(project), "--host", "orca", "--role", "main=agy",
        "--role", "engineer=claude", "--only-role", "main", "--only-role", "engineer",
        "--model", "engineer=original-engineer",
    ])
    runtime.start(cli.make_plan(args), args)
    saved = deepcopy(runtime.binding(project))

    selected = cli.parser().parse_args([
        "start", str(project), "--only-role", "engineer", "--only-role", "writer",
        "--model", "writer=chosen-writer",
    ])
    plan = cli.make_plan(selected)
    assert [(role["role"], role["harness"], role["model"])
            for role in plan["roles"] if role["active"]] == [
        ("engineer", "claude", "original-engineer"), ("writer", "codex", "chosen-writer")]
    runtime.start(plan, selected)

    assert [launch[:2] for launch in client.launches] == [
        ("agy", None), ("claude", "original-engineer"), ("codex", "chosen-writer")]
    assert runtime.binding(project)["roles"]["engineer"] == saved["roles"]["engineer"]
