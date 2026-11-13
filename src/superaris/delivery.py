"""Conservative input delivery: human panes receive a visible notice by default."""
from pathlib import Path
import re

from .client import Herdr, HerdrError, verify_owner, read_screen, send_prompt, notify


def codex_input(text: str) -> str | None:
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    prompts = [line.strip()[1:].strip() for line in clean.splitlines() if line.lstrip().startswith("›")]
    return prompts[-1] if prompts else None


def empty_codex_input(text: str) -> bool:
    """Only the actual empty Codex placeholder tested by this adapter is eligible."""
    return codex_input(text) in {"", "Ask Codex to do anything"}


def automatic_input_supported(client, role: dict) -> bool:
    return role.get("harness") == "codex" or (
        role.get("harness") == "agy" and getattr(client, "host", None) != "orca")


def agy_input(text: str) -> str | None:
    """Read the idle AGY composer, including every line of a pending draft."""
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    lines = clean.splitlines()
    borders = [index for index, line in enumerate(lines) if re.fullmatch(r"\s*─{3,}\s*", line)]
    if len(borders) < 2:
        return None
    top, bottom = borders[-2:]
    footer = "\n".join(lines[bottom + 1:]).strip()
    body = lines[top + 1:bottom]
    if (not footer.startswith("? for shortcuts") or any(line.lstrip().startswith(">") for line in lines[bottom + 1:])
            or not body or not body[0].lstrip().startswith(">")):
        return None
    return "\n".join([body[0].lstrip()[1:].strip(), *[line.strip() for line in body[1:]]]).strip()


def empty_agy_input(text: str) -> bool:
    value = agy_input(text)
    return value is not None and " ".join(value.split()) in {
        "", "Auto mode: edits & safe commands auto-approved (shift+tab to cycle)"}


def deliver(client: Herdr, project: Path, role: dict, prompt: str) -> dict:
    live = verify_owner(client, role, project)
    from .runtime import binding
    latest = binding(project).get("roles", {})
    persisted = next((record for record in latest.values() if record.get("pane_id") == live["pane_id"]), None)
    # Honor a handoff that happened after the receiver's earlier snapshot.
    automation = role.get("automation_owned") and (role.get("_initial_bootstrap") or persisted is None or persisted.get("automation_owned"))
    revoke = False
    if automation and automatic_input_supported(client, live) and live["status"] in {"idle", "done"}:
        view = read_screen(client, live["pane_id"])
        parser = agy_input if live["harness"] == "agy" else codex_input
        empty = empty_agy_input if live["harness"] == "agy" else empty_codex_input
        if empty(view):
            # Recheck the occupant/status after reading. This is a dedicated automation
            # session, not a guarantee against a human concurrently typing after the read.
            second = verify_owner(client, live, project)
            current = binding(project).get("roles", {})
            current_owner = next((record for record in current.values() if record.get("pane_id") == second["pane_id"]), None)
            still_owned = role.get("_initial_bootstrap") or current_owner is None or current_owner.get("automation_owned")
            if second["status"] in {"idle", "done"} and still_owned:
                native_receipt = send_prompt(client, second["pane_id"], prompt)
                receipt = {"delivery": "submitted", "pane_id": second["pane_id"], "acceptance": "not_evaluated"}
                if getattr(client, "host", None) == "orca":
                    receipt["native_receipt"] = native_receipt
                return receipt
        else:
            # A startup splash without a composer is not a human draft.
            # Wait for the known input surface; never type into the splash.
            revoke = parser(view) is not None
    ui_language = binding(project).get("ui_language")
    if ui_language in {"zh", "en"}:
        from .ui import tr
        title = tr("ARIS 工作包已准备", lang=ui_language)
    else:
        title = "ARIS work packet ready"
    # Only the notification chrome follows UI language. Its original packet
    # body and native delivery/unknown semantics stay unchanged.
    notice = notify(client, title, prompt)
    receipt = {"delivery": "visible_notice", "pane_id": live["pane_id"],
            "revoke_automation": revoke,
            "reason": "Human-owned input, active/unknown state, or an unverified input surface; no keys sent",
            "acceptance": "not_evaluated"}
    if getattr(client, "host", None) == "orca":
        receipt["notice"] = notice
    return receipt
