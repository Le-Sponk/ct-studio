# READ ME FIRST — MKW Track Studio handoff kit

This kit is everything an agent needs to build the app without coming back to the planner. You set
it up once (≈20 minutes), then mostly paste "Continue" and answer occasional checkpoints.

## What's inside
| Path | Who reads it | Purpose |
|---|---|---|
| `README_FIRST.md` | You | This guide (you can delete it from the repo after setup) |
| `KICKOFF_PROMPT.md` | You | Prompts to paste into Hermes (first session, continue, gates, feedback) |
| `AGENTS.md` | Agent (auto-loaded every message) | Short hard rules and a map of the docs |
| `STATUS.md` | Both | Live progress, blockers, and questions for you |
| `docs/PROJECT_BRIEF.md` | Both | Vision, principles, scope, UX concept |
| `docs/ARCHITECTURE.md` | Agent | Stack, layers, build graph, reconciliation, budgets |
| `docs/DECISIONS.md` | Both | Decision records (some provisional until Phase 0 proves them) |
| `docs/ROADMAP.md` | Both | Phases, milestones, gates, checkpoints |
| `docs/phases/PHASE_00…14` | Agent | Task lists with acceptance criteria |
| `docs/process/` | Agent (+ you for checkpoints) | Workflow, reviews, testing, human checkpoints |
| `docs/reference/` | Agent | MKW domain notes and external tool catalogue |
| `skills/mkw/` | Hermes | Two skills: `mkw-task-loop`, `mkw-phase-review` |

## Setup (once)
1. **Create a new repository** (separate from the Blender add-on), e.g. `mkw-track-studio`, and push it
   to GitHub. Enable GitHub Actions — this is how Windows gets tested continuously without you.
2. **Copy the kit into the repo root** (everything except the `skills/` folder can live in the repo;
   keeping `skills/` in the repo too is fine as a backup). Commit: `chore: add planning kit`.
3. **Make the repo visible to both Hermes and your desktop.** Keep the repo in a host folder (e.g.
   `~/dev/mkw-track-studio`) and bind-mount it into the Hermes container/sandbox. That way the agent
   works inside Docker while you can run the GUI on Linux Mint for checkpoints.
4. **Install the skills.** Copy `skills/mkw/` into your Hermes skills directory: on the host that's
   `~/.hermes/skills/mkw/` (the official Docker image maps `~/.hermes` to `/opt/data`, so inside the
   container it appears under `/opt/data/skills/mkw/`). Start a new session and run `/skills` — you
   should see `mkw-task-loop` and `mkw-phase-review`.
5. **Give the agent git push access** to the repo (deploy key or token), or plan to push yourself.
6. **Sandbox permissions.** Phase 0 needs to download tools (szs.wiimm.de, github.com, blender.org,
   pypi) and may need system packages (OpenGL/Qt libraries, Xvfb). If your container can't install
   packages, the agent will write a `docker/dev.Dockerfile` and ask you to rebuild the sandbox — that's
   expected, not a failure.
7. **Start Hermes in the repo root** and paste prompt 1 from `KICKOFF_PROMPT.md`.

## Recommended way to run it
- **One task per session.** Paste prompt 2 ("Continue…") in a fresh session each time. STATUS.md is the
  memory between sessions, so nothing is lost.
- **Use your strongest model** for Phase 0 (spikes), Phase 1 (foundations), every phase gate and Deep
  Clean, and the tricky tasks (P4 build engine, P7 reconciliation, P9 preview). Well-specified
  tasks (dialogs, parsers with recordings, docs) can use a cheaper model.
- **Check STATUS.md occasionally.** "Needs human — BLOCKING" means something is waiting on you; the
  agent keeps working on unblocked tasks meanwhile.
- **Optional but valuable:** put one or two of your own real track projects (the `.blend`, SZS, or
  extracted files) in `local_fixtures/` inside the repo. It's gitignored; tests use it only locally.

## Your time commitment
| Checkpoint | When | Time | What you do |
|---|---|---|---|
| HC0 | End of Phase 0 | ~10 min | Confirm licence/name, GitHub, bind mount, backend choice |
| HC1 | End of Phase 5 | ~15 min | Build an SZS from existing files in the GUI, race it |
| HC2 | End of Phase 7 | ~25 min | Blender → course model; edit in BrawlCrate; confirm edits survive rebuild |
| HC3 | End of Phase 10 | ~30 min | Full workflow incl. collision, minimap, KMP editing |
| HC4 | End of Phase 12 | ~30 min | Install packaged builds on Windows + Linux, first-run as a beginner |
Exact steps and a feedback template are in `docs/process/HUMAN_CHECKPOINTS.md`.

## Assumptions I made (change them at HC0 if wrong)
- "Compatible" means **Windows and Linux are first-class**; macOS is best-effort.
- Working name **MKW Track Studio** (Python package `trackstudio`) — renaming later is a single task.
- Licence **GPL-3.0-or-later** (compatible with reusing GPL-2.0-or-later code from your add-on).
- The app lives in a **new repo**; your add-on is pulled in as a pinned git submodule. Any changes to the
  add-on itself (e.g. a live-link panel) are proposed to you first, because that repo is yours.
- The app never ships Nintendo files; features that need original tracks (templates, auto-add objects,
  Dolphin test setup) ask you to point at your own extracted game.

## Key decisions and why (details in `docs/DECISIONS.md`)
- **Python 3.12 + PySide6 (Qt).** Your add-on and ABMatt are Python; agents are most reliable in Python;
  Qt is mature on Windows/Linux and can be tested headless. The slow work happens in native tools, so
  Python isn't the bottleneck.
- **Logic separate from the GUI, with a matching command line** (`trackstudio build/status/doctor`).
  This lets the agent test nearly everything without a screen, and gives veterans scripting.
- **Incremental builds with content hashing.** Only changed parts rebuild; a no-change rebuild should take
  under a second. This is the biggest efficiency win in the whole app.
- **External tools always run as separate programs** through small typed adapters. ABMatt pins very old
  libraries, so importing it would poison the app's dependencies.
- **Course model backend is chosen by evidence in Phase 0.** RiiStudio's CLI looks strongest (best geometry
  optimisation, material presets, JSON round-trip) but has no Linux build and uncertain maintenance;
  ABMatt is the fallback. The app supports both behind one interface.
- **BrawlCrate stays a first-class escape hatch, not an automation target.** It can't be driven headlessly.
  Instead the app detects your edits, captures material settings, and reapplies them after every rebuild,
  with backups. An optional BrawlCrate bridge plugin is listed in Phase 14.
- **Minimap is automatic by default**, generated from the road-type collision surfaces and positioned with
  `wszst minimap --auto`.
- **Quality is enforced by tooling, not goodwill:** import rules, complexity/size limits, dead-code and
  duplicate detection, benchmarks with budgets, fresh-context phase reviews, and three Deep Cleans.

## What I could not verify from here (Phase 0 checks these first)
- Exact `wszst create`/`check` invocation details and whether `check` has a machine-readable mode.
  (Note: in `wszst`, `-d` is `--dest` and needs a path.)
- RiiStudio CLI import options for BRRES, its licence, and whether it builds on Linux.
- Whether RiiStudio presets / ABMatt name-matching preserve settings from a **BrawlCrate**-edited file.
- Which editors accept a file path on the command line (BrawlCrate, RiiStudio, Lorenzi's, KMP Cloud).
- The most reliable way to launch Dolphin with a test track.
- Your add-on's exact operator names for headless export.

## If something goes wrong
- The agent is looping or drifting → prompt 6 in `KICKOFF_PROMPT.md`.
- Tests keep failing in the container because of missing libraries → approve the Dockerfile it proposes.
- You disagree with a decision → write it under "Needs human — BLOCKING" in STATUS.md yourself (or tell the
  agent); it will supersede the ADR and update the affected phases before continuing.
- You want a quick progress report → prompt 7.
