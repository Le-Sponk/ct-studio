# Human checkpoints

The human tests only what automation cannot: the real game, real tracks, real Windows habits, taste.
Before requesting a checkpoint the agent must: pass the phase review, write exact instructions
(copy-pasteable commands) into the "Needs human — BLOCKING" section of STATUS.md, and continue with
unblocked tasks while waiting. The human replies by pasting the feedback template (bottom) into
STATUS.md under "Human checkpoint results" (or into the chat); the agent turns each issue into a task ID.

---

## HC0 — Kick-off decisions (≈10 min, end of Phase 0)
Agent provides: spike summary (1 page), any Dockerfile changes needed, recommendations.
Human confirms:
1. Licence GPL-3.0-or-later OK? (Name settled before Phase 0 ended: ADR-015, CT Studio.)
2. Is the repo on GitHub with Actions enabled (needed for Windows CI)? Can the agent push?
3. Is the repo folder bind-mounted so the human can run the GUI on the Linux Mint host?
4. Will you provide real track files in `local_fixtures/` (optional but valuable)? Which?
5. Windows machine available for HC2/HC4? Do you use BrawlCrate natively or via Wine?
6. Approve BRRES backend recommendation and any scope changes from spikes.

## HC1 — Manual-mode MVP (≈15 min, end of Phase 5)
On the Linux Mint host, in the repo folder:
1. `uv sync` then `uv run ctstudio`.
2. First launch: open Settings → Tools; confirm Wiimms tools are detected (point to them if not).
3. New project → choose a folder → skip the `.blend` → pick a slot.
4. Assign existing files from one of your tracks (course_model.brres, course.kcl, course.kmp,
   map_model.brres, vrcorn_model.brres, posteffect folder) by drag & drop.
5. Build test SZS. Check the Issues panel makes sense.
6. Put the SZS in your usual test setup (Riivolution / extracted game / My Stuff) and race one lap.
7. Try "Open in…" for the BRRES and the KMP. Edit and save something in an editor; confirm the card
   notices and the choices make sense.
Report: anything confusing, slow, ugly, or wrong; screenshots welcome.

## HC2 — Course model automation (≈25 min, end of Phase 7)
1. New project from a real `.blend` (or the fixture if you prefer); review the collection mapping.
2. Build & race: textures correct? transparency (fences, water) correct? any Harry Potter effect?
   performance/slowdown compared with your usual BrawlCrate/RiiStudio import?
3. Textures page: do the recommended formats match what you would choose? Change one; rebuild; check.
4. Materials page: set a material to double-sided/cutout; rebuild; check in game.
5. Open `course_model.brres` in **BrawlCrate** (Windows or Wine), change a material setting you care
   about (e.g. transparency/blend/shader), save. In CT Studio choose "Keep & capture".
6. Change something in Blender (move a mesh), save — auto-rebuild — confirm your BrawlCrate edit
   survived in game.
   **From S4 (P0-T07), these are the specific unknowns this step exists to settle.** The spike
   proved the capture mechanism (`rszst dump-presets` → `--preset-path`) on a 4-material synthetic
   model, covering xlu, blend mode, cull mode and one SRT0. Still unverified, so test them here:
   - a **TEV stage / shader** edit, an **indirect texture**, a **multi-layer** material, a
     **PAT0 or CLR0** animation, and **LightSet/FogSet** indices — does the preset carry each?
   - does a **BrawlCrate-saved** BRRES re-import into rszst at all? S3b found rszst rejects
     ABMatt output (`Invalid quantization for normal data: U16`); if BrawlCrate output hits the
     same wall, capture must move to *before* the edit and ARCHITECTURE §8 changes materially.
   - rename a material in Blender and confirm CT Studio **reports the orphaned capture** rather
     than silently dropping it (no tool does this for us).
   - real material counts and timings, versus the spike's four.
7. Windows spot check: install/run from the repo on Windows (`uv sync`, `uv run ctstudio`) and
   repeat steps 1–2 briefly.

## HC3 — Full workflow (≈30 min, end of Phase 10)
1. From a `.blend` with collision: build; open the Preview — are KCL colours/flags as expected?
2. Minimap: race — is the minimap aligned and shaped correctly?
3. KMP: start from "Starter KMP" or your own; click "Edit KMP"; place/change checkpoints in the
   editor; save; confirm the checklist updates.
4. Build & race a full 3-lap race: lap counting, respawns, item boxes/objects (if game files set up).
5. Is anything still forcing you to leave the app that shouldn't?

## HC4 — Installable release (≈30 min, end of Phase 12)
1. Install the packaged app on Windows and on Linux Mint (from CI artefacts) on a profile without
   the dev environment.
2. Walk through the first-run wizard as a beginner would. Note every moment of confusion.
3. Create a track project from scratch and get to racing in Dolphin with "Build & launch".
4. Try one veteran action: a post-import ABMatt command file or a custom tool in "Open in…".
5. Record cold-start time and whether anything felt slow.

---

## Feedback template
```
HC#: 
Date / OS / tool versions (if relevant):
Overall: works | mostly works | blocked
Issues:
- [severity: blocker|major|minor|polish] what I did → what happened → what I expected (screenshot?)
- ...
Wishes / ideas (not bugs):
- ...
Answers to questions:
- ...
```
