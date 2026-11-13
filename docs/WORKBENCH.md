# Workbench and human handoff

Run `superaris` in an interactive terminal; `superaris start` without a project
opens the same wizard. Noninteractive input/EOF exits or displays usage without
starting a model. The wizard selects UI language, project, available clients,
models, layout and optional task before confirmation. The three recommended presets are shortcuts; **Custom team** chooses Codex, Claude Code or Antigravity independently for main, engineer and writer. Any one installed agent client is enough for a custom team; each role has a separate session and model choice. The visible `writer` role is **Research & Writing**. A new empty task waits.
UI language changes product text and new readable labels, not paper/task
language, native client UI or skill bodies. It is saved on confirmed startup
in the existing project binding; cancellation does not save a new preference.

When run from a bound project, the initial language default uses that binding;
from elsewhere it defaults to Chinese, with an explicit first-screen choice.
Existing projects offer continuation of their original owner, session, models,
roles and tasks. Existing labels/layout stay intact. Startup continues while
Herdr is attached after you handle actual native login/trust prompts. It never
answers them for you or blindly resends an unknown initial task.

The AGY model menu offers Gemini 4 Argon High (`gemini-4-argon-high`), Carbon
High (`gemini-4-carbon-high`) and Hydrogen High (`gemini-4-hydrogen-high`) for
any role, including main. Native CLI settings remain the default; manual IDs
are also available. Back retains the selected model, and existing teams keep
their recorded requests rather than adopting new menu choices.

## Explicit commands

`start PROJECT --plan` previews without starting native processes. Every new
preset defaults to main/engineer/writer: Codex/Codex/Codex, CC/Codex/CC, or
CC/Codex/AGY. Existing and pending teams retain their original membership on
ordinary reentry. Roles are responsibilities rather than client restrictions. For example, an AGY main can coordinate CC engineering and a separate AGY writer:

```bash
superaris start /path/to/project --role main=agy --role engineer=claude --role writer=agy --plan
```

Add `--host orca` for a new Orca project, and repeat `--model ROLE=MODEL` as needed. The main role owns goals, delegation, acceptance and follow-up; engineering usually goes to the engineer, but main can also execute or code within its authorization and write scope. Changing a new-team selection does not migrate existing owners. Use `--only-role` to explicitly select a subset, as below:

```bash
superaris start /path/to/project --session research-demo --preset cc-codex --only-role main --only-role engineer --write-scope main=notes --write-scope engineer=outputs/engineer --role-task 'engineer=Implement the assigned stage in outputs/engineer' --task 'Coordinate the existing project task' --plan
```

Use real existing project paths. Remove `--plan` when ready to launch. Repeat
`--skill NAME` for selected ARIS work; a workflow may bring its catalog-defined
children. `--model ROLE=MODEL` requests models only for new sessions. `--name`
sets a readable new-workbench title. Missing optional clients are unavailable,
not proof of a fully running team. Role scopes are instructions, not OS sandboxes.

For research and paper work, main can delegate methods, hypotheses, derivation
drafts and experiment suggestions to Research & Writing while engineering runs
a baseline. Main collects both deliveries, checks the evidence, adjusts the next
assignment, and brings evidence-backed writing to a fresh MCP reviewer. Any
configured client/model can hold these responsibilities. Writing and fresh review
remain different responsibilities. No requirement routes every MCP job into a
pane. New three-role workbenches place the owner left, engineer upper right and
writer lower right; adopted owner topology is preserved.

For SSH work, role write scopes refer to file ownership on the project host;
they do not require a new OS sandbox. Record the authorized remote host/path
and the existing environment in the original task separately. An existing
engineer owns remote setup and returns the first real result/log through the
project's original synchronization entry. See [SSH results](RESULTS_AND_MEMORY.md#ssh-results)
for receipt and troubleshooting handoff boundaries.

## Input ownership

Human-owned roles receive visible notices by default. `start --automation-owned`
marks new dedicated roles only; it never elevates an adopted owner. Explicitly
automation-owned Codex roles and Herdr AGY roles support automatic follow-up
when the original owner is idle and its verified input is empty. Herdr AGY uses
the existing live TUI and receiver; it does not start a second headless writer.
CC and Orca AGY follow-up remain notice-based. The input guard is best effort,
not atomic against concurrent human typing.

```bash
superaris control /path/to/project --role main --mode human
# After clearing human drafts and dedicating the role to automation:
superaris control /path/to/project --role main --mode automation
```

An observed draft revokes automation until explicitly re-enabled. Actual readback
resolves uncertain delivery, without repeated prompts or automatic resend:

```bash
superaris resolve-delivery /path/to/project --role main --resolution received --evidence notes/RECEIPT.md
```

Use `--resolution not-delivered` only after inspection confirms non-delivery.
For an uncertain bridge signal use `--handle ID` instead of the role. The evidence
file must exist in the project. Submitted context remains pending until explicit
received evidence; delivery does not establish scientific acceptance.

On reconnect, omitted task/skills/recovery/scope preserve the original inputs;
`--clear-recovery` explicitly empties recovery inputs. Main identity changes
require an ownership decision, not automatic takeover. Do not run competing
launchers against the same project or submit an existing human draft.
