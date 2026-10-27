# Testing strategy

Goal: the agent, not the human, finds almost all bugs. The human's time is reserved for things only
a human with the real game and real habits can judge (see HUMAN_CHECKPOINTS.md).

## Local gate (P1-T02)
`uv run python scripts/check.py` runs ruff format/check, pyright (`src/` and the gate;
strict on `src/ctstudio/core`), import-linter, pytest with coverage, xenon (core), then
vulture. It stops at the first failure unless `--all`; `--fast` skips pyright and
coverage only. The normal gate reads pytest-cov's JSON report from a temporary directory
and fails unless core statement coverage is ≥ 85% and GUI ≥ 60% (REVIEW_CHECKLIST §6);
`--fast` does not enforce coverage. Each step prints status and duration; failed steps
also print captured output and exit status. In GitHub Actions, failed pytest cases also emit
annotations with only the test file and function name (never parametrized values), so a failed
public check identifies the case without requiring access to restricted job logs.
`xenon (core)` is active from P1-T04, when
arrive. Before that it explicitly skipped: xenon itself returned 0 on an absent or empty
package. P1-T03 added empty `core`, `cli` and `gui` package markers for import-linter.
Import-linter's three contracts protect core↛GUI/CLI/PySide6, CLI↛GUI, and application↛`spikes`,
including external packages via `include_external_packages = True`.
The unit test AST-scans `blender_bridge` for imports outside stdlib/`bpy` and project code
(`src`, `scripts`, `tests`) for imports of throwaway `spikes`. Tests copy the skeleton and
insert forbidden imports, so "kept" is not vacuous.
The gate prepends its active venv to child PATH: pyright probes `python` for installed
packages, and otherwise misdiagnoses PySide6 as missing in a copied tree.
The dev dependency `pyright[nodejs]` includes Node as a wheel, avoiding a network
bootstrap on a clean CI machine. Tool configuration is in
`pyproject.toml`, with the import-linter root in `.importlinter`.

## 1. Layers and markers
| Layer | Location | Marker | Runs | Speed target |
|---|---|---|---|---|
| Unit (pure core logic) | `tests/unit/` | — | every `check.py` | whole suite < 20 s |
| Contract (fakes ↔ recorded real tool help/outputs) | `tests/contract/` | — | every `check.py` | < 5 s |
| GUI (pytest-qt, offscreen) | `tests/gui/` | `gui` | every `check.py` (CI both OS) | < 60 s |
| Integration (real tools from `.tools/`) | `tests/integration/` | `integration` | before commit when touching tools/pipelines; nightly CI | minutes |
| End-to-end (fixture `.blend` → SZS) | `tests/e2e/` | `slow`, `integration` | before phase gates; nightly CI | minutes |
| Real data (user's own tracks) | `tests/realdata/` | `realdata` | only when `local_fixtures/` exists | varies |
| Benchmarks | `tests/benchmarks/` | `benchmark` | phase gates, deep cleans | — |
| External-endpoint dependent | anywhere | `network` | nightly CI only, never `check.py` | varies |

A `network` test depends on something outside the repo being reachable. It must **skip with a
precise reason** naming the endpoint when that precondition fails, never fail and never pass
vacuously — an offline machine is not a broken build. `check.py` excludes the marker (P1-T02);
the nightly integration workflow is the only place it runs and must surface skip reasons rather
than report green (P1-T07). First instance: TD-001, RiiStudio's update check.

Every test file sets a timeout (`pytest-timeout`, default 30 s unit, 600 s integration; 900 s for
the Wine/emulator suites that drive GUIs). **`pytest-timeout` must be installed for those marks to
do anything** — without the plugin pytest reports `PytestUnknownMarkWarning` and the marks are
silently inert, which is how they shipped through P0 (found at the P0 gate). It is in P1-T01's dev
group and every documented run command; if a run warns about an unknown `timeout` mark, the plugin
is missing and nothing is protected.

## 2. Fake tools and recordings
- Fakes implement only the CLI surface we use and never guess: anything their recordings do
  not pin down exits **121** ("not modelled", a code no real tool here uses) before any output
  or write. They are launched through the *real* process runner, so the runner is exercised too.
  P2-T04b: `tests/fakes/fake_wiimm.py` (wszst create/list/check/minimap --auto, wkclt decode,
  wkmpt decode/encode, wimgt encode, plus `version`/`help`), `wiimm_cli.py` (getopt as the
  real tools parse it, from their recorded `--xhelp`: unknown option → exit 110, an option
  another command owns → exit 108), `fake_runtime.py` (call log, outcomes, LF output) and
  `install.py`. rszst/ABMatt/Blender fakes follow in P2-T04c.
- **`fake_tools_path`** (`tests/conftest.py`) installs real executables for the fakes once per
  session into a folder with a space and `é`, puts it first on PATH, and gives each test its
  own call log (`fake_tools_path.calls()` → tool, argv, cwd, in call order). One file per
  call: a shared append-only file lost lines when probes ran in parallel on Windows (the C
  runtime's `O_APPEND` is a seek then a write). Windows: pip's console
  launcher (distlib `t64.exe`, from the pip wheel bundled with CPython) + a zip, so they are real
  `.exe` files; Linux: an executable sh/Python polyglot (a `#!` line cannot hold a path with
  spaces).
- Archives a fake writes carry a marker and list the source files' sizes and magic; a fake
  refuses (121) to read a real SZS/KMP/TEX0, so fake and real outputs never mix.
- `tests/fakes/recordings/<tool>/<version>/` store captured real outputs (`--help`, `version`,
  `check` on good/bad inputs). Parsers are unit-tested against recordings.
- `scripts/record_tool_outputs.py` (P2-T04b) runs a case table of real Wiimm operations on
  the generated fixtures (`<os>-ops.json`: output, exit code, files created/changed with their
  first bytes, and the size + first 32 bytes of each fixture used). `test_fake_wiimm.py`
  replays every case against the fakes with stand-in inputs of the same size and leading
  bytes; stdout must match exactly, or as a prefix where the real tool goes on to print
  KMP/KCL findings a fake cannot compute (`wszst check` then exits 0 instead of 2).
- `scripts/record_tool_help.py` (P2-T04a) re-records `<os>-help.json` for every pinned CLI
  through the app's process runner, with LF newlines and the install folder replaced by
  `<tool-dir>`. It refuses a tool whose installed version differs from the catalogue pin.
  `tests/fakes/help_contract.py` reads those recordings (Wiimm option tables, clap, ABMatt's
  pipe table, Blender) into the flags each subcommand accepts. `test_help_contract.py` checks
  every argv template in TOOLS.md against them, so a misspelt flag, a flag borrowed from
  another subcommand, or an unrecorded subcommand fails. After a version bump: bootstrap,
  re-run the recorder, delete the old version folder. For Wiimm it also writes
  `<os>-options.json` (every command, alias and option with its argument kind, from `--xhelp`)
  for the fakes' option parser.
- Contract tests fail if an adapter emits a flag absent from the recorded help of the pinned version,
  or if a parser can't handle a recording. Upgrading a tool = add a new recording folder, re-run.

## 3. Fixtures
- **Synthetic, generated, deterministic** (`scripts/fixtures/`): fixture `.blend` (course, KCL,
  skybox collections; opaque/cutout/translucent/grayscale textures), fixture KMP (via `wkmpt`),
  crafted bad variants (non-POT textures, unflagged KCL objects, out-of-range coordinates, missing
  materials, corrupt KCL/KMP bytes).
- **No golden binaries of tool outputs** (they change with tool versions). Assert structure instead:
  `wszst list` contents, parsed `check` issues, `inspect` results (formats, material settings),
  KCL/KMP reader stats.
- Generated fixtures are cached under `tests/fixtures/generated/` keyed by generator hash.

## 4. Real data (optional, local only)
The human may place their own track projects/SZS files in `local_fixtures/` (gitignored) with a
`local_fixtures/README.md` describing each. Tests marked `realdata` auto-skip when absent. The real
Wiimms auto-add build/use test also carries this marker and runs at HC1; synthetic fixture builds
must not require an auto-add library. Never upload game-derived inputs or auto-add contents to CI
or commit them.

## 5. GUI testing
- `QT_QPA_PLATFORM=offscreen`, pytest-qt `qtbot`, wait on signals (`qtbot.waitSignal`) — never sleep.
- Every GUI test that shows a new screen state saves a screenshot to `tests/artifacts/screens/`
  (`widget.grab().save(...)`), uploaded as a CI artefact. Screens are reviewed at gates (§5 of
  REVIEW_CHECKLIST) by the agent if it can view images, otherwise listed for the human at HCs.
  P1-T06 saves the dashboard (light, dark and 150% scale) and About (light/dark), reviewed locally.
  Windows Qt offscreen can report zero system fonts; `MainWindow` loads the installed Segoe UI
  only in that case, with a Linux DejaVu fallback, so test PNGs contain glyphs rather than boxes.
- The dev watchdog is enabled in GUI tests; any UI stall > 100 ms fails the test (allowlist startup).
- GL/preview tests **cannot use `QT_QPA_PLATFORM=offscreen`** — it cannot create a GL context at all
  (`QOpenGLWidget is not supported on this platform`, verified in S6/P0-T09). Run them under
  `xvfb-run` with `QT_QPA_PLATFORM=xcb`, which gives GL 4.5 core on llvmpipe. Non-GL widget tests keep
  using offscreen. A standalone `moderngl.create_context(standalone=True, backend="egl")` also works
  and needs no X server, so use it for pure-render checks with no Qt widget involved. Linux runners
  need `libgl-dev` (the unversioned `libGL.so`) as well as the runtime library. Skip with a clear
  reason if GL is unavailable on a runner, but never on the Linux integration job.

## 6. CI matrix
- `ci.yml` (every push/PR): ubuntu-latest + windows-latest · locked `uv sync`,
  `check.py` (unit, contract, gui) and an uploaded per-OS artifact containing coverage XML
  and GUI screenshots. Linux installs Qt runtime libraries plus DejaVu fonts.
- `integration.yml` (nightly UTC + manual): both OSes currently run only `pytest -m network`
  (P1-T07 scaffold). `scripts/ci_network.py` parses pytest's JUnit XML and writes exact
  selected-test skip reasons to the log, GitHub job summary and public job annotations; no selected
  tests or any selected skip fails the job rather than producing a false green. Unrelated collection
  skips are displayed separately. Both workflows provision Linux Qt libraries/fonts and set
  `QT_QPA_PLATFORM=offscreen` before test collection. P2-T08 adds bootstrap tools and the full
  integration/e2e suites; until the RiiStudio/Wine prerequisites are present nightly is expected
  to fail visibly with the missing precondition. It uploads JUnit XML.
- `compat.yml` (weekly): Blender 4.5 LTS compatibility run of bridge tests.
- `release.yml` (tags): packaging + packaged smoke tests (P12).
Windows CI is how Windows is validated continuously — the human only does Windows spot checks at HC2
and HC4.

## 7. What each phase must add
- New adapter operation → recording + parser unit test + integration test.
- New node → unit test with fakes (params → args, caching behaviour) + integration test.
- New GUI page → pytest-qt flow + screenshots (light/dark).
- New parser → corrupt-input tests (P13 adds hypothesis fuzzing).
- New heavy operation → benchmark.

## 8. Flaky tests policy
A flaky test is a bug. Quarantine only with a task ID and a date; fix within the phase.
