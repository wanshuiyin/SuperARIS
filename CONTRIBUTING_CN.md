# 参与贡献 SuperARIS

[English](CONTRIBUTING.md) · [项目首页](README_CN.md)

欢迎提交问题、小型复现、文档与翻译，以及工作台、客户端和运行时改进。通过 [Issues](https://github.com/wanshuiyin/SuperARIS/issues) 反馈问题或讨论修改，通过 [Pull requests](https://github.com/wanshuiyin/SuperARIS/pulls) 贡献代码。

## 反馈问题

请说明操作系统、Python 版本、工作台宿主（Herdr 或 Orca）、相关客户端（Claude Code、Codex 或 Antigravity）、实际命令、预期行为与实际结果。小型复现和简短脱敏日志比整段会话更有用。公开前请移除凭据、私有路径和科研数据。

## 准备本地工作副本

需要 Git 和 Python 3.10 或更新版本。先在自己的账号下 fork 仓库，克隆 fork，再创建聚焦本次修改的分支：

```sh
git clone https://github.com/YOUR-USERNAME/SuperARIS.git
cd SuperARIS
git switch -c fix/short-description
```

在隔离虚拟环境中构建并安装真实 wheel。安装包测试要求从 `site-packages` 加载，子进程测试也使用该环境的 Python；editable 安装或 `PYTHONPATH=src` 不能代替这一检查。

macOS / Linux：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install build pytest pipx
python -m build
python -m pip install --force-reinstall --no-deps dist/*.whl
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install build pytest pipx
python -m build
$wheel = (Get-ChildItem dist/*.whl).FullName
python -m pip install --force-reinstall --no-deps $wheel
```

所选启动器应使用 Python 3.10+。请让 `dist/` 只保留本次 wheel，旧 wheel 可移到其它目录。修改源码或包内资源后，在同一虚拟环境重新构建、安装，再检查改动。

## 验证改动

以下命令可在任一已激活的环境执行：

```sh
python -m superaris --help
python -m pytest -q tests/test_installed_package.py
```

随后只运行与改动相关的测试。运行时回归应利用已有合成项目和 fake transport 添加聚焦复现；错字或文档修改只需相关链接、渲染检查。平台覆盖以现有 [Linux/macOS 测试](.github/workflows/ci.yml) 和 [Windows 测试](.github/workflows/windows.yml) 为准；完整 Unix 套件包含 PTY 测试，不能直接当作原生 Windows 测试列表。

涉及打包或依赖时，可运行干净安装验证：

```sh
python scripts/verify_install.py "dist/*.whl"
```

它会创建临时 HOME 和虚拟环境、安装 wheel、下载固定版本的公开 ARIS 源码并执行 canonical helper，不调用付费模型。普通单元测试与 fake transport 测试无需模型凭据；安装测试可能使用 pip、Git 和包下载。原生演示可选，请使用自己的隔离项目和会话，不操作已有用户团队。

## 找到相关代码

- `src/superaris/`：CLI、向导、宿主适配、上下文与收件器。
- `src/superaris/resources/{claude,codex}/project-agent/`：随包分发的技能与共享引用镜像，修改相关内容时保持对应材料一致。
- `tests/`：回归、合成项目与 fake 宿主 transport。
- `docs/`：用户指南；`site/` 与 `assets/`：首页、演示与 README 媒体。
- `scripts/`：安装包和平台验证工具。

修改派工或恢复前，请读已有测试和[工作台指南](docs/WORKBENCH.md)。保留原负责人、角色／模型选择、未知投递状态与人工输入，避免重复派工或重复收件器。[上下文指南](docs/PROJECT_CONTEXT.md)和[结果／记忆指南](docs/RESULTS_AND_MEMORY.md)说明了现有合同。

## 提交 Pull Request

将修改提交并推送到自己的 fork，向 `wanshuiyin/SuperARIS` 的 `main` 发起 PR。使用自己的作者身份，保留其他贡献者的署名。说明具体问题、修改后的行为和实际执行的检查，包括尚未验证的平台。无关改动请分开，较大的变更先在 Issue 中讨论。

涉及用户文档时同步中英文。公开功能或修复上线时，在双语 README News 中加入真实日期和 PR／发布链接；尚未合并的修改不能写成已发布。保留项目的 [MIT 许可](LICENSE)和现有[来源声明](NOTICE)。
