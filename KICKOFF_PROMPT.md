# Prompts to paste into Hermes

Start Hermes with the **repository root as the working directory** so `AGENTS.md` is loaded.
Use a fresh session for each prompt below (`/new`), then name it (`/title ...`).

---

## 1. First session (paste once)

```
You are starting a new project: CT Studio. The repository currently contains only planning
documents; no application code exists yet.

Before doing anything else:
1. Read AGENTS.md (already loaded), then STATUS.md, then docs/PROJECT_BRIEF.md, docs/ROADMAP.md and
   docs/process/WORKFLOW.md. Skim docs/ARCHITECTURE.md and docs/DECISIONS.md so you know where
   things are, but don't memorise them.
2. Confirm the skills `mkw-task-loop` and `mkw-phase-review` are available (/skills). If they are
   not, tell me and stop.
3. In 10 lines or fewer, tell me: what you are building, how work is organised, and which task you
   will do first. Then flag anything in the plan that looks contradictory or impossible in your
   environment — don't fix it yet.

Then start task P0-T01 using the mkw-task-loop skill. Treat the plan as a well-researched hypothesis:
Phase 0 exists to verify it. Record evidence, update the plan when evidence disagrees, and keep
STATUS.md current. Stop at the end of the task.
```

## 2. Every following session

```
Continue CT Studio. Use the mkw-task-loop skill: read STATUS.md, take the next task,
complete it fully (tests, checks, docs, STATUS.md, commit), then stop and summarise in 5 lines:
what was done, evidence it works, what's next, and anything you need from me.
```

## 3. Phase gate (when STATUS.md says the next item is a -GATE)

```
Run the phase gate for the current phase using the mkw-phase-review skill. The review must be done
by a delegated reviewer with fresh context. Fix all Must/Should findings, record the gate, and tell
me if a human checkpoint is due (with the exact steps for me).
```

## 4. Deep Clean (when STATUS.md says the next item is a -DEEPCLEAN)

```
Run the Deep Clean using the mkw-phase-review skill (Deep Clean procedure). Measure first, simplify
in small behaviour-preserving commits, update benchmark baselines, and report before/after numbers.
```

## 5. After a human checkpoint (paste your filled-in feedback template under this)

```
Here are my results for the human checkpoint below. Record them in STATUS.md under
"Human checkpoint results", convert every issue into a task ID in the right phase file (blockers
first), answer my questions, and tell me the new plan in 5 lines. Don't implement anything this session.

<paste feedback template here>
```

## 6. If the agent drifts

```
Stop. Re-read AGENTS.md and STATUS.md. Tell me which task you are on and which hard rule(s) the
current work breaks, if any. If the working tree contains unrelated or unverified changes, stash them
on a branch named wip/<task-id>, return to the last green commit, and restart the task with a plan
of at most 6 steps.
```

## 7. When you want a status report without work

```
Read STATUS.md and the current phase file. Report: phase progress (tasks done/total), last gate,
open "Needs human" items, blocked tasks, tech debt count, and your honest risk assessment for the
next phase. No code changes.
```
