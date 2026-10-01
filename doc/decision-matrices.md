# Decision matrix methodology

This document explains how the scores and weights in [template.md](template.md)'s
decision matrices (`uv` vs. alternatives, `Ruff` vs. alternatives, `Pyright` vs.
alternatives) were derived, so the numbers can be revisited or challenged
rather than taken on faith.

## How to read the tables

Each table follows the same method:

1. **Criterion** — a property that matters for this template's goals (fast
   local dev loop, low config overhead, reproducibility).
2. **Weight (1-10)** — how much that criterion matters for *this template's*
   use case (small-to-medium Python projects, solo or small-team dev). Weights
   are subjective judgment calls, not benchmarked — they reflect priorities
   for this template, not a universal ranking of what matters in tooling.
3. **Score (1-10) per tool** — how well that tool satisfies the criterion,
   scored relative to the other tools in the same row, not against an
   absolute standard.
4. **Weighted Total** — `sum(weight * score)` per tool, used only to rank
   tools against each other within one table. The absolute number has no
   meaning outside that comparison.

Scores are informed estimates based on public documentation, changelogs, and
general community consensus (e.g. GitHub star history, PyPI download trends,
official docs) as of when the table was written — not a formal benchmark
suite. Treat them as a structured opinion, not measured data.

## uv vs. Poetry vs. pip+venv vs. conda

| Criterion | Why this weight | Why each score |
|---|---|---|
| Install/resolve speed | 9 — this is uv's headline feature and directly affects daily dev loop time | uv (10): resolver written in Rust, benchmarks show 10-100x over pip. Poetry (5): usable but resolver has historically been slow on large dependency trees. pip+venv (4): pip's resolver is correct but slow, no parallel downloads by default. conda (3): package + environment resolution (SAT solver) is the slowest of the group, especially on first solve. |
| Lockfile support | 8 — reproducibility across machines/CI is a core template goal | uv (9): built-in `uv.lock`, generated automatically, cross-platform. Poetry (8): mature `poetry.lock`, been the standard for years. pip+venv (3): no native lockfile; needs `pip-tools`/`pip freeze` workarounds that don't lock transitive deps as robustly. conda (4): needs the third-party `conda-lock` tool, not built in. |
| Manages Python versions | 6 — convenient, but a project can work without it (e.g. via pyenv) | uv (9): `uv python install`/`uv python pin` built in. Poetry (2): delegates entirely to whatever Python is on `PATH`, no version management. pip+venv (1): no version management at all, needs pyenv or system Python. conda (9): long-standing strength, installs any Python version into an env. |
| PEP 621 native config | 7 — sticking to the standard `pyproject.toml` format avoids tool lock-in | uv (10): reads/writes standard `[project]` table directly, no extra section needed. Poetry (6): still requires its own `[tool.poetry]` table for most metadata even though it also supports parts of PEP 621. pip+venv (8): pip itself just installs; PEP 621 metadata is standard and pip respects it, but pip provides none of the tooling around it. conda (2): primarily driven by `environment.yml`, which predates and ignores PEP 621. |
| Ecosystem maturity | 5 — matters, but is expected to close over time as uv adoption grows | uv (6): public since 2024 (Astral); smaller base of blog posts/Stack Overflow answers/CI templates/IDE integrations than the alternatives. Poetry (8): mainstream since ~2018, wide plugin ecosystem, well understood by most Python devs. pip+venv (10): part of the language/stdlib toolchain since the 2000s/3.3, universal support everywhere. conda (9): over a decade of use in the scientific/data community, mature channel ecosystem (conda-forge). |
| Single tool for venv + deps + build | 8 — reducing the number of tools to install/learn is a stated template goal | uv (10): replaces pip, pip-tools, virtualenv, and pyenv in one binary. Poetry (8): also covers venv+deps+build, but not Python-version installs. pip+venv (3): pip only installs packages; venv only creates environments; neither builds/publishes without extra tools (`build`, `twine`). conda (5): manages envs and non-Python deps well, but has no PyPI-style build/publish workflow. |

**Weighted total** = sum of `weight * score` per column, e.g. uv: `9*10 + 8*9 + 6*9 + 7*10 + 5*6 + 8*10 = 347`. It only says "uv ranks highest given these weights," not "uv is 347% better."

## Ruff vs. flake8+isort+black vs. pylint

Added for the "Why Ruff?" section, same method as above. The baseline
alternative bundles the tools Ruff is meant to replace, since no one of them
alone covers formatting, import sorting, and linting.

| Criterion | Why this weight | Why each score |
|---|---|---|
| Speed (lint + format a mid-size codebase) | 9 — Ruff's core selling point, and it shapes whether checks run on every save/commit or only in CI | Ruff (10): implemented in Rust, published benchmarks show order-of-magnitude speedups over the Python-based tools it replaces. flake8+isort+black (4): each tool re-parses the codebase separately; workable but noticeably slower, especially with plugins. pylint (2): does much deeper (type/semantic) analysis, which is why it's markedly slower on the same codebase. |
| Single tool for lint + format + import-sort | 8 — fewer configs and fewer moving parts is a stated template goal | Ruff (10): one binary and one config file (`ruff.toml`) covers linting, formatting, and import sorting. flake8+isort+black (4): three separate tools, three configs, and the risk of them disagreeing (e.g. line-length mismatches). pylint (3): lints only; still needs a separate formatter and import sorter. |
| Rule coverage / plugin breadth | 6 — matters, but a smaller, curated rule set is arguably a feature for a template meant to stay simple | Ruff (8): reimplements the rule sets of flake8, pyupgrade, bugbear, and many popular plugins natively. flake8+isort+black (7): decades of plugins exist, so coverage is broad but scattered across separately-maintained packages. pylint (9): does the deepest static analysis (some type-inference-like checks) of the group, at the cost of speed and more false positives. |
| Config simplicity | 7 — a template should be easy to understand and adapt without deep tool-specific knowledge | Ruff (9): one TOML file, unified option names. flake8+isort+black (5): three separate config sections/files that must be kept consistent by hand. pylint (4): large default rule set with a big, dense config surface; commonly needs per-project tuning to be usable. |
| Ecosystem maturity | 5 — same reasoning as uv's row: real, but expected to keep narrowing | Ruff (7): public since 2022, has already become a de facto standard in many modern Python projects, faster adoption curve than uv's. flake8 (10)/black (9)/isort (9) blended: each individually has 10+ years of use, wide IDE/CI support, huge base of existing answers and integrations. pylint (9): also long-standing (since ~2003), deeply embedded in many enterprise/legacy pipelines. |
| Autofix support | 7 — auto-fixing lint issues (not just formatting) reduces manual cleanup work | Ruff (9): many lint rules are auto-fixable via `ruff check --fix`, in addition to full formatting. flake8+isort+black (6): black and isort auto-fix formatting/import order, but flake8 itself only reports, it does not fix lint issues. pylint (3): reporting-only, no autofix. |
| **Weighted Total** | | Ruff: `9*10+8*10+6*8+7*9+5*7+7*9 = 375`. flake8+isort+black: `9*4+8*4+6*7+7*5+5*9+7*6 = 268`. pylint: `9*2+8*3+6*9+7*4+5*9+7*3 = 224`. |

Ruff wins primarily on speed and consolidation, the same axes uv wins on in
the table above — both tools trade a shorter ecosystem track record for
replacing several older, slower, single-purpose tools with one fast one.

## Pyright vs. ty vs. mypy

Added for the "Why Pyright?" section. `ty` is Astral's type checker — the
same team behind `uv` and `Ruff` — so it's the natural alternative to
consider first, given this template otherwise favors Astral tooling. `mypy`
is included as the long-standing incumbent for comparison.

| Criterion | Why this weight | Why each score |
|---|---|---|
| Stability / production-readiness | 10 — a type checker that changes behavior or breaks between releases actively erodes trust in its output, which defeats the point of using one | Pyright (9): stable for years, backs VS Code's Pylance in production for millions of users. ty (3): explicitly labeled beta by Astral at time of writing, with breaking changes still expected as it matures. mypy (8): the original mature type checker, very stable, occasional edge-case regressions between releases. |
| Speed | 7 — matters for a fast local dev loop, but less than for Ruff since type checking runs less frequently (on save/push, not on every keystroke the way formatting does) | Pyright (8): implemented in TypeScript, well-optimized incremental checking. ty (9): Rust-based like Ruff/uv, benchmarks suggest it will be faster once mature, but this is unproven at scale given its beta status. mypy (4): Python-based, historically the slowest of the group on large codebases. |
| Ecosystem maturity / community adoption | 7 — determines how easily questions get answered, how well third-party stubs are supported, and how likely edge cases have already been found by someone else | Pyright (9): extremely wide adoption via Pylance, huge base of existing configs/answers. ty (2): very new, minimal community track record yet. mypy (9): the de facto standard for over a decade, deepest stub/plugin ecosystem (e.g. django-stubs). |
| Editor integration (VS Code) | 6 — this template's `.vscode/` setup targets VS Code specifically | Pyright (10): Pylance (VS Code's default Python language server) is built directly on Pyright, so integration is first-class with zero extra config. ty (5): has editor support but not the default/bundled experience in VS Code yet. mypy (6): supported via extensions, but not as tightly integrated as Pylance. |
| **Weighted Total** | | Pyright: `10*9 + 7*8 + 7*9 + 6*10 = 326`. ty: `10*3 + 7*9 + 7*2 + 6*5 = 154`. mypy: `10*8 + 7*4 + 7*9 + 6*6 = 255`. |

Pyright wins mainly on stability and editor integration today. This is the
one table in this document explicitly expected to become outdated soon: once
`ty` exits beta, its stability score (and likely its speed score, once
proven at scale) should be revisited — at that point it may overtake Pyright
given the same Rust-based-tooling rationale that won uv and Ruff their
places in this template.

## Revisiting these numbers

These weights and scores reflect this template's priorities (fast local
loop, low config overhead, standard-compliant metadata) as of the time this
document was written. If a future project has different priorities (e.g.
heavy native/scientific dependencies, where conda's ecosystem maturity would
matter far more), the weights — not just the scores — should be revisited.
