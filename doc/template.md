# Python Project Template

A reusable template for Python projects using uv and Ruff.

This repository is intentionally a template, so you can copy it for new Python work.

## Typical workflow

1. Create a new repository from this template (see [Using this repo as a GitHub template](#using-this-repo-as-a-github-template)) or copy/clone it directly.
2. Run `scripts/init.sh` and enter your new project name when prompted.
3. Add your application code under `src/`.
4. Add tests under `tests/`.
5. Run linting and formatting before committing.

## Using this repo as a GitHub template

This repository is marked as a GitHub template, so you can create a new, independent repository from it (a single initial commit, no shared history) instead of forking or cloning it. See GitHub's docs on [creating a repository from a template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template).

Once you have your new repository, clone it and run `scripts/init.sh` to rename the project (see below).

## Renaming the project

```bash
./scripts/init.sh
```

The script prompts for a project name (e.g. `My Cool Project`), description, author name, and author email (description and author fields default to `""` if left blank), and:

- sets `[project].name` in `pyproject.toml` to the kebab-case distribution name (e.g. `my-cool-project`)
- sets `[project].description` and `[project].authors` in `pyproject.toml`
- renames `src/python_template` to the snake_case package name (e.g. `src/my_cool_project`) and updates `packages = [...]` in `pyproject.toml` to match
- updates `known-first-party` in `ruff.toml`
- rewrites any existing imports referencing the old package name under `src/` and `tests/`

Nothing is applied until you confirm the derived names. Run `uv sync` afterwards to refresh the environment.

## Why this template?

A starting point for future Python projects, focused on being lean, reproducible, and easy to understand.
It provides a minimal set of tools and configuration that give you a solid foundation without a heavy setup or maintenance burden.

### Why should I care even for prototypes?

- prototypes live longer than you thought
- better check errors before than after
- clean code guidelines reduce cognitive load and so clean code is easier to understand for other people and your future self
- consistent between other projects and working in teams

## Decision notes

This template was chosen to be practical and maintainable for Python work without introducing unnecessary complexity.

Key decisions:

- uv instead of Poetry or ad hoc virtualenv/pip setups
- Ruff instead of maintaining multiple formatting and linting tools
- Pyright instead of ty for static type checking
- a simple src-layout project structure
- a dedicated config file for lint and formatting rules

### Why uv?

uv provides a consistent way to manage dependencies, virtual environments, and project metadata.
It helps keep project configuration in one place and makes installation and package management fast and straightforward for both local development and future packaging.

Benefits:

- single tool for dependency management, virtual envs, and Python version installs
- reproducible environment setup via a committed lockfile (`uv.lock`)
- clear project metadata in `pyproject.toml`
- simple package and script management

#### Alternatives

| Criterion | Weight (1-10) | uv | Poetry | pip + venv | conda |
| ----------- | -------------- | ---- | -------- | ------------ | ------- |
| Install/resolve speed | 9 | 10 | 5 | 4 | 3 |
| Lockfile support | 8 | 9 | 8 | 3 (needs pip-tools) | 4 (needs conda-lock) |
| Manages Python versions | 6 | 9 | 2 | 1 | 9 |
| PEP 621 native config | 7 | 10 | 6 (needs `[tool.poetry]`) | 8 | 2 (uses `environment.yml`) |
| Ecosystem maturity | 5 | 6 | 8 | 10 | 9 (strong for native/scientific deps) |
| Single tool for venv + deps + build | 8 | 10 | 8 | 3 | 5 (no PyPI packaging/build support) |
| **Weighted Total** | | **347** | **242** | **170** | **212** |

uv wins on speed and scope (it replaces pip, pip-tools, virtualenv, and pyenv with one tool), while staying compatible with standard `pyproject.toml` metadata instead of requiring a Poetry-specific `[tool.poetry]` table.

See [decision-matrices.md](decision-matrices.md) for how these weights and scores were derived.

### Why Ruff?

Ruff is used for formatting and linting in a fast and lightweight way.
It replaces a larger stack with one tool that is quick to run and easy to configure.

Benefits:

- fast linting and formatting
- consistent code style across contributors
- support for import sorting and quality checks
- configuration kept in a dedicated `ruff.toml` file

#### Alternatives

| Criterion | Weight (1-10) | Ruff | flake8 + isort + black | pylint |
| ----------- | -------------- | ------ | ------------------------- | -------- |
| Speed (lint + format a mid-size codebase) | 9 | 10 | 4 | 2 |
| Single tool for lint + format + import-sort | 8 | 10 | 4 | 3 |
| Rule coverage / plugin breadth | 6 | 8 | 7 | 9 |
| Config simplicity | 7 | 9 | 5 | 4 |
| Ecosystem maturity | 5 | 7 | 9 (blended) | 9 |
| Autofix support | 7 | 9 | 6 | 3 |
| **Weighted Total** | | **375** | **268** | **224** |

Ruff wins primarily on speed and consolidation: one tool and one config file (`ruff.toml`) replace three separately-maintained tools with three separate configs. See [decision-matrices.md](decision-matrices.md) for how these weights and scores were derived.

### Why Pyright?

Pyright is used for static type checking, catching type errors before code ever runs.

Benefits:

- fast, incremental type checking (implemented as a language server, so it also powers VS Code's Pylance)
- no separate stub-cache setup — resolves types from installed packages directly
- widely used, mature, actively maintained by Microsoft

#### Why Pyright over `ty`?

`ty` (Astral's type checker) would fit this template's pattern of favoring Astral tooling (uv, Ruff), but as of writing it is **still in beta** — Astral itself does not yet recommend it for projects that depend on a stable, predictable type checker. Pyright, by contrast, is a battle-tested tool used across a huge share of the Python ecosystem (it's the engine behind VS Code's Pylance), with years of edge cases already ironed out.

| Criterion | Weight (1-10) | Pyright | ty | mypy |
| ----------- | -------------- | ------- | ---- | ------ |
| Stability / production-readiness | 10 | 9 | 3 (beta, breaking changes still expected) | 8 |
| Speed | 7 | 8 | 9 (Rust-based, but unproven at scale) | 4 |
| Ecosystem maturity / community adoption | 7 | 9 | 2 (very new) | 9 |
| Editor integration (VS Code) | 6 | 10 (Pylance is built on Pyright) | 5 | 6 |
| **Weighted Total** | | **326** | **154** | **255** |

Pyright wins mainly on being a known, stable quantity today. Once `ty` graduates out of beta, this decision is worth revisiting — see [decision-matrices.md](decision-matrices.md) for how these weights and scores were derived.

### Why this structure?

The project follows a simple layout that scales reasonably well for small to medium Python projects:

```text
.
├── pyproject.toml
├── uv.lock
├── ruff.toml
├── README.md
├── src/
│   └── python_template/
│       └── __init__.py
└── tests/
    └── __init__.py
```

This keeps source code separated from project configuration and makes it easier to expand later.

## Contributing

Use the project as a starting point and keep the setup simple.
When adding new dependencies, prefer:

```bash
uv add <package>
```

For development-only tools:

```bash
uv add --dev <package>
```

## Getting started

### Prerequisites

- Python 3.12 or newer
- uv

### Install uv

If uv is not installed yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install the project

From the repository root:

```bash
uv sync
```

This creates a virtual environment and installs the project dependencies defined in `pyproject.toml`, using `uv.lock` for reproducible versions.

### Activate the environment

```bash
source .venv/bin/activate
```

Or run commands without activating the shell:

```bash
uv run <command>
```

## Running the application

The template ships with a small CLI in [main.py](../main.py) that greets someone by name.

```bash
uv run main.py
# Hello, World!

uv run main.py Ada
# Hello, Ada!
```

Run it without `uv run` if you've activated the virtual environment (`source .venv/bin/activate`):

```bash
python main.py Ada
```

## Using the src package as a module

Application code lives under [src/python_template/](../src/python_template/) and is installed as a regular Python package (see `packages = ["src/python_template"]` in `pyproject.toml`). After `uv sync`, import it like any other package instead of duplicating logic elsewhere:

```python
from python_template import greet

print(greet("World"))
# Hello, World!
```

This works from scripts, tests, and notebooks alike, since `uv sync` installs the package into the project's virtual environment. To add more functionality, create additional modules under `src/python_template/` and export what should be public from [`__init__.py`](../src/python_template/__init__.py).

## Linting and formatting

This template uses Ruff for both code formatting and linting.

### Run the linter

```bash
uv run ruff check .
```

### Run the formatter

```bash
uv run ruff format .
```

### Check formatting without applying changes

```bash
uv run ruff format --check .
```

### Fix simple lint issues automatically

```bash
uv run ruff check --fix .
```

## Type checking

This template uses [Pyright](https://microsoft.github.io/pyright/) for static type checking, configured via `[tool.pyright]` in `pyproject.toml`.

### Run the type checker

```bash
uv run pyright
```

## Git hooks

A `pre-push` hook in `.githooks/` runs formatting, linting, type checking, and the test suite before a push is allowed to proceed:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

Git hooks live outside version control by default, so this repo's hooks are tracked under `.githooks/` instead of `.git/hooks/`. Point Git at that directory once per clone:

```bash
git config core.hooksPath .githooks
```

If any check fails, the push is aborted. Fix the issue (or run `uv run ruff format .` / `uv run ruff check --fix .`) and push again.

## VS Code setup

The `.vscode/settings.json` file points VS Code at the project's `.venv` interpreter, configures Ruff as the formatter with format-on-save and auto-fix/import-sort on save, and enables the Testing panel to discover tests with pytest. Install the recommended extensions from `.vscode/extensions.json` (Ruff and Python) to get this working.

`.vscode/launch.json` provides two run/debug configurations:

- **Python: Run Current File** — runs the file open in the active editor.
- **Python: Debug Tests** — runs the test suite under `tests/` with pytest.

Tests use [pytest](https://docs.pytest.org/), added as a dev dependency (`uv add --dev pytest`).
