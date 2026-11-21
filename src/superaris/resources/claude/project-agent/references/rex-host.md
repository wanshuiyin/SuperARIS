# Rex terminal workbench

Use this entry when the prepared packet or current launch.json has `host: rex`.
The agent harness (Codex, Claude Code or AGY) is separate from the workbench host.
An older binding without a host field remains Herdr; do not migrate its team.

Read the project's existing startup instructions, recovery, role packet and
original task/memory files first. Product commands remain installed `superaris`
or the same interpreter's `python -m superaris`, including context, watch,
report, receiver and memory commands. Those commands target the original project
binding. For a new explicitly requested Rex project use `superaris start
/path/to/project --host rex`; inspect `--plan` before starting if needed.

Before operating the host, read `rex skill show` (or the installed `rex` skill)
and the relevant command's `--help` for the installed version. Rex calls a tab a
window and a pane a block. Verify the actual server instance, session, block,
foreground agent process and project cwd against launch.json (`rex_instance`,
`rex_session`, the role's `pane_id`, `pid` and `runtime_id`). Labels and the
`REX_SESSION`/`REX_BLOCK` variables of your own terminal identify where you run,
not which role you are; never use the focused block as an implicit target or
synthesize HERDR_ENV. Do not send input to your own block.

SuperARIS owns this project's role assignments, registered receipt handles,
scientific acceptance and next steps. Rex provides its workbench, terminal
delivery and the agent-reported OSC 7501 program status. Do not create a second
task ledger or a separate coordinator for the same work. Use the existing product
watch/report/receiver chain and original owner to continue authorized work.
A reported `working` or `done` state after a submitted prompt does not prove the
packet was read, an artifact exists or the result passed acceptance. Preserve
human drafts, permission waits and unknown delivery states; reconcile actual
terminal output and status before any resend. Changed owner/process/server
identity requires explicit handoff; do not replace the owner to keep receiving.

Preserve personal preferences, research wiki and task state in their existing
files. Re-read the current packet, recovery and originals after compact/restart.
Keep existing MCP routes, exclusive writer scopes, fresh independent reviewer
requirements, budgets and paused Goals. A persistent author session cannot
replace an independent reviewer. Workbench availability does not establish model
login, tool access or universal ARIS helper compatibility. Closing the Rex window
does not stop its server or blocks; inspect the bound receiver's actual status on
recovery.
