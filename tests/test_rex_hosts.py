"""Rex host selection, discovery, receiver identity, context and wizard choices; all offline."""
import os
from pathlib import Path

import pytest

from superaris import hosts, receiver, rex, ui, wizard
from superaris.cli import make_plan, parser
from superaris.context import prepare_context
from superaris.state import directory, write
from tests.support import make_aris_repo
from tests.test_orca_wizard import no_launch, select  # noqa: F401  (autouse: selection never spawns)


def test_new_rex_plan_is_offline_and_keeps_explicit_cli_link(tmp_path):
    current = tmp_path / "Rex Server.app/Versions/Current"
    (tmp_path / "Rex Server.app/Versions/2061").mkdir(parents=True)
    current.symlink_to("2061")
    args = parser().parse_args(["start", str(tmp_path), "--host", "rex", "--rex-bin", str(current / "rex"), "--plan"])
    plan = make_plan(args)
    assert plan["host"] == "rex" and len(plan["roles"]) == 3
    assert not (tmp_path / ".aris").exists()
    resumed = parser().parse_args(args.start_arguments)
    assert resumed.host == "rex" and resumed.rex_bin == str(current / "rex")  # Not resolved to Versions/2061.


def test_rex_binding_is_inherited_and_cannot_switch(tmp_path):
    write(directory(tmp_path) / "launch.json", {"host": "rex", "session": "original", "roles": {}})
    assert make_plan(parser().parse_args(["start", str(tmp_path), "--plan"]))["host"] == "rex"
    with pytest.raises(ValueError, match="belongs to rex"):
        make_plan(parser().parse_args(["start", str(tmp_path), "--host", "herdr", "--plan"]))


def test_discovery_prefers_path_then_app_bundle_without_installing(tmp_path, monkeypatch):
    monkeypatch.setattr(rex.shutil, "which", lambda command: "/usr/local/bin/rex" if command == "rex" else None)
    assert rex.discover_rex() == {"cli": os.path.abspath("/usr/local/bin/rex"), "source": "PATH"}
    monkeypatch.setattr(rex.shutil, "which", lambda command: None)
    monkeypatch.setattr(rex.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert rex.discover_rex()["cli"] is None
    bundled = (tmp_path / "Library/Application Support/com.superlogical.rex/RexServer/Versions/Current"
               / "Rex Server.app/Contents/MacOS/rex")
    bundled.parent.mkdir(parents=True)
    bundled.write_text("bundled CLI fixture; never executed")
    assert rex.discover_rex() == {"cli": str(bundled), "source": "bundled"}
    monkeypatch.setattr(rex.sys, "platform", "linux")
    assert rex.discover_rex()["source"] == "missing"
    assert "superlogical.com/rex" in rex.rex_missing_action(rex.discover_rex())


def test_receiver_identity_pins_server_instance_and_session():
    main = {"host": "rex", "pane_id": "block:1", "harness": "codex", "pid": 7, "runtime_id": "instance-A",
            "execution_host": "host-A", "rex_session": "session:1"}
    bound = {"host": "rex", "session": "aris", "execution_environment": "local", "roles": {"main": main}}
    expected = receiver.signature(bound)
    assert expected["host"] == "rex" and expected["runtime_id"] == "instance-A" and expected["rex_session"] == "session:1"
    assert hosts.identity_present(main)
    assert not hosts.identity_present({**main, "pid": None})
    assert receiver.same_owner(expected, receiver.signature(bound))
    for key, value in (("runtime_id", "instance-B"), ("rex_session", "session:2"), ("pid", 8)):
        changed = {**bound, "roles": {"main": {**main, key: value}}}
        assert not receiver.same_owner(expected, receiver.signature(changed))


@pytest.mark.parametrize("harness", ["codex", "claude", "agy"])
def test_rex_packet_requires_its_host_entry(tmp_path, harness):
    project = tmp_path / "research project 中文"
    project.mkdir()
    prepared = prepare_context(project, "writer", harness, "Read existing results", [],
                               repo=make_aris_repo(tmp_path / "aris"), workbench_host="rex")
    host = Path(prepared["host_reference"]).read_text(encoding="utf-8")
    navigation = Path(prepared["navigation"]).read_text(encoding="utf-8")
    assert "Workbench host: rex" in Path(prepared["packet"]).read_text(encoding="utf-8")
    assert "Before operating Rex" in navigation and "Rex block binding" in navigation
    assert "`rex_instance`" in host and "Do not send input to your own block" in host
    assert "independent reviewer" in host and "personal preferences" in host


def caps(**found):
    return {"herdr": None, "orca": None, "orca_app": None, "rex": None, "brew": None,
            "codex": "fake-codex", "claude": "fake-claude", "agy": "fake-agy", **found}


@pytest.mark.parametrize("available,answer,expected", [
    (caps(rex="/rex"), None, "rex"),
    (caps(herdr="herdr", rex="/rex"), "", "herdr"),
    (caps(herdr="herdr", rex="/rex"), "2", "rex"),
    (caps(herdr="herdr", orca="orca", rex="/rex"), "3", "rex"),
])
def test_new_project_offers_rex_only_when_found(monkeypatch, tmp_path, capsys, available, answer, expected):
    project = tmp_path / "new rex project"
    # CC + Codex + AGY, so the host-specific AGY follow-up line is shown.
    answers = ["2", str(project), *([answer] if answer is not None else []), "3", "", "", "", "", "", "1"]
    selection, prompts = select(monkeypatch, tmp_path, answers, available)
    arguments = selection.arguments
    assert ("--host" in arguments) == (expected != "herdr")
    if expected != "herdr":
        assert arguments[arguments.index("--host") + 1] == expected
    output = capsys.readouterr().out
    assert f"Host: {expected.capitalize()}" in output
    if expected == "rex":
        assert "Rex: CLI found" in output and "on Rex, explicit automation ownership" in output


def test_previous_rex_choice_is_the_menu_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert wizard.select_workbench(caps(herdr="herdr", orca="orca", rex="/rex"), "rex") == "rex"


@pytest.mark.parametrize("available,message", [
    (caps(), "install and open Rex"),
    (caps(rex_recorded="/old/rex"), "--rex-bin"),
])
def test_missing_rex_explains_the_next_step_without_installing(capsys, available, message):
    ui.set_language("en")
    assert not wizard.dependency_summary(available, "rex")
    output = capsys.readouterr().out
    assert message in output and "brew" not in output


def test_recovery_uses_the_recorded_rex_cli_from_files_only(tmp_path):
    launcher = tmp_path / "recorded rex"
    launcher.write_text("CLI fixture; must not be executed")
    bound = {"host": "rex", "pending_start": {"arguments": ["start", str(tmp_path), "--rex-bin", str(launcher)]}}
    found = wizard.recovery_capabilities(caps(), bound)
    assert found["rex"] == os.path.abspath(launcher) and found["rex_recorded"] == str(launcher)
    gone = wizard.recovery_capabilities(caps(rex="/other/rex"), {"host": "rex", "rex_bin": str(tmp_path / "gone")})
    assert gone["rex"] is None


@pytest.mark.parametrize("old_still_on_disk", [False, True])
def test_resume_replays_the_corrected_rex_cli_not_the_stale_pending_one(monkeypatch, tmp_path, old_still_on_disk):
    corrected = tmp_path / "corrected rex"
    corrected.write_text("CLI fixture; must not be executed")
    old = tmp_path / "old rex"
    if old_still_on_disk:  # e.g. an incompatible API revision the user replaced with --rex-bin.
        old.write_text("CLI fixture; must not be executed")
    stale = ["start", str(tmp_path), "--host", "rex", "--rex-bin", str(old), "--only-role", "main"]
    bound = {"host": "rex", "session": "original", "rex_bin": str(corrected), "roles": {"main": {"harness": "codex"}},
             "pending_start": {"arguments": stale, "roles": [{"role": "main", "harness": "codex", "model": None}]}}
    selection, _ = select(monkeypatch, tmp_path, ["2", str(tmp_path), "1", "1"], caps(), bound)
    assert selection.arguments == [*stale[:5], os.path.abspath(corrected), *stale[6:]]
    assert bound["pending_start"]["arguments"] == stale  # The record itself is untouched.
