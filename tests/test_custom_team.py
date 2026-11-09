"""Custom role selection through the real wizard; no native clients or models."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from superaris import cli, runtime, ui, wizard
from tests.test_aris_workbench import fake_herdr, project  # noqa: F401
from tests.test_orca_runtime import setup as orca_setup  # noqa: F401
from tests.test_three_role_defaults import invoke, start

TEAM = {"main": "agy", "engineer": "claude", "writer": "agy"}


def caps(host="herdr", clients=("claude", "agy")):
    return {"herdr": "fake-herdr" if host == "herdr" else None,
            "orca": "fake-orca" if host == "orca" else None, "orca_app": None, "brew": None,
            **{kind: f"fake-{kind}" if kind in clients else None for kind in wizard.LABELS}}


def select(monkeypatch, tmp_path, answers, available, bound=None):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wizard, "capabilities", lambda: available)
    if bound is not None:
        monkeypatch.setattr(runtime, "binding", lambda p: bound)
    iterator = iter(answers)
    prompts = []

    def reply(prompt):
        prompts.append(prompt)
        return next(iterator)

    monkeypatch.setattr("builtins.input", reply)
    previous = ui.language
    try:
        return wizard.run(), prompts
    finally:
        ui.set_language(previous)


@pytest.mark.parametrize("host", ["herdr", "orca"])
@pytest.mark.parametrize("language", ["1", "2"])
def test_custom_without_codex_selects_models_and_same_host_plan(monkeypatch, tmp_path, capsys, host, language):
    project = tmp_path / "custom project"
    answers = [language, str(project), "4", "3", "2", "3",
               "2", "main-model", "2", "engineer-model", "2", "writer-model", "", "", "1"]
    selection, prompts = select(monkeypatch, tmp_path, answers, caps(host))
    assert selection.create_project and not project.exists()
    args = cli.parser().parse_args(selection.arguments)
    assert cli.assignments(args.role) == TEAM
    assert cli.assignments(args.model) == {role: role + "-model" for role in TEAM}
    project.mkdir()  # Test fixture only; selection/confirmation itself wrote nothing.
    before = list(project.iterdir())
    plan = cli.make_plan(args)
    assert plan["host"] == host
    assert {r["role"]: r["harness"] for r in plan["roles"] if r["active"]} == TEAM
    assert {r["role"]: r["model"] for r in plan["roles"]} == cli.assignments(args.model)
    assert all("wait" in r["task"].lower() for r in plan["roles"])
    assert len({r["write_scope"] for r in plan["roles"]}) == 3
    assert list(project.iterdir()) == before
    output = capsys.readouterr().out
    assert ("主会话 / AGY" if language == "1" else "Main / AGY") in output
    assert ("工程 / CC" if language == "1" else "Engineer / CC") in output
    assert ("CC/AGY 收到后续结果" if language == "1" else "CC/AGY will notify") in output
    assert "All current combinations require Codex" not in output


@pytest.mark.parametrize("client,number", [("claude", "2"), ("agy", "3")])
def test_one_installed_client_can_fill_all_three_roles(monkeypatch, tmp_path, client, number):
    selection, _ = select(monkeypatch, tmp_path,
                          ["2", str(tmp_path), "4", number, number, number, "", "", "", "", "", "1"],
                          caps(clients=(client,)))
    args = cli.parser().parse_args(selection.arguments)
    assert cli.assignments(args.role) == dict.fromkeys(TEAM, client)
    assert all(r["harness"] == client for r in cli.make_plan(args)["roles"])


def test_no_clients_explains_missing_dependency_without_writing(monkeypatch, tmp_path, capsys):
    selection, _ = select(monkeypatch, tmp_path, ["2", str(tmp_path / "absent")], caps(clients=()))
    assert selection is None and list(tmp_path.iterdir()) == []
    output = capsys.readouterr().out
    assert "No agent client was found" in output
    assert "require Codex" not in output


def test_unavailable_custom_client_is_not_selected(monkeypatch, tmp_path, capsys):
    selection, _ = select(monkeypatch, tmp_path,
                          ["2", str(tmp_path), "4", "1", "3", "3", "3", "", "", "", "", "", "1"],
                          caps(clients=("agy",)))
    assert set(cli.assignments(cli.parser().parse_args(selection.arguments).role).values()) == {"agy"}
    assert "Choose an available local client" in capsys.readouterr().out


def test_back_keeps_custom_roles_and_cancel_writes_nothing(monkeypatch, tmp_path):
    answers = ["2", str(tmp_path / "uncreated"), "4", "3", "2", "3", "", "", "", "", "", "2",
               "", "", "", "", "", "", "", "", "", "", "3"]
    selection, prompts = select(monkeypatch, tmp_path, answers, caps())
    assert selection is None and list(tmp_path.iterdir()) == []
    combo = [p for p in prompts if "Client combination" in p]
    assert combo[-1].endswith("[4]: ")
    main = [p for p in prompts if "Main:" in p and " — Client" in p]
    assert len(main) == 2 and main[-1].endswith("[3]: ")


@pytest.mark.parametrize("pending", [False, True])
def test_custom_existing_or_pending_reentry_keeps_original_contract(monkeypatch, tmp_path, pending):
    args = cli.parser().parse_args(["start", str(tmp_path), "--host", "orca", "--task", "original assignment",
                                   "--role", "main=agy", "--role", "engineer=claude", "--role", "writer=agy",
                                   "--model", "main=original-main", "--model", "writer=original-writer"])
    plan = cli.make_plan(args)
    bound = {"host": "orca", "session": "original-session", "preset": "codex",
             "roles": {r["role"]: {"harness": r["harness"], "requested_model": r["model"],
                                    "inputs": {"task": r["task"], "write_scope": r["write_scope"]},
                                    "delivery": {"phase": "unknown"}} for r in plan["roles"]}}
    if pending:
        bound["pending_start"] = {"arguments": args.start_arguments, "roles": plan["roles"]}
        bound["roles"] = {"main": bound["roles"]["main"]}
    original = deepcopy(bound)
    selection, prompts = select(monkeypatch, tmp_path, ["2", str(tmp_path), "1", "1"], caps("orca"), bound)
    assert bound == original
    assert not any("Client combination" in prompt for prompt in prompts)
    if pending:
        assert selection.arguments == args.start_arguments
    else:
        assert selection.resume_existing
    (tmp_path / ".aris/workbench").mkdir(parents=True)
    (tmp_path / ".aris/workbench/launch.json").write_text(json.dumps(bound))
    restored = cli.make_plan(cli.parser().parse_args(selection.arguments))
    assert {r["role"]: r["harness"] for r in restored["roles"]} == TEAM
    assert restored["roles"][0]["task"] == "original assignment"
    assert restored["roles"][0]["model"] == "original-main"
    assert restored["roles"][2]["model"] == "original-writer"


def test_custom_main_partial_fake_start_recovers_original_owner_and_full_team(project, fake_herdr):
    binary = fake_herdr["binary"]
    code = binary.read_text()
    anchor = '    output({"agent": state["agents"][name]})'
    binary.write_text(code.replace(anchor, '''    if state.pop("fail_first_start_response", False):
        save()
        raise SystemExit("simulated startup timeout after owner actually launched")
    output({"agent": state["agents"][name]})''', 1))
    state = json.loads(fake_herdr["state"].read_text()); state["fail_first_start_response"] = True
    fake_herdr["state"].write_text(json.dumps(state))
    selected = ["--role", "main=agy", "--role", "engineer=claude", "--role", "writer=agy",
                "--model", "main=chosen-main", "--model", "writer=chosen-writer"]
    first = invoke(project, "--session", "isolated-test", "--no-attach", "--no-receiver", "--no-install",
                   "--herdr-bin", str(binary), *selected, environment=fake_herdr["env"])
    assert first.returncode != 0 and "startup timeout" in first.stderr
    partial = runtime.binding(project)
    assert {r["role"]: r["harness"] for r in partial["pending_start"]["roles"]} == TEAM
    result = start(project, fake_herdr)
    assert {name: r["harness"] for name, r in result["roles"].items()} == TEAM
    assert result["roles"]["main"]["pane_id"] == partial["roles"]["main"]["pane_id"]
    assert result["roles"]["main"]["delivery"] == partial["roles"]["main"]["delivery"]
    assert result["roles"]["main"]["requested_model"] == "chosen-main"
    assert result["roles"]["writer"]["requested_model"] == "chosen-writer"
    assert "pending_start" not in runtime.binding(project)
    commands = json.loads(fake_herdr["state"].read_text())["commands"]
    assert len([v for v in commands if v[:2] == ["agent", "start"]]) == 3
    assert not any(v[:2] == ["agent", "prompt"] for v in commands)


def test_custom_orca_launch_and_reentry_retain_choices(orca_setup):
    project, client, args, _, calls, deliveries = orca_setup
    args.role = [f"{role}={kind}" for role, kind in TEAM.items()]
    args.model = ["main=main-model", "writer=writer-model"]
    plan = cli.make_plan(args)
    result = runtime.start(plan, args)
    saved = deepcopy(runtime.binding(project))
    assert {name: r["harness"] for name, r in result["roles"].items()} == TEAM
    assert [kind for kind, _, _ in client.launches] == list(TEAM.values())
    plain = cli.parser().parse_args(["start", str(project)])
    runtime.start(cli.make_plan(plain), plain)
    assert runtime.binding(project)["roles"] == saved["roles"]
    assert len(client.launches) == 3
