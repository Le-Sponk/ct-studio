# Workflow

## 1. Unit of work
- A **task** is one ID in a phase file (e.g. `P5-T03`). One task per Hermes session.
- If a task will clearly take more than ~400 changed lines or several sessions, split it first:
  add `P5-T03a/b/c` entries to the phase file (each with acceptance criteria), log the split in
  STATUS "Plan changes", then do `a`.
- Start each task in a fresh session (`/new`) and name it (`/title P5-T03 dashboard cards`).
  STATUS.md is the memory between sessions — not the chat history.

## 2. Session protocol (the `mkw-task-loop` skill mirrors this)
1. **Orient:** STATUS.md → phase file → referenced docs only. Check the task's dependencies are done.
2. **Plan:** write under STATUS "In progress": task ID, 3–6 step plan, acceptance criteria restated,
   files expected to change, risks. Keep it ≤ 15 lines.
3. **Verify assumptions:** any external tool flag/format you rely on is already in TOOLS.md with a
   version — if not, verify now (run `--help`/real command) and record it.
4. **Test first where practical:** write/extend tests that express the acceptance criteria.
5. **Implement** the smallest change that passes. Prefer deleting/simplifying over adding.
6. **Check:** `uv run python scripts/check.py`. If you touched adapters/pipelines, also
   `uv run pytest -m integration -k <area>`. If you touched GUI, run the GUI tests and look at the
   screenshots (or list them for the human if you can't view images).
7. **Self-review** the diff against REVIEW_CHECKLIST.md §3 (smells). Fix what you find.
8. **Document:** TOOLS.md facts, DECISIONS.md if a decision changed, user docs if user-visible,
   BENCHMARKS.md if performance-relevant.
9. **Close:** tick `[x]` in the phase file with the short commit hash; move the STATUS entry to "Done";
   set "Next task"; commit (`P5-T03: dashboard component cards` + body with what/why/tests).

## 3. Definition of Done (task)
- Acceptance criteria demonstrably met (tests or recorded evidence).
- `check.py` green; no new warnings; coverage of new core code ≥ 85 %.
- No TODO without a task ID. No commented-out code. No debugging prints.
- Budgets respected (AGENTS.md rule 8/9). Cross-platform concerns considered (paths, processes).
- Docs updated. STATUS.md updated. Committed.

Before P1-T02, apply ADR-016: recorded acceptance commands and task-specific tests,
diff review, `git diff --check`, and local file-link checks for documentation-only tasks.
The missing `check.py` is not a green result; do not create a stub to satisfy this rule.

## 4. Context hygiene (Hermes-specific)
- AGENTS.md is injected into every message: don't grow it; put detail in docs.
- Don't paste large logs into the conversation — read tails (`tail -n 80`) or grep.
- Use `/compress` when a session gets long; if you need it twice, the task was too big — split it.
- Use `delegate_task` for: phase reviews (reviewer must not share the implementer's context),
  verifying a tool's CLI behaviour, researching a format spec, writing tests for an independent
  module. Give subagents file paths and the exact question; ask for concise findings.
- Save durable facts to memory sparingly (e.g. "Blender binary at .tools/blender-5.2/blender").
  Procedures belong in skills; project facts belong in docs.

## 5. Branches and commits
- `main` must always pass `check.py`. Work directly on `main` in small commits, or on
  `phase-XX` branches merged at the gate — pick one at P1 and record it in DECISIONS.md.
- Tag each passed gate: `phase-05-done`. Deep cleans: `deepclean-1-done`.
- Never rewrite published history. Never commit `.tools/`, `.ctstudio/`, game files, or large binaries.

## 6. When stuck
1. Timebox: 45 minutes of failed attempts on the same problem → stop.
2. Write what you tried and what you observed under STATUS "Blocked tasks".
3. Look for an alternative listed in the phase file/ADR; if one exists and doesn't change scope, try it.
4. Otherwise mark the task blocked, add a precise "Needs human" item (question, options, your
   recommendation, what's blocked), and continue with the next unblocked task.
5. Never "fix" a failing test by weakening it without writing down why the test was wrong.

## 7. When the plan is wrong
Plans are hypotheses. When evidence contradicts them:
- Update the ADR (supersede, don't erase) and the affected phase tasks in the same commit.
- Log in STATUS "Plan changes" with a link to the evidence (spike notes, tool output).
- Scope changes visible to the user (removing a feature, adding a dependency on the user doing
  something) require a "Needs human" item before implementation.

## 8. Asking the human
Only through STATUS.md "Needs human" (BLOCKING or non-blocking). Each item: one clear question,
2–3 options with consequences, your recommendation, and what is waiting on it. Batch questions so
the human can answer several at once. Human checkpoints use `HUMAN_CHECKPOINTS.md`.

## 9. Performance habits (always on)
- Anything touching geometry, images or files > 10 MB gets a benchmark or at least a timing log line.
- No per-element Python loops over vertices/triangles/pixels — use numpy.
- Don't read the same file twice in one operation; pass data or fingerprints along.
- Don't start Blender more than once per build. Don't re-run a tool whose inputs haven't changed.
- UI: long work → worker + signal. Never `processEvents()` loops as a substitute.
