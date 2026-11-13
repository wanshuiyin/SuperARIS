# Project ownership, receipts and memory

## Restore before assigning

Read the actual project instructions, recovery entrypoint and current artifacts.
Keep personal preferences, project facts and task state in their existing owner
files. A correction, decision, delivery, failure or handoff is a reason to update
the relevant record with evidence and the next action. Do not create mandatory
`personal.md`, `COORDINATION.md`, a second research wiki or a new business task
ledger. Re-read user-edited files at the next relevant boundary; cached prompts
must not overwrite current facts.

The user designates the coordinator. Verify the bound workbench host and its real server/runtime, session,
pane/terminal or live agent handle, project cwd, task and owner before reuse. Role labels
alone are insufficient. Reuse the existing task mapping; record only the
transport/ownership facts it lacks: handle, checkout/branch, exclusive write
scope, current assignment, delivery/query path and next action. Git and native
session IDs are useful when present, not prerequisites for a project.

## Allocate substantive work

One owner retains intent, authorization, integration and final acceptance. That
owner can execute directly or delegate a whole workflow, a stage or a bounded
part. Choose the existing ARIS skill for the requested work and actually read
its instructions and relevant references in the executing host. A complete
pipeline remains a complete pipeline; a workflow or a single skill stays usable
on its own. Do not open a new agent for every skill.

A useful packet states the objective, necessary facts and sources, selected
skills, actual owner/handle, exclusive write scope, deliverable paths, acceptance
method, budget/permission limits and continuation/query handle. Use separate
worktrees or exclusive directories for concurrent writers. Hand off ownership
before integrating shared files. Do not send simultaneous MCP and workbench commands
to the same native session.

In a typical research cycle, main can register watch/report handles and run
stages in parallel across disjoint write scopes: engineer reproduces a baseline
or runs a pilot check while Research & Writing (`writer`) reads selected ARIS
skills (such as `research-refine`, `formula-derivation` or `experiment-plan`),
frames the problem, drafts candidate methods or derivations, and proposes
discriminating experiments. Untested assumptions and expected outcomes are
hypotheses. Return both deliveries through the original task's `watch`/`report`
path. Main reads the actual baseline logs and metrics alongside the proposal,
updates the original project record, and scopes the next experiment. With
accepted empirical evidence, writer structures the argument and drafts
substantial sections from results, formulas and citations (`paper-plan` /
`paper-write`). A fresh MCP reviewer examines the draft; main checks the
findings and assigns concrete revisions before integrating shared files.

Choose models from the user's configuration; Claude Code does not imply
DeepSeek. Add a figure specialist only when the output needs one, with the
appropriate existing figure skill and an exclusive artifact directory. Writer
and reviewer are separate roles. Keep original MCP routes, fresh-context
requirements, reviewer independence, acceptance gates, frozen commands and
budgets. A persistent author can continue; a fresh reviewer must still be fresh.
Codex reviewing Codex records `review_independence: same-family` and
`acceptance_status: provisional` where applicable.

## Delegate an SSH experiment

For an authorized remote experiment, give the existing engineer one concrete
work package before starting prolonged setup. The research-and-writing role
can advance independent methods and argument planning in parallel; use verified
facts for result claims. Record the SSH host alias, authorized remote directory, existing
user-confirmed environment and run command, first small real experiment,
local deliverable paths, original sync/status entry and budget/stop condition in
the original task. Reuse the environment and working entry; apply the original
experiment skill's checks when an actual environment or execution change needs
them. Main collects and verifies the first command, exit status, log and result;
it may still execute or code directly when needed and authorized.

At key milestones, have the engineer return a compact evidence package:
changed artifacts, actual command/exit status, result summary and original log
pointers, including prior validation that still applies. Main inspects the raw
evidence needed for the current acceptance question and reuses unchanged,
verified results; do not reread entire logs or recompute identical checksums
without a new change or question. Keep independent acceptance and the project's
required information isolation. If that isolation cannot run with available
permissions, escalate the requirement or prerequisite rather than bypass it.

Write scopes describe file ownership on the machine running the project, not a
requirement to build OS sandboxes. When the whole team runs remotely, that
machine is its local host. Authorize the SSH target and remote writes in the
same task; do not confuse a remote directory with a local `--write-scope`.
One engineer owns shared remote setup changes; other roles should not configure
the same environment concurrently. See [SSH results](receipts.md#ssh-results)
for bringing remote evidence back to the original receiver.

Carry failed commands, repair attempts and the remaining agreed budget through
child skills and handoffs; changing skills does not reset them. When the task's
allowed attempts are exhausted or the same blocker repeats without new
progress, stop repeating expensive preparation. Hand main the actual error,
last command/exit status, attempted fixes and next viable path so it can take
over or re-scope. An external permission, network, authentication or driver
failure alone is not a reason to rewrite training code. Keep the original
skill's sanity/reimplementation limits and scientific acceptance gates; this
adds no price threshold, automatic model downgrade or background monitor.

## Receive and continue while the project runs

Use an existing native callback when it supplies real completion/failure
receipts. Otherwise use the project's limited receipt/event bridge, bound to the
original project, owner session and registered worker handles. The bridge is
transport, not scientific judgment. Keep each MCP's job/thread protocol;
Workbench `idle`/`done`, a CLI exit and a model's self-report are prompts to inspect
actual files, command exit codes and completed reviewer responses.

On a result, failure, stalled task, new reply or relevant file update: read the
actual evidence, apply the original acceptance criteria, continue the next
already-authorized step with the existing owner, then update its original
record. Keep a pending item's owner, expected result and query/continuation
handle recoverable. If the same obstacle persists without progress, inspect
the real failure and take over or re-scope the concrete gap; do not leave a
finished deliverable waiting for an unrelated batch. Notify the user when a
result is useful or a real decision is required; do not use idle LLM polling.

Automatic prompt submission is appropriate only for a newly created or
explicitly automation-owned role whose input safety is established. For an
existing human-owned pane or uncertain input state, show a visible receipt
notice and leave its draft untouched. Never press Enter to submit an unknown
human draft. A notification alone must not be reported as an executed follow-up.

After a disconnect, restart or `events_lost`, re-subscribe and reconcile the
actual snapshot, original handles and output files. Confirm whether the prior
operation happened before repeating a write or paid invocation. Where file
notifications are unavailable, check current files at read/write and recovery
boundaries; do not promise whole-project real-time observation. The receiver subprocess survives launcher exit and UI detach, including
`--no-attach`, while bound to the original project/main identity. It stops on
that main ending/changing, server unavailability or explicit stop; it does not
rebuild or follow a replacement owner. Cross-machine memory synchronization and
exactly-once execution across crashes remain outside this version's guarantee.

## Preserve boundaries

Starting or reconnecting a workbench does not create/resume a Goal, start a
production batch, publish, merge or enlarge a budget. Paused work stays paused.
Goal Pulse keeps its own purpose and thread binding; it is not the receipt
queue. Preserve the user's existing model selection and project permissions.
When a needed capability is absent or ownership conflicts, report the specific
blocker and continue independent authorized work. No global permanent daemon or mandatory coordinator pane is required.

## Executable receipt and memory path

Use [receipts.md](receipts.md) for the confirmed CLI chain, original-record
pointers, the project/original-main-bound receiver and explicit `remember` events. The CLI
never parses arbitrary Markdown into tasks, infers memory updates or replaces
MCP-specific query/status protocols. Human-owned roles default to visible
notices. Explicitly automation-owned Codex and Herdr AGY can continue when
idle with a verified empty input; CC and Orca AGY remain notice-based. These
input guards are best effort, not atomic human-input protection. These behaviors and the complete three-host native validation are
separate claims; a preset or offline plan does not prove all hosts were tested.

Use explicit `control` for a persisted human/automation handoff; startup's
`--automation-owned` applies to new roles only. An observed draft revokes
that automation grant until explicitly re-enabled. Resolve unknown deliveries
from readback via `resolve-delivery`; even a submitted context stays pending
until received evidence is recorded. Delivery receipt never replaces the
original acceptance gate. See [receipts.md](receipts.md) for syntax.
