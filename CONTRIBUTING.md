# Contributing to CT Studio

CT Studio is pre-alpha. Read [AGENTS.md](AGENTS.md) for the engineering rules and
[STATUS.md](STATUS.md) for the current task and blockers before changing code. Work on one
[phase task](docs/phases/PHASE_01_skeleton_and_quality.md) at a time and ship tests with changes.

## Set up and check

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git. From the repo root
on Windows or Linux:

```sh
git submodule update --init
uv sync --locked
uv run ctstudio --version
uv run python scripts/check.py
uv run pytest -m "not network" tests
```

The gate checks formatting, lint, types, import boundaries, unit/GUI tests, complexity and dead
code. GitHub Actions runs it on Ubuntu and Windows. GUI widget tests use Qt offscreen; GL preview
tests require an X server instead. Real-tool integration tests need the optional executables under
`.tools/` and may skip when those tools are absent. See the [testing strategy](docs/process/TESTING_STRATEGY.md)
and [environment notes](docs/dev/ENVIRONMENT.md) for details.

## Boundaries

Keep `core` independent of Qt; launch external programs through the core tool adapters rather
than importing or spawning them elsewhere in application code. Verify tool flags against real
help/output and record the version in [TOOLS.md](docs/reference/TOOLS.md). Follow the file and
complexity budgets in AGENTS.md, and do not overwrite user-editable files without a backup.
Do not commit Nintendo game files, generated output, credentials, or local tools. Put any
personal game-derived test files in the gitignored `local_fixtures/` directory.

The app is [GPL-3.0-or-later](LICENSE). Keep [third-party notices](THIRD_PARTY_NOTICES.md)
accurate when dependencies or the pinned Blender add-on change.
