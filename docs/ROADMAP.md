# Roadmap

Each phase ends with a **review gate** (skill `mkw-phase-review`). Three phases additionally end
with a **Deep Clean**. **HC** = human checkpoint (see `docs/process/HUMAN_CHECKPOINTS.md`).
Work continues on unblocked tasks while waiting for a human checkpoint response.

| # | Phase | Goal (user-visible result) | Gate |
|---|---|---|---|
| 0 | Environment, toolchain & spikes | Tools run in the container; provisional decisions resolved with evidence | Review · **HC0** |
| 1 | Skeleton & quality gates | Empty app launches; `check.py` + CI (Linux & Windows) green | Review |
| 2 | Tools: registry, runner, doctor | `trackstudio doctor` finds and versions every tool | Review |
| 3 | Project model & status | `trackstudio new/status` with component statuses | Review |
| 4 | Build engine & SZS assembly | `trackstudio build` makes a valid SZS from manual files; no-op rebuild < 1 s | Review |
| 5 | GUI shell & dashboard | Same as P4 in the GUI: cards, open-in-tool, issues, logs | Review · **HC1** · **Deep Clean #1** |
| 6 | Blender bridge | Saving the `.blend` produces fresh exports automatically | Review |
| 7 | Course model pipeline | DAE → BRRES with texture formats, material rules, preserved external edits | Review · **HC2** |
| 8 | Collision, minimap, skybox, post-effects, objects | All non-KMP components automated | Review · **Deep Clean #2** |
| 9 | 3D preview | Collision/source/minimap preview in-app | Review |
| 10 | KMP workflow & validation hub | KMP checklist, editor launch/watch, starter KMP, unified issues | Review · **HC3** |
| 11 | Dolphin testing & release build | "Build & launch Dolphin"; release packaging of the track | Review |
| 12 | Onboarding & installers | First-run wizard; Windows + Linux installers | Review · **HC4** |
| 13 | Final optimisation & hardening | Budgets met, dead code gone, fuzzed parsers | **Deep Clean #3** · v1.0 RC |
| 14 | Optional extras | BrawlCrate bridge plugin, Blender live link, macOS evaluation | Review |

## Dependencies
- P0 must finish before P1 (it may change the stack).
- P2 → P3 → P4 → P5 are strictly sequential.
- After P5: P6 → P7 sequential; P8 depends on P6 (+ minimap may depend on P7's backend).
- P9 can start after P8-T01 (KCL reader). P10 depends on P9 for the KMP overlay only (other P10
  tasks can start after P8).
- P11 after P10. P12 after P11. P13 last. P14 any time after P12 if the human asks.

## Milestones that matter to the human
- **M1 (end P5):** "Drop in my files, click Build, get a working SZS" — already saves time.
- **M2 (end P7):** "Save in Blender → course model rebuilt with my texture/material choices."
- **M3 (end P10):** "Everything except placing KMP data is automatic, and the app tells me what's missing."
- **M4 (end P12):** "Installable app a friend can use."

## Definition of done for v1
- All components in PROJECT_BRIEF §5 work in auto and manual modes on Windows and Linux.
- External edits are detected and never lost.
- Budgets in ARCHITECTURE §15 met (or amended with evidence).
- CI green on both OSes including integration tests with real tools.
- HC1–HC4 passed; no open "Must fix" review items.
- User docs cover conventions, every component, and troubleshooting.

## Future ideas (not scheduled — do not build without the human's go-ahead)
In-app KMP object placement; BRRES material preview via `rszst brres-to-json`; distribution/LE-CODE
pack builder; BRSTM music conversion; track thumbnail generator; multi-track workspaces; macOS
packaging; noclip.website-style web preview export.
