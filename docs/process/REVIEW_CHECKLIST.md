# Review checklists

Two kinds of review:
- **Phase review** — at every phase gate. Run by a *fresh-context* reviewer via `delegate_task`.
- **Deep Clean** — after P5, P8 and P13. Metrics-driven simplification + performance comparison.

Reviews write `docs/reviews/PHASE_XX_REVIEW.md` or `docs/reviews/DEEP_CLEAN_N.md` with findings in
three buckets: **Must fix** (blocks the gate) · **Should fix** (fix now unless costly; else task ID)
· **Consider** (logged as tech debt or dropped with a reason). The implementer fixes Must + Should,
re-runs checks, records the gate in STATUS.md and tags the commit.

---

## 1. Phase review procedure
1. Implementer prepares a brief: phase file path, `git diff --stat phase-(N-1)-done..HEAD`, list of
   new modules, commands to run, known limitations.
2. Delegate to a reviewer subagent with: that brief, ARCHITECTURE.md, this checklist, AGENTS.md rules.
   Instruct it to **run** the checks and tests itself, read the code, and report findings with file:line.
3. Implementer triages and fixes; reviewer (new delegate) verifies Must-fix items if any were found.
4. Update DECISIONS.md/ARCHITECTURE.md if reality diverged. Gate recorded.

## 2. Phase review checklist
**Acceptance**
- [ ] Every task's acceptance criteria verified by running the tests/commands, not by reading claims.
- [ ] Phase exit criteria met; STATUS.md accurate.

**Architecture**
- [ ] Import contracts pass; no subprocess outside `core/tools/process.py`; no Qt in core.
- [ ] New code sits in the module the ARCHITECTURE tree says it should (or the doc was updated).
- [ ] Adapters own all tool flags; flags recorded in TOOLS.md with versions.
- [ ] No new dependency without an ADR.

**Correctness & robustness**
- [ ] Errors are typed, carry user message + hint; nothing swallowed; cancellation handled.
- [ ] File writes atomic; backups before overwriting possibly user-edited files.
- [ ] Paths: pathlib, spaces/unicode tested, no hard-coded separators or drive letters.
- [ ] Windows-specific process behaviour considered (no console flash, tree kill).

**Tests**
- [ ] Tests assert behaviour/outputs, not merely that mocks were called.
- [ ] Mutation spot-check: reviewer breaks 3 lines of new logic; at least one test fails each time.
- [ ] Integration tests exist for every adapter operation used; fakes match recordings.
- [ ] No sleeps for synchronisation in tests (use signals/events/wait conditions).

**Performance**
- [ ] No blocking work on the UI thread (watchdog log clean during GUI tests).
- [ ] Benchmarks for anything heavy; no regression > 10 % vs BENCHMARKS.md without justification.

**UX (phases with GUI work)** — see §5.

**Docs**
- [ ] ARCHITECTURE/DECISIONS/TOOLS/user docs match the code.

## 3. AI-generated code smells (hunt for these every review)
- Speculative abstraction: base classes/interfaces/factories with one implementation and no ADR.
- Duplicate helpers with different names doing the same thing (grep for similar function bodies;
  run `pylint --disable=all --enable=duplicate-code`).
- "Defensive" code that hides bugs: broad `except Exception`, returning `None`/`{}` on failure,
  `getattr(x, "y", None)` chains on objects we own.
- Parameters, flags and config options nothing uses; dead branches for "future" features.
- Re-reading files, re-hashing, or re-parsing inside loops; repeated JSON (de)serialisation of the
  same data; copying large numpy arrays unnecessarily (`.copy()`, `np.array(existing)`).
- Python loops over geometry/pixels; string concatenation in loops for large outputs.
- Tool flags as magic strings outside adapters; shell-like string commands.
- Comments restating the code, stale docstrings, emoji/log noise, commented-out code.
- Overly long functions that mix I/O, parsing and business logic.
- Signal/slot connections never disconnected; QObjects without parents leaking; threads not joined.
- `processEvents()` or `QTimer` polling used instead of proper worker/signal design.
- Tests that duplicate implementation logic to compute expected values.
- Inconsistent naming for the same concept (e.g. `course_model` vs `courseModel` vs `model`).
- Logging at INFO inside hot loops; f-strings in logging calls on hot paths (use lazy `%s`).

## 4. Deep Clean procedure (after P5, P8, P13)
1. **Measure** and paste results in the report:
   - `radon cc -s -a src/` (list anything worse than B), `xenon` thresholds
   - `vulture src/ --min-confidence 60` (triage every hit)
   - `pylint --disable=all --enable=duplicate-code src/`
   - coverage per module (core ≥ 85 %, gui ≥ 60 % via pytest-qt)
   - `uv tree` / dependency list; unused dependency check
   - line counts per package; files > 400 lines; functions > 60 lines
   - benchmarks vs BENCHMARKS.md baseline; `python -X importtime` top 15
2. **Simplify:** target deleting ≥ 5 % of lines in touched packages without losing behaviour
   (removing dead code, merging duplicates, collapsing needless layers). Every deletion keeps tests green.
3. **Performance:** profile the slowest user-visible operation (pyinstrument/py-spy); fix the top
   hotspot if it's cheap; otherwise log a task.
4. **Consistency:** naming, error messages tone, logging levels, event names, settings keys.
5. **Docs sync:** ARCHITECTURE.md reflects the real module structure; remove stale sections.
6. Record new baselines; tag `deepclean-N-done`.

## 5. UI checklist (review screenshots in light and dark themes)
- [ ] One primary action per card/page is visually obvious; destructive actions need confirmation.
- [ ] Status never conveyed by colour alone (icon + text).
- [ ] Plain-language labels; jargon has a tooltip or "What is this?" link.
- [ ] No truncated text at 1280×720 and at 150 % scaling.
- [ ] Empty states explain what to do next; errors offer "Copy details" and a next step.
- [ ] Keyboard: logical tab order, shortcuts for Build (Ctrl+B) and Cancel (Esc during build).
- [ ] Long operations show progress and can be cancelled; the window stays responsive.
- [ ] Advanced options are reachable but not in the beginner's path (collapsed sections / Advanced tab).
- [ ] Every generated file has "Open in…" and "Reveal in file manager".

## 6. Metric thresholds (defaults — change only via DECISIONS.md)
| Metric | Threshold |
|---|---|
| Cyclomatic complexity per function | ≤ 10 (radon grade B) |
| File length | ≤ 400 lines |
| Function length | ≤ 60 lines |
| Core coverage | ≥ 85 % |
| GUI coverage | ≥ 60 % |
| Benchmark regression | ≤ 10 % (preview/GL on llvmpipe: ≤ 25 %) |
| Vulture findings (confidence ≥ 80) | 0 unexplained |
