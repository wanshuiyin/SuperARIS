"""Research responsibilities and AGY choices through installed product entrypoints."""
import json
from pathlib import Path

import pytest

from superaris import cli, ui, wizard
from tests.test_custom_team import caps, select
from tests.test_workbench_context_command import project_context, invoke  # noqa: F401
from tests.test_superaris_wizard import Terminal, environment  # noqa: F401


@pytest.mark.parametrize("role", ["main", "engineer", "writer"])
@pytest.mark.parametrize("number,model", [("3", "gemini-4-argon-high"),
                                         ("4", "gemini-4-carbon-high"),
                                         ("5", "gemini-4-hydrogen-high")])
def test_agy_shortcuts_for_every_role_and_previous_choice(monkeypatch, role, number, model):
    prompts = []
    answers = iter([number, ""])
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or next(answers))
    assert wizard.select_model(role, "agy", None) == model
    assert wizard.select_model(role, "agy", model) == model
    assert prompts[-1].endswith(f"[{number}]{ui.tr('：')}")


def test_native_default_manual_and_codex_choice_remain(monkeypatch):
    answers = iter(["", "2", "custom-native-model", "", "", "3"])
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or next(answers))
    assert wizard.select_model("main", "agy", None) is None
    assert wizard.select_model("writer", "agy", None) == "custom-native-model"
    assert wizard.select_model("writer", "agy", "custom-native-model") == "custom-native-model"
    assert wizard.select_model("engineer", "codex", None) == "gpt-6.1-sol"


def test_back_keeps_all_three_model_choices_and_original_role_ids(monkeypatch, tmp_path):
    answers = ["2", str(tmp_path / "not-created"), "4", "3", "3", "3",
               "4", "5", "3", "", "", "2",  # back from summary
               "", "", "", "", "", "", "", "", "", "", "1"]
    selection, prompts = select(monkeypatch, tmp_path, answers, caps(clients=("agy",)))
    args = cli.parser().parse_args(selection.arguments)
    assert cli.assignments(args.model) == {"main": "gemini-4-carbon-high",
                                          "engineer": "gemini-4-hydrogen-high",
                                          "writer": "gemini-4-argon-high"}
    assert cli.assignments(args.role) == dict.fromkeys(("main", "engineer", "writer"), "agy")
    assert [p for p in prompts if "Model selection" in p][-3:] == [
        "Model selection [4]: ", "Model selection [5]: ", "Model selection [3]: "]
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize("role", ["main", "engineer", "writer"])
def test_prepared_responsibilities_and_coordination_reach_original_role_without_redispatch(project_context, role):
    fixture = project_context
    before = fixture["binding"].read_bytes()
    old_packet = Path(fixture["roles"][role]["context"]["packet"])
    old_content = old_packet.read_bytes()
    result = invoke(fixture, role)
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout)
    role_text = Path(prepared["role_file"]).read_text()
    if role == "writer":
        assert "Research & Writing" in role_text
        assert "hypotheses" in role_text and "derivation drafts" in role_text
        assert "engineering runs" in role_text and "verified results" in role_text
        assert "original main" in role_text
    elif role == "main":
        assert "research" in role_text and "in parallel" in role_text
        assert "acceptance" in role_text and "next authorized assignments" in role_text
    skill = Path(prepared["skill_index"]["project-agent"])
    coordination = (skill.parent / "references/coordination.md").read_text()
    assert "discriminating" in coordination and "baseline" in coordination
    assert "watch/report" in coordination and "fresh" in coordination and "MCP reviewer" in coordination
    assert "keep the writer waiting" not in coordination
    assert fixture["roles"][role]["inputs"]["task"] in role_text
    assert fixture["binding"].read_bytes() == before
    assert old_packet.read_bytes() == old_content
    assert not fixture["marker"].exists()


@pytest.mark.parametrize("language", ["zh", "en"])
def test_real_pty_agy_choices_preview_and_cancel(environment, language):
    fixture = environment
    project = fixture["root"] / "new research team"
    term = Terminal([], fixture["root"], fixture["env"], language="1" if language == "zh" else "2")
    try:
        term.expect("项目目录" if language == "zh" else "Project directory")
        term.line(str(project))
        term.expect("客户端组合" if language == "zh" else "Client combination")
        term.line("4")
        for _ in range(3):
            term.expect("— 客户端" if language == "zh" else "— Client")
            term.line("3")
        for number in ("4", "5", "3"):
            term.expect("Gemini 4 Hydrogen High")
            term.expect("模型选择" if language == "zh" else "Model selection")
            term.line(number)
        term.expect("工作台名称" if language == "zh" else "Workbench name")
        assert ("研究与写作 / AGY" if language == "zh" else "Research & Writing / AGY") in term.text
        term.line()
        term.expect("本次任务" if language == "zh" else "Task (leave blank")
        term.line()
        term.expect("[4/4]")
        term.expect("请选择" if language == "zh" else "Choose an option")
        assert all(model in term.text for model in ("gemini-4-carbon-high", "gemini-4-hydrogen-high", "gemini-4-argon-high"))
        term.line("3")
        assert term.finish() == 0, term.text
        assert not project.exists()
        assert json.loads(fixture["state"].read_text())["commands"] == []
    finally:
        (fixture["root"] / f"RESEARCH-MODELS-{language}.txt").write_text(term.text)
        term.close()
