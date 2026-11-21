"""Bounded foreground receipt bridge for one explicitly bound project.

Native events wake local reconciliation; they never establish task acceptance.
No daemon or model polling is involved, and all input uses draft-safe delivery.
Inspect unknown sends, then use ``aris resolve-delivery PROJECT --handle ID
--resolution received|not-delivered --evidence EXISTING_FILE``; never clear them
by retrying input blindly.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
from pathlib import Path
import time

from .client import Herdr, HerdrError, verify_owner
from .delivery import automatic_input_supported, deliver
from .runtime import binding
from .state import directory, read, write
from .hosts import client_for_binding, selected_host


def _pending_signals(project: Path, client: Herdr) -> list[dict]:
    # tasks may land independently of the transport. Resolve only at use time.
    from .tasks import pending_signals
    signals = pending_signals(project, client)
    for name, role in binding(project).get("roles", {}).items():
        delivery = role.get("delivery", {})
        context = role.get("context", {})
        packet = context.get("packet")
        if (role.get("automation_owned") and delivery.get("phase") == "visible_notice"
                and not delivery.get("receipt", {}).get("revoke_automation") and packet and context.get("prompt")):
            signals.append({"id": f"context-{name}-{Path(packet).parent.name}",
                            "reason": "context awaiting safe input", "prompt": context["prompt"],
                            "owner_role": name, "context_role": name, "packet": packet})
    return signals


def _mark_notified(project: Path, signal: dict, receipt: dict) -> None:
    if "observed" in signal:
        from .tasks import mark_notified
        mark_notified(project, signal, receipt)


def _signal_current(project: Path, signal: dict) -> bool:
    """Cached notices cannot outlive their original task or context packet."""
    if signal.get("context_role"):
        role = binding(project).get("roles", {}).get(signal["context_role"], {})
        return (role.get("context", {}).get("packet") == signal.get("packet")
                and role.get("delivery", {}).get("phase") in {"visible_notice", "prepared"})
    if "observed" in signal:
        from .tasks import handle_path
        return bool(read(handle_path(project, str(signal["id"])), {}).get("active"))
    return True


RESOLVE_WAIT = 6  # A receiver stopped on an unknown attempt releases listen.lock every 2 s.


def mirror_context_phase(current: dict, signal: dict, pane_id: str, phase: str, expect: set, **details) -> bool:
    """Move a context packet's role record from an expected phase, so a later
    start sees the same attempting/unknown state and never submits it again."""
    record = current.get("roles", {}).get(signal.get("context_role"), {})
    if (record.get("pane_id") != pane_id or record.get("context", {}).get("packet") != signal.get("packet")
            or record.get("delivery", {}).get("phase") not in expect):
        return False
    record["delivery"].update(phase=phase, **details)
    if phase in {"submitted", "received"}:
        record.pop("bootstrap_pending", None)
    if phase == "received":
        record["pending_context"] = None
    return True


def _mirror(project: Path, signal: dict, pane_id: str, phase: str, expect: set, **details) -> dict | None:
    from .runtime import save_binding
    from .state import launch_lock
    with launch_lock(project):  # ValueError while a launcher owns the project.
        current = binding(project)
        if mirror_context_phase(current, signal, pane_id, phase, expect, **details):
            save_binding(project, current)
            return current
    return None


@contextmanager
def quiet_listener(project: Path):
    """Hold listen.lock so a receiver's older bridge snapshot cannot overwrite a
    resolution. Take it before the launch lock: a receiver may need that lock."""
    from .platform import FileLock, LockBusy
    deadline = time.monotonic() + RESOLVE_WAIT
    while True:
        try:
            listener = FileLock(directory(project) / "listen.lock", blocking=False).acquire()
            break
        except LockBusy:
            if time.monotonic() > deadline:
                raise ValueError("A receiver is delivering for this project; stop it "
                                 "(receiver PROJECT --action stop), then resolve again") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        listener.release()


def role_attempt(project: Path, role: str, key: str = "attempts") -> str | None:
    """The bridge handle of an unknown attempt at this role's current context packet,
    or with key="settles", of a known outcome not yet written back to the role."""
    record = binding(project).get("roles", {}).get(role, {})
    for handle, attempt in read(directory(project) / "bridge.json", {}).get(key, {}).items():
        signal = attempt.get("signal") or {}
        if (signal.get("context_role") == role and signal.get("packet") == record.get("context", {}).get("packet")
                and attempt.get("pane_id") == record.get("pane_id")):
            return handle
    return None


def resolve_attempt(project: Path, handle: str, resolution: str, evidence: Path) -> dict:
    """Clear one inspected unknown attempt under quiet_listener and the launch lock."""
    path = directory(project) / "bridge.json"
    state = read(path, {})
    attempt = state.get("attempts", {}).pop(handle, None)
    if not attempt:
        raise ValueError("No unknown bridge delivery for this handle")
    state.setdefault("resolutions", []).append({**attempt, "resolution": resolution, "evidence": str(evidence)})
    if resolution == "received":
        state.get("deferred", {}).pop(handle, None)  # Received input must never be submitted again.
        state.setdefault("delivered", {})[handle] = {"signal": attempt["signal"], "pane_id": attempt["pane_id"], "delivery": "visible_notice"}
        if "observed" in attempt["signal"]:
            from .tasks import handle_path
            pointer = handle_path(project, attempt["signal"]["id"])
            observed = read(pointer)
            if observed:
                observed.update(attempt["signal"]["observed"], last_delivery={"delivery": "received", "evidence": str(evidence)})
                write(pointer, observed)
    if attempt["signal"].get("context_role"):
        from .runtime import save_binding
        current = binding(project)
        unsent = {"attempting", "unknown", "visible_notice", "prepared"}
        # A later start may have submitted the same packet; received evidence confirms that too.
        if mirror_context_phase(current, attempt["signal"], attempt["pane_id"], "received" if resolution == "received"
                                else "prepared", unsent | {"submitted"} if resolution == "received" else unsent,
                                evidence=str(evidence)):
            save_binding(project, current)
    write(path, state)
    return {"handle": handle, "resolution": resolution, "evidence": str(evidence)}


def _event_type(event: dict) -> str | None:
    """Read native stream envelopes, including the terminal events_lost error."""
    if event.get("code") == "events_lost":
        return "events_lost"
    for key in ("result", "event", "params", "error", "data"):
        value = event.get(key)
        if isinstance(value, dict):
            found = _event_type(value)
            if found:
                return found
    for key in ("type", "event", "method"):
        value = event.get(key)
        if value in ("pane.agent_status_changed", "pane_agent_status_changed"):
            return "pane.agent_status_changed"
        if value == "events_lost":
            return value
    return None


def listen(project: Path, binary: str = "herdr", duration: float | None = 300, interval: float = 5,
           stop_event=None) -> dict:
    """Only one foreground/attached receiver may deliver for this project."""
    from .platform import FileLock, LockBusy
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    root = directory(project)
    root.mkdir(parents=True, exist_ok=True)
    try:
        lock = FileLock(root / "listen.lock", blocking=False).acquire()
    except LockBusy as exc:
        raise ValueError("Another receiver owns this project; stop or reuse that receiver before listening again") from exc
    try:
        return _listen(project, binary, duration, interval, stop_event)
    finally:
        lock.release()


def _listen(project: Path, binary: str, duration: float | None, interval: float, stop_event) -> dict:
    """Listen during this foreground invocation and reconcile registered signals.

    Idle socket reads expire at interval boundaries so local artifact/task
    updates are checked even when Herdr produces no native events. A successful
    visible notice counts as delivery, never scientific acceptance.
    """
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    if duration is None and stop_event is None:
        raise ValueError("A receiver without a duration requires the attached client's stop event")
    if duration is not None and (not math.isfinite(duration) or duration < 0) or not math.isfinite(interval) or interval <= 0:
        raise ValueError("duration must be finite and nonnegative; interval must be finite and positive")
    bound = binding(project)
    if not bound.get("session") or not bound.get("roles", {}).get("main"):
        raise ValueError("No bound main owner for this project; start or bind the project first")
    client = client_for_binding(bound, project, binary, herdr_factory=Herdr)
    state_path = directory(project) / "bridge.json"
    state = read(state_path, {"delivered": {}})
    delivered = state.setdefault("delivered", {})
    attempts = state.setdefault("attempts", {})
    deferred = state.setdefault("deferred", {})
    deadline = math.inf if duration is None else time.monotonic() + duration
    result = {"project": str(project), "session": bound["session"], "reason": "duration_elapsed",
              "deliveries": [], "events": 0, "reconciliations": 0, "reconnects": 0}

    def stopped() -> bool:
        if stop_event is not None and stop_event.is_set():
            result["reason"] = "stopped"
            return True
        return False

    def reconcile() -> list[dict]:
        nonlocal bound
        current = binding(project)
        if current.get("session") != client.session or selected_host(current) != selected_host(bound):
            raise HerdrError("Project binding changed; listener stopped without transferring ownership")
        roles = current.get("roles", {})
        if not roles.get("main"):
            raise HerdrError("Project no longer has a main owner")
        if getattr(client, "host", None) == "rex":
            client.bind(current)  # Subscribe roles a later start added to this team.
        snapshot = client.snapshot()
        panes = {agent.get("pane_id") for agent in snapshot.get("agents", [])}
        if roles["main"].get("pane_id") not in panes:
            raise HerdrError("Bound main owner is absent from the current server snapshot")
        verify_owner(client, roles["main"], project)
        bound = current
        result["reconciliations"] += 1
        subscriptions = []
        for name, role in roles.items():
            if role.get("pane_id") not in panes:
                continue
            if name != "main":
                try:
                    verify_owner(client, role, project)
                except HerdrError:
                    continue
            subscriptions.append({"type": "pane.agent_status_changed", "pane_id": role["pane_id"]})
        return subscriptions

    def settle(signal_id: str, signal: dict, pane_id: str, phase: str, **details) -> dict | None:
        """Mirror a claimed packet's outcome; while a launcher holds the lock it waits here."""
        if not signal.get("context_role"):
            return None
        try:
            updated = _mirror(project, signal, pane_id, phase, {"attempting"}, **details)
        except ValueError:
            state.setdefault("settles", {})[signal_id] = {"signal": dict(signal), "pane_id": pane_id,
                                                          "phase": phase, "details": details}
            write(state_path, state)
            return None
        if state.get("settles", {}).pop(signal_id, None):
            write(state_path, state)
        return updated

    def check_signals() -> bool:
        nonlocal bound
        for signal_id, item in list(state.get("settles", {}).items()):
            settle(signal_id, item["signal"], item["pane_id"], item["phase"], **item["details"])
        for signal_id, attempt in attempts.items():
            if (attempt.get("signal") or {}).get("context_role"):
                # Its role now records the unknown too, so no signal re-raises it.
                result.update(reason="unknown_requires_inspection", pending_unknown=signal_id, attempt=attempt,
                              error="An earlier context delivery outcome is unknown. Inspect the actual owner input/receipt before explicitly clearing this attempt; no input was resent.")
                return False
        changed = False
        settles = state.setdefault("settles", {})  # Their role phase is not yet written back.
        for identifier, signal in list(deferred.items()):
            if identifier in settles:
                continue
            owner = bound["roles"].get(signal.get("owner_role") or "main", {})
            if not owner.get("automation_owned") or not automatic_input_supported(client, owner) or not _signal_current(project, signal):
                del deferred[identifier]
                changed = True
        if changed:
            write(state_path, state)
        signals = dict(deferred)
        signals.update({str(signal["id"]): signal for signal in _pending_signals(project, client)})
        for signal_id, signal in signals.items():
            if stopped():
                return False
            if signal_id in settles:
                continue
            if not _signal_current(project, signal):
                if deferred.pop(signal_id, None) is not None:
                    write(state_path, state)
                continue
            if signal_id in attempts:
                result.update(reason="unknown_requires_inspection", pending_unknown=signal_id,
                              attempt=attempts[signal_id],
                              error="An earlier delivery outcome is unknown. Inspect the actual owner input/receipt before explicitly clearing this attempt; no input was resent.")
                return False
            role_name = signal.get("owner_role") or "main"
            role = bound["roles"].get(role_name)
            if role is None:
                # An explicit unbound owner must not silently become main.
                result.setdefault("pending", []).append({"id": signal_id, "reason": f"Unbound owner role: {role_name}"})
                continue
            previous = delivered.get(signal_id, {})
            automation = role.get("automation_owned") and automatic_input_supported(client, role)
            if signal.get("context_role") and not previous and automation:
                # Runtime has already displayed this context's notice.
                # The receipt of the packet this signal came from, read as fresh as the signal itself.
                source = binding(project).get("roles", {}).get(signal["context_role"], {})
                receipt = (source.get("delivery", {}).get("receipt")
                           if source.get("context", {}).get("packet") == signal.get("packet") else None)
                previous = {"signal": signal, "pane_id": role["pane_id"], "delivery": "visible_notice",
                            **({"receipt": receipt} if receipt else {})}
                delivered[signal_id] = previous
                deferred[signal_id] = signal
                write(state_path, state)
            if previous.get("signal") == signal and previous.get("pane_id") == role["pane_id"]:
                # Also recover a crash/failure between successful bridge persistence
                # and updating the original transport handle's observed fields.
                _mark_notified(project, signal, {"delivery": previous["delivery"], "pane_id": previous["pane_id"]})
                if signal_id not in deferred or not automation:
                    continue
                if verify_owner(client, role, project)["status"] not in {"idle", "done"}:
                    continue
            # This exact signal's notice is already visible: recheck, never re-notify.
            notified = (previous.get("signal") == signal and previous.get("pane_id") == role["pane_id"]
                        and previous.get("delivery") == "visible_notice")
            # Re-read original state immediately before initiating delivery;
            # fresh signals can also become obsolete during reconciliation.
            if not _signal_current(project, signal):
                if deferred.pop(signal_id, None) is not None:
                    write(state_path, state)
                continue
            # The attempt is persisted before its role claim, so a crash between
            # the two leaves a resolvable handle rather than an orphaned claim.
            attempts[signal_id] = {"signal": dict(signal), "pane_id": role["pane_id"], "status": "attempted"}
            write(state_path, state)
            if signal.get("context_role"):
                try:
                    claimed = _mirror(project, signal, role["pane_id"], "attempting", {"visible_notice", "prepared"})
                except ValueError:
                    claimed = None  # A launcher owns the role record; it decides delivery.
                if not claimed:
                    del attempts[signal_id]
                    write(state_path, state)
                    continue
            try:
                receipt = deliver(client, project, role, signal["prompt"], **({"renotify": False} if notified else {}))
            except (HerdrError, OSError) as exc:
                # Unknown send outcomes require reconciliation, never an automatic
                # second input submission in this invocation.
                attempts[signal_id].update(status="unknown", error=str(exc))
                if getattr(exc, "response", None):
                    attempts[signal_id]["native_response"] = exc.response
                write(state_path, state)
                settle(signal_id, signal, role["pane_id"], "unknown", error=str(exc))
                result.update(reason="unknown_requires_inspection", error=str(exc), pending_unknown=signal_id)
                return False
            if receipt.get("delivery") not in {"submitted", "visible_notice"}:
                attempts[signal_id].update(status="unknown", receipt=receipt)
                write(state_path, state)
                settle(signal_id, signal, role["pane_id"], "unknown")
                result.update(reason="unknown_requires_inspection", pending_unknown=signal_id)
                return False
            if receipt.get("revoke_automation"):
                from .runtime import control
                control(project, role_name, "human", binary)
                bound = binding(project)
                role = bound["roles"][role_name]
                automation = False
                for identifier, item in list(deferred.items()):
                    if (item.get("owner_role") or "main") == role_name:
                        del deferred[identifier]
            if receipt["delivery"] == "visible_notice" and automation:
                deferred[signal_id] = dict(signal)
            else:
                deferred.pop(signal_id, None)
            delivered[signal_id] = {"signal": dict(signal), "pane_id": role["pane_id"],
                                    "delivery": receipt["delivery"]}
            if getattr(client, "host", None) in {"orca", "rex"}:
                if notified and receipt.get("notice", {}).get("repeated"):
                    # A recheck raised no notice; keep the original one's receipt (and any alert error).
                    receipt["notice"] = previous.get("receipt", {}).get("notice", receipt["notice"])
                delivered[signal_id]["receipt"] = receipt
            submitted = receipt["delivery"] == "submitted"
            details = {"receipt": receipt} if submitted else {}
            if signal.get("context_role"):
                # Persisted with the attempt's removal, so a crash before the role
                # write-back still leaves a known outcome to replay.
                state.setdefault("settles", {})[signal_id] = {"signal": dict(signal), "pane_id": role["pane_id"],
                                                              "phase": receipt["delivery"], "details": details}
            del attempts[signal_id]
            write(state_path, state)
            updated = settle(signal_id, signal, role["pane_id"], receipt["delivery"], **details)
            if updated and submitted:
                bound = updated
            _mark_notified(project, signal, receipt)
            result["deliveries"].append({"id": signal_id, **receipt})
        return True

    first = True
    while first or time.monotonic() < deadline:
        first = False
        if stopped():
            break
        try:
            subscriptions = reconcile()
        except (HerdrError, OSError) as exc:
            result.update(reason="owner_or_server_unavailable", error=str(exc),
                          owner_state=getattr(exc, "owner_state", "unverified"))
            break
        if not check_signals():
            break
        if stopped():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        stream = client.events(subscriptions, timeout=min(interval, remaining))
        reconnect = False
        try:
            for event in stream:
                if stopped():
                    return result
                event_type = _event_type(event)
                if event_type == "events_lost":
                    reconnect = True
                    break
                if time.monotonic() >= deadline:
                    break
                if event_type == "pane.agent_status_changed":
                    result["events"] += 1
                    reconcile()
                    if not check_signals():
                        return result
                if time.monotonic() >= deadline:
                    break
        except (HerdrError, OSError, ValueError) as exc:
            # Includes events_lost surfaced as HerdrError by the raw client.
            reconnect = True
            result["last_transport_error"] = str(exc)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()
        if stopped():
            break
        if reconnect:
            result["reconnects"] += 1
            try:
                reconcile()
            except (HerdrError, OSError) as exc:
                result.update(reason="owner_or_server_unavailable", error=str(exc),
                              owner_state=getattr(exc, "owner_state", "unverified"))
                break
            # Back off disconnected streams without starting a model or daemon.
            delay = max(0, min(interval, deadline - time.monotonic()))
            if stop_event is None:
                time.sleep(delay)
            else:
                stop_event.wait(delay)
                if stopped():
                    break
    return result
