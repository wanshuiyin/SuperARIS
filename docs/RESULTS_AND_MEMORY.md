# Registered results and explicit memory

A main owner can follow an entire workflow or delegate a bounded part with
exclusive writing areas, deliverables and original acceptance criteria. Keep
the original task record; transport handles are pointers, not a new scientific
state machine. These examples assume an existing `notes/WORK.md` and bound
`main`/`engineer` roles. Use actual project paths and register before reporting.

```bash
superaris watch /path/to/project --id result-check --owner-role main --worker-role engineer --record notes/WORK.md --deliverable outputs/engineer/RESULT.md --wait-for 'Result file and report' --query 'original worker continuation/status entry' --next 'Read the result, apply the original check and update notes/WORK.md'

# Worker after writing the actual output:
superaris report /path/to/project --id result-check --outcome completed --message 'Result ready in outputs/engineer/RESULT.md; inspect it and the original checks'

superaris receiver /path/to/project --action status
```

`report` also accepts `failed`, `blocked` and `reply`. Herdr events, file changes
and reports prompt inspection; they do not establish acceptance. `--query` is a
displayed original-protocol pointer, never shell-executed. Existing MCP job/thread
protocols and reviewer freshness remain intact; omit `--worker-role` for an
external worker and retain its original query handle. Never send conflicting
MCP and Herdr instructions to the same native session.

The project/original-main-bound receiver survives UI detach and `--no-attach`.
It stops on main identity ending/changing, Herdr unavailability or explicit stop.
It creates no new owner and does not rebuild the server. `--no-receiver` persists
an opt-out; `receiver --action start` explicitly re-enables it. Manual `listen`
is a bounded diagnostic and refuses a second receiver while the managed one is
active. Human-owned inputs get notices, not automatic execution.

After a disconnect, inspect actual handles and files before repeating writes or
paid calls. A deferred prompt must not override newer task/owner evidence.

```bash
superaris reconcile /path/to/project
# Owner closes the transport wait after the original evidence is sufficient:
superaris acknowledge /path/to/project --id result-check --evidence notes/WORK.md
```

Acknowledgement requires an existing evidence file and does not grant scientific
PASS. Keep the handle active while still waiting. Unknown delivery uses
[explicit readback resolution](WORKBENCH.md#input-ownership), not blind retries.

## SSH results

Assign remote experiment work to the existing engineer with its SSH host,
authorized remote directory, user-confirmed environment/working command, first
small real experiment, local result/log paths and original sync/status entry in
the task record. Main actually dispatches and checks that first result.
Research & Writing can develop independent methods and arguments in parallel;
result claims use accepted facts. Main can still execute or code within its authority.
Reuse the existing environment and entry, applying the original experiment
skill's checks to actual changes.

Use the `watch` → `report` chain above for the returned local artifacts. The
receiver observes its host's registered files and reports; it does not watch
arbitrary SSH paths, execute `--query` or copy remote files. If the whole team
runs remotely, its project/receiver paths refer to that host. The original
worker must synchronize the actual result and command/exit-status log through
the project's existing entry. A remote-only result or `completed` report is not
acceptance; if retrieval is blocked, report `blocked` or `reply` with the
original query pointer and retain the wait.

Carry prior failures, attempted fixes and the remaining agreed budget across
skills and handoffs. When the task's attempts are exhausted or the same blocker
repeats without progress, hand main the actual error and next viable path;
do not restart the same costly preparation or rewrite training code merely
because of an external permission/network/authentication/driver failure.
Original skill retry/acceptance limits, CC/AGY notices, dedicated Codex input
guards and MCP protocols remain. This introduces no timer, price threshold,
automatic model change or new task ledger.

## Existing memory, explicit events

The authorized owner can update its original records directly or append an event:

```bash
superaris remember /path/to/project --file notes/PROGRESS.md --kind delivery --scope 'existing results task' --source outputs/engineer/RESULT.md --text 'Result checked against the original criterion; next action is in notes/WORK.md'
```

The destination must already exist. Kinds are correction, decision, delivery,
failure and handoff. The command appends the supplied event; it does not infer
preferences, verify its truth or update a wiki graph automatically. Optional
`--expected-mtime-ns` uses the owner's most recent read to detect intervening
edits; reread on mismatch. Receiving and memory updates do not resume a Goal,
raise a budget or authorize publication/merge. Goal Pulse keeps its own purpose.
