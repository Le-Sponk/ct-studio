# Phase 1 review brief — skeleton and quality gates
**Reviewer:** verify independently; this is orientation, not evidence. Repository `C:\dev\ct-studio`.

## Goal and scope
A minimal launchable Qt desktop shell on Windows/Linux, with a locked Python environment,
architecture boundaries, typed errors/logging, filesystem/platform utilities, a local gate,
CI, and contributor basics. Exit: `scripts/check.py` green locally and in GitHub Actions
on ubuntu-latest/windows-latest. All P1-T01…P1-T08 tasks are ticked in the phase file.

`git diff --stat phase-00-done..HEAD`: 82 files, +6157/-305 (includes P0 follow-ups after
the tag, not all of these lines are new Phase 1 code). Source modules added:
`src/ctstudio/__main__.py`, `core/{errors,logging,platform,fsutil}.py`,
`gui/{app,main_window}.py`, plus empty package markers. Gate/CI:
`scripts/{check,ci_network}.py`, `.importlinter`, `.github/workflows/{ci,integration}.yml`.
New unit/GUI tests for each, benchmark for 200 MiB hash, README/CONTRIBUTING/LICENSE/notices.
Planning architecture: `docs/ARCHITECTURE.md`; rules: `AGENTS.md` and review checklist.

## Checks to reproduce
On this Windows git-bash host, first `export PATH="$LOCALAPPDATA/Microsoft/WinGet/Links:$PATH"`.
- `uv run python scripts/check.py --all`
- `uv run pytest -p no:cacheprovider -m 'integration and not network' tests/integration -q -rs`
- `uv run pytest -p no:cacheprovider -m 'not network' tests -q -rs`
- Check image pixels in `tests/artifacts/screens/p1-t06-*.png` if vision is available.
- Inspect three negative/mutation tests in isolated *scratch copies*, never edit live checkout.

Local pre-review: check.py --all green (125 passed/1 optional skip); integration
71 passed/6 skips/14 deselected; broad non-network 198 passed/19 optional skips/
1 deselected. Main GitHub CI on last P1-T08 closeout passed on both OSes:
https://github.com/Le-Sponk/ct-studio/actions/runs/36343346249

## Known limits to challenge, not silently call passes
- Real editor/GL tests auto-skip without optional Wine/Xvfb/moderngl/Dolphin; no
  Nintendo data in CI. Verify the skip reasons, not "all integrations covered".
- Linux font-family and screenshot creation passed in CI; pixels were not visually
  inspected on Mint. User explicitly deferred the optional spot-check.
- Scheduled network job intentionally non-green when Wine is missing; its reason was
  verified on both OSes in run 36341608296, not a completed nightly cron run.
- `LICENSE` is canonical verbatim GPLv3 (674 legal-text lines); code-size budget
  cannot shorten legal terms. See ADR-009 and docs tests for checksum.
- No HC at Phase 1 exit. HC1 is at the end of Phase 5.
