[![SuperARIS — Your personal research agent with ARIS (Auto Research In Sleep), powered by a team of agents.](assets/superaris-banner.png)](https://wanshuiyin.github.io/SuperARIS/)

**SuperARIS — Your personal research agent with ARIS (Auto Research In Sleep, ~20k stars), powered by a team of agents.**

[![Homepage](https://img.shields.io/badge/Homepage-Live%20demo-0969da?style=flat)](https://wanshuiyin.github.io/SuperARIS/) [![Quick Start](https://img.shields.io/badge/Quick%20Start-Herdr%20%2B%20Orca-2da44e?style=flat)](#quick-start) [![Guides](https://img.shields.io/badge/Guides-Docs-0d9488?style=flat)](#guides) [![Preview v0.1.0](https://img.shields.io/badge/Preview-v0.1.0-6e7781?style=flat)](pyproject.toml) [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-8250df?style=flat)](README_CN.md)<br>[![Built on ARIS](https://img.shields.io/badge/Built%20on-ARIS-455299?style=flat)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) [![Cite ARIS](https://img.shields.io/badge/Cite%20ARIS-BibTeX-556b52?style=flat)](#cite-aris) [![MIT License](https://img.shields.io/badge/License-MIT-555555?style=flat)](LICENSE) [![Join Community](https://img.shields.io/badge/Join%20Community-ARIS-07a65a?style=flat)](#community)

[![Research teamwork in action — English animated preview](assets/demo-en.gif)](https://wanshuiyin.github.io/SuperARIS/media/demo-en.mp4)

**[▶ Watch the full 1080p demo · ≈21 seconds](https://wanshuiyin.github.io/SuperARIS/media/demo-en.mp4)**

*Animated preview · click to play the full video. Illustrative project and data.*

**Orca multi-model team:** [Interactive homepage](https://wanshuiyin.github.io/SuperARIS/?host=orca#workbench) · [English video](https://wanshuiyin.github.io/SuperARIS/media/orca-multi-demo-en.mp4) · [中文视频](https://wanshuiyin.github.io/SuperARIS/media/orca-multi-demo-zh.mp4). The [single-model team (3 Codex agents)](https://wanshuiyin.github.io/SuperARIS/orca-demo/?team=codex&lang=en) and its original [English](https://wanshuiyin.github.io/SuperARIS/media/orca-demo-en.mp4)/[中文](https://wanshuiyin.github.io/SuperARIS/media/orca-demo-zh.mp4) videos remain available.

## Quick Start

Have Python 3.10+, Git and [pipx](https://pipx.pypa.io/stable/installation/) ready, plus your chosen agent CLIs (`codex`, `claude`, `agy`) with model access configured. Install once, then open the wizard:

```bash
pipx install "git+https://github.com/wanshuiyin/SuperARIS.git"
superaris
```

Choose your language, project, workbench, team and models. Existing Herdr or Orca installations are reused.

For an explicit start, open a new project's directory and choose one workbench:

| Workbench | Start in the current project | Setup guide |
|---|---|---|
| **Herdr (default)** | `superaris start . --host herdr` | [Workbench and startup](docs/WORKBENCH.md) · [Windows](docs/WINDOWS.md) |
| **Orca (optional)** | `superaris start . --host orca` | [Orca setup](docs/ORCA.md) |

For Orca, install and open the [official app](https://www.onorca.dev/) first; if its CLI is unavailable, register it in **Settings → General → Orca CLI**. Reopening an existing project keeps its recorded workbench and team. [More installation options ↓](#install-and-open)

## News

- **2026-11-13** — **Bring Gemini into research from the start:** the expanded Research & Writing role spans ideas, methods and substantive paper writing, with new Carbon/Hydrogen model choices. Explicitly automation-owned AGY sessions on Herdr can pick up reports and continue in the same conversation. ARIS workflows, skills and MCP collaboration remain available ([#5](https://github.com/wanshuiyin/SuperARIS/pull/5), [#6](https://github.com/wanshuiyin/SuperARIS/pull/6)).
- **2026-11-13** — Fixed partial team recovery: selecting members with `--only-role` now preserves recorded custom roles, clients and requested models, including interrupted startups ([#4](https://github.com/wanshuiyin/SuperARIS/pull/4)).
- **2026-11-11** — Improved SSH experiment guidance: explicit handoffs, milestone-based verification and bounded troubleshooting. The default ARIS revision now includes source/config sync and working-environment reuse fixes ([#3](https://github.com/wanshuiyin/SuperARIS/pull/3), [ARIS #497](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/pull/497)).
- **2026-11-09** — Choose each role's client and model with Custom team, including AGY-led teams without Codex ([#2](https://github.com/wanshuiyin/SuperARIS/pull/2)).
- **2026-11-09** — Inspect local usage by role and client with `superaris usage` ([#1](https://github.com/wanshuiyin/SuperARIS/pull/1), [guide](docs/USAGE.md)).
- **2026-11-09** — Use the optional Orca workbench and compare multi-model / three-Codex demos ([setup](docs/ORCA.md), [interactive demo](https://wanshuiyin.github.io/SuperARIS/?host=orca#workbench)).

## Overview

Discuss a research goal with your personal agent. It organizes a persistent team, delegates work, checks incoming results, and keeps track of what should happen next. Join any teammate's session to explore an idea, refine a draft, or take over.

Built on [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (Auto Research In Sleep, ~20k GitHub stars), SuperARIS equips each role with the research workflows and project context it needs. The team works within one project, with clear responsibilities and a record you can return to tomorrow.

## One personal agent, a persistent team

Your main agent holds the research direction and coordinates the work. Codex can implement experiments and check evidence; Gemini can discuss the argument and write substantial paper sections. The main role can also execute or code directly within its authorized scope. Each collaborator has its own ongoing session, so you can work directly with the teammate you need and continue the discussion where you left off.

Every new team has three roles: main, engineer and **Research & Writing** (`writer`). Recommended presets offer an all-Codex team, Claude Code main/writer with Codex engineering, or Claude Code / Codex / Antigravity. Choose **Custom team** in the wizard to assign Codex, Claude Code or Antigravity to each role independently, including an AGY main and teams without Codex. Each role keeps its own model choice and session. For any AGY role, the wizard offers Gemini 4 Argon High, Carbon High and Hydrogen High alongside manual IDs; keeping the native CLI settings remains the default. Temporary MCP workers and fresh reviewers remain available alongside the persistent team.

The research-and-writing role can define problems, develop candidate methods and derivations, suggest experiments that distinguish hypotheses, and write the paper. For example, main delegates method discussion alongside a baseline experiment, checks the returned evidence, adjusts the next assignment, then collects evidence-backed writing for a fresh MCP review. Proposals and decisions stay in the existing project record. This responsibility works with any configured client or model.

## ARIS for every teammate

Each role receives its task, working area, ARIS navigation, and the relevant skills to read before acting. Ask the main agent to run a complete pipeline, delegate a connected workflow, or use one skill for a focused task.

| What you need | ARIS entry |
|---|---|
| Carry a research project from idea to paper | [research-pipeline](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-pipeline/SKILL.md) |
| Develop and test a research direction | [idea-discovery](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md) |
| Implement the experiment plan and collect results | [experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/experiment-bridge/SKILL.md) |
| Review, revise, and check the research again | [auto-review-loop](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/auto-review-loop/SKILL.md) |
| Turn checked findings into a paper | [paper-writing](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/paper-writing/SKILL.md) |

These use your configured tools and keep ARIS's review and acceptance criteria. [Skills and project context →](docs/PROJECT_CONTEXT.md)

## Follow up on the work

SuperARIS tracks registered tasks, result files, and reports while the original main session is running—even after you close the workbench window. Your main agent uses those updates to collect finished work, check the evidence, and continue the next authorized step.

Human-controlled sessions receive notices. Explicitly automation-owned Codex sessions and Herdr AGY sessions can continue automatically when idle with a verified empty input; CC and Orca AGY use notices. [Receiving results and continuing work →](docs/RESULTS_AND_MEMORY.md)

[![SuperARIS proactive collaboration: team and MCP reports reach the receiver, the original main agent verifies results and continues authorized work, and project records support recovery (Chinese labels).](assets/proactive-mechanism-zh.png)](assets/proactive-mechanism-zh.png)

*How the team, receiver, main agent and project records connect (Chinese labels). Click to view full size.*

## Long-term project memory

Keep the project's goals, decisions, corrections, results, and next actions in its existing notes and research wiki. Agents update these records as the work progresses and read them back when resuming. The context stays with the project across days and sessions, in files you can inspect and edit.

Reopen a running team to continue its conversations, or give a new session the project's recovery entry. [Context and recovery →](docs/PROJECT_CONTEXT.md)

[![SuperARIS project memory: today’s team updates project files, and later sessions read them back to check the current task and actual artifacts (Chinese labels).](assets/project-memory-zh.png)](assets/project-memory-zh.png)

*Project files carry progress into later sessions (Chinese labels). Click to view full size.*

## Install and open

Requires Python 3.10+ on macOS, Linux or Windows, [Herdr](https://herdr.dev) (default) or [optional Orca Terminal v1](docs/ORCA.md), and your chosen native CLIs (`codex`, `claude`, `agy`) with model access configured.

```bash
pipx install 'git+https://github.com/wanshuiyin/SuperARIS.git'
superaris
```

Choose the interface language, project, team, and models, then confirm the workspace. Give the main agent a task, or open the team and discuss what to do next. The interface language is independent of your paper or task language.

| Recommended preset | Main | Engineer | Research & Writing |
|---|---|---|---|
| Codex | Codex | Codex | Codex |
| Claude Code + Codex | Claude Code | Codex | Claude Code |
| Claude Code + Codex + Antigravity | Claude Code | Codex | Antigravity |

The presets are shortcuts, not role restrictions. For example, choose AGY main, CC engineering and AGY writing in **Custom team**, or use:

```bash
superaris start /path/to/project --role main=agy --role engineer=claude --role writer=agy
```

Add `--host orca` for a new Orca project, or `--model ROLE=MODEL` for individual model requests. The two AGY roles have separate sessions. CC and Orca AGY follow-up remains notice-based. On Herdr, explicitly automation-owned AGY can continue through its verified empty idle composer, alongside existing guarded Codex automation.

New workbenches use the same three-pane layout. Existing teams and pending startup choices stay intact; `--only-role` selects an explicit subset.

SuperARIS obtains its pinned ARIS resources when needed. Existing ARIS installations and custom skills can be used through the documented source selection. [Dependencies and updates →](docs/DEPENDENCIES.md)

<details>
<summary>Other installation options and an existing ARIS checkout</summary>

Local wheel (including offline installation):

```bash
python3 -m pip install --no-index --no-deps /path/to/superaris-0.1.0-py3-none-any.whl
python3 -m superaris
```

Checkout in an isolated environment:

```bash
git clone https://github.com/wanshuiyin/SuperARIS.git
cd SuperARIS
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/superaris
```

Select an existing ARIS source explicitly:

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
```

Help, plans and wizard cancellation do not fetch ARIS. See [source selection](docs/DEPENDENCIES.md) for the fixed revision, local cache and existing receiver compatibility.

</details>

## Windows

Use native Windows Terminal / PowerShell with Python 3.10+ and Git:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
# Open a new terminal after ensurepath.
pipx install "git+https://github.com/wanshuiyin/SuperARIS.git"
superaris
```

The confirmed startup can install missing Herdr using its official Windows installer. Native CLI login and trust remain interactive. A local wheel also works without Git. See [Windows setup, recovery, and support scope](docs/WINDOWS.md).

## Guides

- [Optional local usage](docs/USAGE.md):`superaris usage PROJECT --by-role --json`

- [Windows setup and support scope](docs/WINDOWS.md)
- [Workbench, roles, and human handoff](docs/WORKBENCH.md)
- [Skills, context, and recovery](docs/PROJECT_CONTEXT.md)
- [Follow-up and project memory](docs/RESULTS_AND_MEMORY.md)
- [ARIS source, dependencies, and updates](docs/DEPENDENCIES.md)

<a id="community"></a>

## Community

SuperARIS shares the [ARIS research community](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep#community). Join the same WeChat group to discuss agent collaboration and AI research workflows. The QR code below is maintained upstream by ARIS.

<img src="https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/docs/wechat_group.jpg" alt="ARIS shared research community WeChat QR code" width="300">

## Cite ARIS

SuperARIS builds on ARIS's research workflows, review mechanisms, and project knowledge. If you use this foundation in your research, please cite the [ARIS technical report](https://arxiv.org/abs/2605.03042):

```bibtex
@article{yang2026aris,
  title={ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration},
  author={Yang, Ruofeng and Li, Yongcan and Li, Shuai},
  journal={arXiv preprint arXiv:2605.03042},
  year={2026}
}
```

Thanks to [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) for the research foundation and [Herdr](https://herdr.dev) for the persistent native sessions. SuperARIS is [MIT licensed](LICENSE); source attribution is preserved in [NOTICE](NOTICE).
