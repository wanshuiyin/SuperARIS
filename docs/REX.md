# Rex workbench

SuperARIS can use [Rex](https://www.superlogical.com/rex/) as an optional workbench for its main, engineer and writer roles. Herdr remains the default, and existing Herdr or Orca projects keep their original team and recovery behavior. Rex runs each role as a native terminal block with the same ARIS navigation, skills, project files and MCP configuration; presets and **Custom team** work exactly as on the other workbenches.

Install and open Rex, then run `superaris`. For a new project the chooser lists every workbench it finds, with Herdr preselected. SuperARIS uses the `rex` command on PATH, or on macOS the CLI bundled in the app (`~/Library/Application Support/com.superlogical.rex/RexServer/Versions/Current/…/rex`). It talks only to the local Rex server: an inherited `REX_SERVER` route is ignored, and after the first start every call is pinned to the recorded server endpoint without starting a new server. Rex API revision 18 or newer is required.

| Action | Command |
|---|---|
| Open the project/workbench chooser | `superaris` |
| Inspect a new Rex project plan | `superaris start "/path/to/project" --host rex --plan` |
| Start the default three-role team in Rex | `superaris start "/path/to/project" --host rex` |
| Use AGY main, CC engineer and a separate AGY writer | `superaris start "/path/to/project" --host rex --role main=agy --role engineer=claude --role writer=agy` |
| Supply a specific Rex CLI | `superaris start "/path/to/project" --host rex --rex-bin "/path/to/rex"` |
| Resume the same project and original team | `superaris start "/path/to/project"` |
| Inspect the project's receiver | `superaris receiver "/path/to/project" --action status` |

## How roles are bound

A new team gets one Rex session named `SuperARIS · <name>`: main on the left, engineer upper right, writer lower right. An adopted owner (`--owner block:<id>`) stays in its own session and layout; new collaborators open in the SuperARIS session. A writer added after its engineer block closed splits from main. Each agent is the block's program, started from the same CLI path SuperARIS found, in the project directory. Quitting the agent closes its block.

Ownership is verified before every input: the server instance, the block and its host, the one recognizable agent among the foreground process and its ancestors, its pid and the project cwd. A CLI that renames itself while updating (for example `agy.<stamp>.old`) keeps its identity through the unchanged pid. Agent status comes from the OSC 7501 reports that Codex, Claude Code and Antigravity emit, and counts only when Rex attributes the report to that same pid. Anything else is `unknown`, which means notices only.

Delivery to an explicitly automation-owned Codex or AGY role pastes the prompt, presses Enter, and requires the same agent to report a new turn as working or done. Without that report, or if the agent reports a prompt instead, the attempt stays unknown for inspection and is never resent. Human-owned roles, Claude Code and any unverified input surface receive a notice instead: it is appended to `.aris/workbench/NOTICES.md` and raised as a desktop notification through a short-lived block that closes itself. An observed human draft revokes automation exactly as on Herdr.

`superaris start` without `--no-attach` focuses the main block and asks the Rex app to show its session. That needs Rex's Remote Control setting; when it is off SuperARIS prints the session to open instead and changes no settings.

## Limits

- A restarted Rex server loses its blocks. The recorded team is then reported as changed; SuperARIS does not adopt new processes in its place.
- An agent installed as a Node script appears to Rex as `node`. It is recognized once it reports its own OSC 7501 status; until then delivery waits.
- Local runtime only. Remote Rex hosts, blocks on other machines and the Rex Linux server without a desktop client are outside this integration.

## Validation

Native validation used Rex 0.1.0-preview.21 (API revision 18) on macOS with codex-cli 0.171.0. A two-role Codex team started in Rex. The receiver delivered both role packets once the agents were idle, delivered a registered report to main, which answered it, and kept a typed human draft untouched while revoking automation and raising a notice. Antigravity 1.5.8 and Claude Code status reports and multi-line paste were checked directly in Rex blocks, not in a full team run. Automated tests cover identity pins, status attribution, unconfirmed delivery, drafts, notices, event translation, layout, recovery and real receiver subprocesses against a simulated Rex CLI. Windows and the Rex app's own notification display were not tested.
