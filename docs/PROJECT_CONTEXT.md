# Skills, context and recovery

SuperARIS uses ARIS at three granularities: a full research pipeline, a workflow
or an individual skill. Each role receives `role.md`, `navigation.md`,
`recovery.md`, a local catalog snapshot and an exact `skill_index` identifying
its selected host-correct copies and dependency closure. Catalog descriptions
are navigation; read the actual `SKILL.md` and required references before acting.
A file being discoverable is not evidence the executing session read it.

For an already bound role, add context without sending native input:

```bash
superaris context /path/to/project --role main --skill research-pipeline
superaris context /path/to/project --role engineer --skill analyze-results
superaris context /path/to/project --role writer --skill research-refine
```

The `writer` role is Research & Writing. Main can prepare a research workflow
or individual skill for method discussion alongside the engineer's baseline.
The role reads the prepared skill and relevant references, delivers proposals
through the original task's `watch`/`report` path, and main decides the next
authorized work. Hypotheses stay distinct from verified findings. Later writing
uses accepted evidence and a fresh MCP reviewer; decisions and artifacts remain
in the original project memory.

Repeat `--skill` for additive selections. Preparation uses the binding's original
task, recovery, source and scope. `--task TEXT` changes this preparation only;
it does not replace the live assignment. `context` leaves binding, delivery and
unknown-delivery state unchanged and does not contact a model. A file-only agent
can ask its main owner to prepare the needed material.

`.aris/workbench/RECOVERY.md` points to the original project records and current
binding. `.aris/workbench/context/ROLE/LATEST_PREPARED.md` locates a preparation,
not an active, delivered or accepted task. Compare it with the binding and
original handoff before use.

A small role-neutral managed pointer follows native project instructions:
Codex `AGENTS.md` (an existing nonempty `AGENTS.override.md` takes priority),
CC `CLAUDE.md`, AGY `GEMINI.md`. Existing user text is retained. No global skills
or configuration changes are needed. Native discovery helps future startup;
a current session must explicitly reread the pointer, current role/navigation,
original task records and required skills. This is not permanent model memory.

Original wiki/task/memory files own facts, decisions, scope and acceptance.
Generated `.aris/workbench/` files hold transport and context, not a replacement
scientific ledger. Preserve paused Goals, budgets, model/MCP routes, fresh
reviewer isolation and publication permissions when resuming.
