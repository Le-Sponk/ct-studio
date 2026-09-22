# Phase 1 — Skeleton & quality gates

**Goal:** a tiny app that launches, with every quality gate in place *before* real code exists.
**Exit:** `scripts/check.py` green locally and in CI on ubuntu-latest + windows-latest.

### [ ] P1-T01 — Project metadata & environment
`pyproject.toml` (src layout, package `ctstudio`, Python `>=3.12,<3.14`, entry point
`ctstudio = "ctstudio.__main__:main"`). Runtime deps now: `PySide6`, `numpy`, `Pillow`,
`tomli-w`, `platformdirs`, `watchfiles`. Dev group: ruff, pyright, pytest, pytest-qt,
pytest-timeout, pytest-cov, pytest-benchmark, import-linter, vulture, radon, xenon, pylint.
Commit `uv.lock`. `.gitignore`: `.tools/`, `.ctstudio/`, `build/`, `dist/`, `local_fixtures/`,
`tests/fixtures/generated/`, `tests/artifacts/`, `spikes/out/`.
**Acceptance:** `uv sync` then `uv run ctstudio --version` works on Linux and in Windows CI.

### [ ] P1-T02 — `scripts/check.py`
Runs in order, fails fast unless `--all`: `ruff format --check`, `ruff check`, `pyright`,
`lint-imports`, `pytest -m "not integration and not slow and not realdata and not network"` with
coverage, `xenon --max-absolute B --max-modules A --max-average A src/ctstudio/core`
(tune once, document), `vulture src/ vulture_whitelist.py --min-confidence 80`.
`--fast` skips pyright + coverage.
`network` is excluded because a test with an external precondition cannot be a local gate — it must
skip loudly with a reason rather than fail on an offline machine (see TD-001, and the `network`
marker in `pytest.ini`). Nightly integration runs it (P1-T07).
Prints a one-line summary per step with duration.
**Acceptance:** passes on the skeleton; deliberately broken sample (in a test) makes it fail; a
`network`-marked test is not collected by the default run.

### [ ] P1-T03 — Architecture contracts
`.importlinter` contracts: core ↛ gui/cli/PySide6; cli ↛ gui; nothing ↛ spikes. A unit test asserts
`blender_bridge` files import only stdlib + `bpy` (AST scan).
**Acceptance:** adding `import PySide6` in core makes `check.py` fail (verified by a test fixture copy).

### [ ] P1-T04 — Errors & logging foundation
`core/errors.py`: `CTStudioError(user_message, hint=None, details=None)` → `ToolNotFound`,
`ToolFailed(cmd, exit_code, stderr_tail, log_path)`, `ProjectError`, `ManifestError(key_path)`,
`BuildError(node_id)`, `Cancelled`, `ParseError`. `core/logging.py`: stdlib logging, JSON-lines
rotating file handler in `platformdirs.user_log_dir`, console handler for CLI, `get_logger(__name__)`.
**Acceptance:** unit tests for message/hint formatting and log file creation in a temp dir.

### [ ] P1-T05 — Platform & filesystem utilities
`core/platform.py`: OS detection, user dirs, Flatpak/Snap detection (port ideas from the add-on's
`diagnose.py`/tool discovery). `core/fsutil.py`: `atomic_write_bytes/text`, `replace_with_backup`,
`ensure_inside(root, path)`, `Fingerprint(size, mtime_ns, blake2b?)` with lazy hashing and an
in-memory LRU keyed by `(path, size, mtime_ns)`; `hash_file` streaming in 1 MiB chunks.
**Acceptance:** tests incl. paths with spaces/unicode, concurrent replace, backup naming; a benchmark
hashing a 200 MB temp file (recorded, not asserted yet).

### [ ] P1-T06 — Minimal GUI shell
`gui/app.py` + `main_window.py`: window with placeholder dashboard, About dialog (version, licence,
third-party list placeholder), follows system light/dark. `ctstudio --offscreen-smoke <png>`
starts, renders, saves a screenshot, exits 0. Lazy-import PySide6 only on GUI paths.
**Acceptance:** pytest-qt test passes headless; `python -X importtime -m ctstudio --version` shows
no Qt import.

### [ ] P1-T07 — CI
`.github/workflows/ci.yml`: matrix ubuntu-latest/windows-latest, uv cache, `uv sync`,
`python scripts/check.py`; Linux installs Qt runtime libs; uploads coverage + GUI screenshots as
artifacts. `integration.yml` placeholder (manual dispatch) filled in P2-T08.
`integration.yml` also runs **nightly on a schedule** and is the only place `network`-marked tests
run: `pytest -m network` after the integration selection. A skip there is a signal (the external
precondition moved), so the job must surface skip reasons in its summary rather than report green.
**Acceptance:** green run on both OSes (if the repo isn't on GitHub yet, add a "Needs human" item and
continue; verify later); the nightly job's log shows either the `network` tests running or the exact
skip reason.

### [ ] P1-T08 — Contributor basics
`CONTRIBUTING.md` (short: commands, rules pointer to AGENTS.md), `LICENSE` (GPL-3.0-or-later pending
HC0), `THIRD_PARTY_NOTICES.md` skeleton, `docs/dev/BENCHMARKS.md` skeleton, `vulture_whitelist.py`.
**Acceptance:** files exist; README.md has a 10-line project description and dev quick start.

### [ ] P1-GATE — Phase review (skill `mkw-phase-review`)
