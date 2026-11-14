# Dependencies and source selection

SuperARIS v0.1.0 requires Python ≥3.10 on macOS, Linux or native Windows.
Herdr carries visible sessions. Windows uses kernel file locks, named-pipe
transport and a detached receiver process; Unix uses `fcntl` and Unix sockets.
See [Windows setup and support scope](WINDOWS.md) for PowerShell installation
and the distinction between product compatibility and individual ARIS skills.

Install/login to the native CLIs selected for your team using their own
instructions. Executable detection is not an authentication or model probe.
On confirmed startup, missing Herdr can be installed through Homebrew where
available, or the official PowerShell installer on Windows. Language/project
selection, help, plans and cancellation do not install dependencies or fetch ARIS.
Native login and trust prompts are never automatically approved.

## ARIS is a separate source dependency

SuperARIS bundles its Claude Code/Codex project-agent resources. ARIS supplies
research skills, shared references, catalogs and canonical helpers. The default
public source is [Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
at MIT-licensed commit
[`8f493923f28c3f991dcca1287db97aa780d0969b`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/8f493923f28c3f991dcca1287db97aa780d0969b).
This pin includes the SSH synchronization and environment-reuse fixes merged in
[ARIS #497](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/497).

When confirmed startup or context preparation needs that source, the product
lazily downloads it to `$XDG_CACHE_HOME/superaris/aris/<commit>` or
`~/.cache/superaris/aris/<commit>` when XDG_CACHE_HOME is unset. Help, offline
plans, chooser screens and cancellation do not fetch ARIS. No model is called
by source acquisition. Network failure is reported rather than silently using
an unrelated checkout.

Use an explicit full ARIS checkout to work offline or retain a chosen version:

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
superaris start /path/to/project --aris-repo /path/to/aris --plan
superaris context /path/to/project --role main --aris-repo /path/to/aris --skill experiment-plan
```

PowerShell source selection uses an environment assignment:

```powershell
$env:SUPERARIS_ARIS_REPO = "C:\Research Tools\aris"
superaris
# Or select the source for one explicit command:
superaris start "C:\Research\项目" --aris-repo "C:\Research Tools\aris" --plan
```

The checkout must contain canonical `skills/`, host mirrors, `docs/` and `tools/`.
SuperARIS does not modify an explicit checkout to inject its bundled resource.
A bound project records `aris_repo` so future preparation preserves its selected
source. Existing host-correct skill customizations retain their source
precedence and provenance; the original project files remain authoritative.

Ambient `ARIS_REPO` is a canonical-helper variable, not an implicit SuperARIS
source selector. Likewise `~/.aris/repo`, the old adaptation tree and globally
installed skills are not prerequisites for the independent product. Use
`SUPERARIS_ARIS_REPO` or `--aris-repo` for product source selection. When a skill
needs a canonical ARIS helper, follow its host-correct resolver against the
selected checkout and set the actual helper root in that same shell invocation.
Do not derive a SuperARIS executable from `$ARIS_REPO/tools/`.

## Updates

### Update the installed application

Run these in an ordinary terminal, including a Herdr or Orca shell pane:

```bash
superaris update --check
superaris update
```

`--check` reads the actual installation and official Git main without installing
or changing project files. The update installs that exact commit with the
original environment's pip or pipx and verifies the installed commit afterward.
A new Git commit counts as an update even when both versions are still `0.1.0`.
Already-current installations are left alone. Source/editable/global Python
installs and unsupported pipx layouts are reported without resetting a checkout
or choosing another environment. Pipx needs `install --upgrade` support; update
pipx through its original installer if that command is unavailable.

Windows console launchers cannot replace themselves while running. The command
hands off to an external worker, prints its result/log paths, and exits. This
initial message means **handed off**, not completed. The result JSON records
`updated` with the actual installed revision, or `failed` with the error; the log
contains the package-manager output. After completion, `superaris update --check`
confirms the revision. On macOS/Linux, the terminal command waits and returns the
actual update result.

### One-time bootstrap for older installations

Older releases have no `update` command. Stop receiving for each running project
first (commands below), then use the original installer once:

```bash
# Existing pipx installation:
pipx install --force --pip-args=--force-reinstall "git+https://github.com/wanshuiyin/SuperARIS.git@main"

# Existing ordinary venv: activate that original environment first.
python -m pip install --upgrade --force-reinstall "git+https://github.com/wanshuiyin/SuperARIS.git@main"
```

Then use `superaris update` for subsequent updates. The bootstrap uses a forced
Git reinstall so an unchanged version number cannot skip new code.

### Refresh receiving for running projects

Installing code preserves native agents, original owners, project notes and
pending/unknown receipts. It does not hot-reload agent context. Update-aware
receivers retain their started revision and stop when the installation changes;
older receivers must be stopped explicitly. Neither is automatically restarted.
For each running project, use its original path:

```bash
superaris receiver "/path/to/project" --action stop
superaris receiver "/path/to/project" --action status
# Once stopped, after the update succeeds:
superaris receiver "/path/to/project" --action start
```

The existing owner is verified and the original receipt history is reused;
starting another receiver while the original lock is held is refused. Updating
SuperARIS does not update Herdr/Orca, agent CLIs, model/auth/MCP configuration or
a user-selected ARIS checkout.

### ARIS source updates

The preview's default ARIS pin does not track mutable upstream main. A later
SuperARIS version can update that pin. To choose another source now, explicitly
provide a valid checkout and preserve the project's existing owner, contracts,
budgets and pending work. Updating source does not mean current sessions have
read it; prepare the required context and explicitly read the selected skill.
No global skills, model settings or MCP configuration are rewritten.

Use `superaris` from the installed environment, or `python -m superaris` with
that environment's interpreter. Do not start a new-version receiver for a project
while a receiver from a legacy launcher is still active. The original local
launcher is not automatically replaced by installing this independent package.
