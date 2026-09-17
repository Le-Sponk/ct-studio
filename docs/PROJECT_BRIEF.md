# Project Brief — MKW Track Studio (working name)

## 1. The problem
Making a Mario Kart Wii custom track means juggling a 3D editor, a KCL exporter, a BRRES converter
(BrawlCrate / RiiStudio / ABMatt), texture-format decisions, a minimap workflow, a KMP editor,
Wiimms SZS Tools commands, and an emulator — each with its own files, conventions and failure modes.
Most time is lost on plumbing: finding the right file, re-running the right command in the right
order, re-applying the same material fixes after every re-import, and discovering errors late.

The Blender side has already been modernised (Blender-MKW-Utilities fork: KCL/DAE/OBJ export,
Blender 3.x–5.2, Windows + Linux). This project builds the hub that connects everything else.

## 2. Vision
One clean app that shows every part of a track, knows what state each part is in, rebuilds only what
changed, and gets you from "saved in Blender" to "racing in Dolphin" with one click — while every
automated step stays inspectable, configurable and overridable.

## 3. Users
- **Beginner:** has a Blender model. Wants defaults that work, plain-language explanations, and to
  open another program only when unavoidable (placing checkpoints/routes in a KMP editor).
- **Veteran:** has habits and edge cases (custom shaders, animations, hand-tuned materials, odd
  slots, LE-CODE features). Needs to drop into BrawlCrate/RiiStudio/hex editors instantly, keep those
  edits across rebuilds, pass extra flags to tools, and script around the app.

## 4. Principles (use these to settle design debates)
1. **Automate the obvious, expose the rest.** Defaults are preset; every default can be changed.
2. **Never trap the expert.** Any file can be opened in any configured tool from the app. Any
   component can be switched to *Manual* ("I'll supply this file").
3. **Never destroy manual work.** Detect external edits, offer to capture/keep them, back up before
   overwriting.
4. **Plain files.** A project is a normal folder with a readable `trackstudio.toml`. The staging
   folder is a valid `wszst create` input. The project remains usable without the app.
5. **Transparent.** The log shows the exact command lines run; each can be copied.
6. **Fast feedback.** Incremental builds with content hashing; a no-change rebuild takes < 1 s.
7. **Cross-platform by construction.** Windows and Linux are first-class; macOS best-effort.
8. **Lean.** Efficient code, small dependency set, periodic clean-ups (see review process).

## 5. Track components (what the dashboard shows)
| Component | Output in SZS | Default mode | Automation target |
|---|---|---|---|
| Course model | `course_model.brres` | Auto from Blender collection | DAE export → BRRES import → texture formats → material rules → reapply captured edits |
| Collision | `course.kcl` | Auto from Blender (`_F####` objects) | Plugin KCL export (wkclt), stats, warnings |
| Minimap | `map_model.brres` | Auto from KCL road-like flags | Filter → map model → `wszst minimap --auto` |
| Skybox | `vrcorn_model.brres` | Auto from Blender collection, or template/manual | Same BRRES pipeline with model name `vrcorn` |
| KMP | `course.kmp` | Manual (external editor) | Starter file, readiness checklist, launch editor with KCL alongside, watch saves |
| Post-effects | `posteffect/*` | Template (from user's own game files) or manual | Copy + "Open in RiiStudio" |
| Objects | object BRRES/KCL/effects | Auto-add (Wiimms library from user's game files) | `wszst create --auto-add` |
| Track info | file name, slot, credits | Wizard | `wszst slots` helper, release naming |
| Validation | — | Always | `wszst check` + own checks → one issues list |

Component status values: **Missing · Stale · Ready · Warning · Error · Manual · Edited externally**.

## 6. UX concept (dashboard)
```
┌ MKW Track Studio — Sponk Speedway ───────────────────────── Slot: Luigi Circuit ▾ ┐
│ Source: track.blend   [Open in Blender]   Rebuild when .blend is saved: ●          │
│                                                                                    │
│ ✔ Course model   12 materials · 18 textures · 2.1 MB  [Rebuild][Textures][Materials][Open in ▾] │
│ ✔ Collision      148k tris · 9 flag types             [Rebuild][Preview][Open in ▾]  │
│ ⟳ Minimap        Stale — collision changed             [Rebuild][Preview]            │
│ ✖ KMP            Missing: checkpoints, enemy routes    [Open KMP editor][Starter KMP]│
│ ● Skybox         Manual file                           [Replace][Open in ▾]          │
│ ● Post-effects   From Luigi Circuit template           [Change][Open in RiiStudio]   │
│ ⚠ Validation     2 warnings                             [Details]                    │
│                                                                                    │
│ [ Build test SZS ]   [ Build & launch Dolphin ]                   Release build ▸   │
│ ▸ Log                                                                              │
└────────────────────────────────────────────────────────────────────────────────────┘
```
Detail pages (Textures, Materials, Collision, KMP checklist, Preview) open from cards. A first-run
wizard locates tools; a new-project wizard asks for name, folder, `.blend`, slot — then "Done".

## 7. Scope for v1
In: everything in §5, 3D preview (collision colours by flag, source geometry, minimap, KMP overlay),
external-edit reconciliation, Dolphin test launch, release build, installers for Windows + Linux.

Out of v1 (possible later): a full in-app KMP editor; replacing BrawlCrate's material editor;
distribution/LE-CODE pack building; music (BRSTM) conversion; official macOS support; ISO patching
beyond what test launching needs; BrawlCrate bridge plugin (optional phase 14).

## 8. Legal/ethical constraints
The app never ships Nintendo files. Features that need original tracks (templates, auto-add
library, Dolphin test copy) ask the user to point at **their own** extracted game files, with
consent and a clear explanation. Third-party tools are downloaded only from official sources.

## 9. Glossary
SZS (Yaz0-compressed U8 archive) · BRRES (model/texture archive: MDL0, TEX0, SRT0…) · KCL (collision)
· KMP (course data: start, checkpoints, routes, objects, cameras, areas) · Slot (which original
track file is replaced, e.g. `beginner_course.szs` = Luigi Circuit) · CMPR (4-bit compressed texture
format) · Auto-add (Wiimms library that inserts object files referenced by the KMP) · HC (human
checkpoint) · ADR (architecture decision record). See `docs/reference/MKW_DOMAIN.md`.
