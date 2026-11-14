# Contributing to SuperARIS

[简体中文](CONTRIBUTING_CN.md) · [README](README.md)

Thanks for helping improve SuperARIS. Bug reports, small reproductions, documentation and translation, and workbench/client/runtime improvements are welcome. Use [Issues](https://github.com/wanshuiyin/SuperARIS/issues) to report a problem or discuss a change, and [Pull requests](https://github.com/wanshuiyin/SuperARIS/pulls) to contribute it.

## Report a problem

Include your OS, Python version, workbench host (Herdr or Orca), affected client (Claude Code, Codex or Antigravity), exact command, expected behavior and actual result. A small reproduction and a short redacted log are more useful than an entire session. Remove credentials, private paths and research data before posting.

## Set up a local checkout

Use Git and Python 3.10 or newer. Fork the repository under your own account, clone your fork, and create a focused branch:

```sh
git clone https://github.com/YOUR-USERNAME/SuperARIS.git
cd SuperARIS
git switch -c fix/short-description
```

Build and install a real wheel into an isolated virtual environment. The installed-package tests require `site-packages`, and subprocess tests use that environment's Python; an editable install or `PYTHONPATH=src` is not an equivalent check.

macOS / Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install build pytest pipx
python -m build
python -m pip install --force-reinstall --no-deps dist/*.whl
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install build pytest pipx
python -m build
$wheel = (Get-ChildItem dist/*.whl).FullName
python -m pip install --force-reinstall --no-deps $wheel
```

Use a Python 3.10+ installation for the selected launcher. Keep one current wheel in `dist/`; move stale wheels elsewhere if needed. After editing source or packaged resources, build and install again in the same environment before checking the change.

## Check your change

These commands work in either activated environment:

```sh
python -m superaris --help
python -m pytest -q tests/test_installed_package.py
```

Then run the tests relevant to your change. For runtime regressions, add a focused reproduction using the existing synthetic projects and fake transports. A typo or documentation change needs the relevant link/render checks, not a runtime suite. See the actual [Linux/macOS suite](.github/workflows/ci.yml) and [Windows suite](.github/workflows/windows.yml) for platform coverage; the full Unix suite includes PTY tests that are not the native Windows test list.

For packaging or dependency changes, the clean-install consumer is:

```sh
python scripts/verify_install.py "dist/*.whl"
```

It creates its own temporary HOME and virtual environment, installs the wheel, fetches the pinned public ARIS source, and executes a canonical helper without calling a paid model. Ordinary unit/fake-transport tests do not need model credentials. Installation tests can use pip, Git and package downloads. Native demos are optional: use your own isolated project/session rather than an existing user's team.

## Find the relevant code

- `src/superaris/`: CLI, wizard, host adapters, context and receiver.
- `src/superaris/resources/{claude,codex}/project-agent/`: bundled skill and shared-reference mirrors; keep corresponding material aligned when editing it.
- `tests/`: regressions, synthetic projects and fake host transports.
- `docs/`: user guides; `site/` and `assets/`: homepage, demos and README media.
- `scripts/`: installed-package and platform verification tools.

Read the existing tests and [workbench guide](docs/WORKBENCH.md) before changing dispatch or recovery. Preserve the original owner, role/model choices, unknown delivery state and human input; avoid duplicate dispatch or receivers. The [context guide](docs/PROJECT_CONTEXT.md) and [results/memory guide](docs/RESULTS_AND_MEMORY.md) explain the existing contracts.

## Send a pull request

Commit and push your branch to your fork, then open a PR against `wanshuiyin/SuperARIS`'s `main`. Keep your own author identity and preserve other contributors' attribution. Describe the concrete problem, resulting behavior and checks you actually ran, including any untested platform. Keep unrelated changes separate and discuss substantial changes in an Issue first.

Keep English and Chinese user documentation aligned where affected. When a public feature or fix ships, include a dated bilingual README News entry with its real PR/release link; an unmerged change is not already released. Preserve the project's [MIT license](LICENSE) and existing [attribution notices](NOTICE).
