# Native Windows setup

SuperARIS supports a native Windows Terminal / PowerShell installation with
Python 3.10+, Herdr and the native CLIs chosen for the team. WSL is optional
for workflows that need a Linux environment. The same three-role presets,
per-role model choices and project recovery records apply.

## Install and open

Install Python with the Windows `py` launcher available. For installation from
the repository, also install Git and make it available on PATH. In PowerShell:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Open a new terminal so PATH changes take effect, then run:

```powershell
pipx install "git+https://github.com/wanshuiyin/SuperARIS.git"
superaris
```

A downloaded local wheel does not need Git:

```powershell
pipx install "C:\Downloads\superaris-0.1.0-py3-none-any.whl"
superaris
```

The wheel installs the product; first use of ARIS resources still needs network
access unless a complete local ARIS checkout is selected. For an offline pipx
installation, its build/runtime dependencies must also be locally available.

Choose language, project, team and models, review the summary, then confirm.
Language/project selection, `--help`, `--plan` and cancellation do not install
Herdr or fetch ARIS. On confirmed startup, missing Herdr can be installed using
the [official PowerShell installer](https://herdr.dev/tui/docs/install/).
You may instead install it yourself:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://herdr.dev/install.ps1 | iex"
```

The installer uses the stable channel by default. When using the manual Windows
zip, keep its extracted directory together: `herdr.exe` needs the accompanying
ConPTY runtime. Reopen the terminal if PATH has changed.

Install the selected `codex`, `claude` and/or `agy` CLI using that vendor's native
Windows instructions, then complete its own login and model configuration.
SuperARIS does not approve login/trust prompts or rewrite model/MCP settings.
Finding the executable confirms only that it is available on PATH.

## Update from PowerShell

Use `superaris update --check`, then `superaris update`. The Windows launcher
hands off to an external worker so its executable can be replaced; its initial
success code acknowledges that handoff. Read the printed result/log paths for
the actual installed commit or failure, then run `--check` again. Existing
pipx copied launchers are supported; Developer Mode or symlink permission is
not required. See [updates, one-time bootstrap and per-project receiver refresh](DEPENDENCIES.md#updates).

## Paths, source selection and recovery

Use quoted Windows paths, including paths with spaces or Chinese characters:

```powershell
superaris start "C:\Research\我的项目" --preset codex --plan
$env:SUPERARIS_ARIS_REPO = "C:\Research Tools\aris"
superaris
```

The environment variable is optional; by default SuperARIS obtains its pinned
ARIS source when needed. A local source must be a complete checkout, including
skills, host mirrors, catalogs and canonical helpers. See
[source selection and cache locations](DEPENDENCIES.md).

Rerun `superaris` and select the same bound project to recover its original
team and pending choices. Keep the original owner and unknown delivery state;
an uncertain prompt is not automatically resent. Native login or trust waits
must be cleared in the relevant CLI. Closing the attached workbench leaves the
receiver and original running team available. Receiver continuation depends on
the original owner and server remaining alive; rebooting or stopping that server
is different from detaching. Do not run a legacy receiver and the installed
product's receiver against the same active project.

## Main pane returns to PowerShell / 主控退回终端

A pane title such as **Main · Claude Code** names its role; it is not a liveness
indicator. If `hi` or `/` is handled by PowerShell, the pane is currently a shell.
That alone does not establish why the native client stopped or failed to start.
SuperARIS pauses receiving when it cannot verify the original main. It records
the failure and attempts one workbench notification; if the host itself is
unreachable, the diagnostic remains available on disk. Busy clients and native
login/trust waits with the original process are not treated as exits.

主控标题只是角色名。如果 `hi` 或 `/` 被 PowerShell 当作命令执行，当前界面就是
Shell，需先查看此前客户端错误。收件器会保留原团队和任务、记录失败并尝试一次通知；
连接或权限异常只提示无法核实，不据此认定客户端已退出。

From a separate PowerShell terminal, inspect the existing diagnostic:

```powershell
superaris receiver "D:\research-project" --action status
Get-Content -LiteralPath "D:\research-project\.aris\workbench\receiver.json"
```

If startup did not complete, also inspect `.aris/workbench/startup-error.json`
when present. Resolve the actual client/connection error first. If the original
main process is still alive and can be verified again, explicitly resume receiving:

```powershell
superaris receiver "D:\research-project" --action start
```

A newly launched client has a new process identity: ordinary `superaris` reentry
rejects it, and `--owner` does not replace an already recorded main. There is
currently no in-place main-replacement command. Preserve the records and resolve
an explicit ownership handoff rather than deleting `.aris` or replaying unknown
tasks. No command is automatically typed into the shell.

请从另一个 PowerShell 查看上述状态和错误文件。只有原主控进程仍活着且重新通过核实后，
才用 `receiver --action start` 恢复收件。重新启动客户端会改变进程身份，不能靠裸
`superaris` 或 `--owner` 覆盖原绑定；当前没有原地替换主控命令。请保留记录，明确交接
负责人，不删除 `.aris`、不重发未知任务，也不向 Shell 输入科研任务。

## Support and verification scope

The product's platform boundary uses Windows kernel file locks, raw
newline-delimited JSON over Herdr named pipes, and a detached receiver subprocess.
It preserves single-listener ownership and delivery/recovery rules. Herdr's
[Windows support documentation](https://herdr.dev/tui/docs/windows-beta/)
describes native ConPTY panes and PowerShell attach; its
[socket API documentation](https://herdr.dev/tui/docs/socket-api/) defines the
transport. These upstream capabilities do not by themselves validate SuperARIS.

Validation has distinct layers: product unit tests with synthetic transport;
Windows runner installation, process/lock/pipe and recovery checks; an isolated
real-Herdr smoke test without a model; and interactive native CLI experience.
A passing layer establishes only its exercised paths. The Windows CI run and
its logs are the evidence for automated checks; this guide does not claim a
complete interactive three-client/model run or paid-model validation.

ARIS skills retain their own dependencies. A skill may require Bash, Unix tools,
SSH, Docker, GPU software, LaTeX or a particular remote host. Read that skill's
requirements before execution; use a suitable host or WSL for those workflows.
Native product support does not mean every upstream skill or helper has been
ported to Windows. Herdr also documents platform-specific terminal and live-cwd
limitations; retain identity verification when those observations are incomplete.
