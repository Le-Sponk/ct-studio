# Phase 8 — Collision, minimap, skybox templates, post-effects, objects

**Goal:** every component except KMP content is automated, with manual/template alternatives.
**Read first:** SPIKES.md §S1/§S5, MKW_DOMAIN.md (KCL, minimap, objects, legal).
**Exit:** fixture builds fully automatically (with a manual KMP); Deep Clean #2 done.

### [ ] P8-T01 — KCL reader (read-only, numpy)
`core/formats/kcl.py`: parse header, vertices, normals, prisms into numpy arrays; derive triangles,
flags, base types (lower 5 bits), extents; no octree traversal needed for stats/preview. Start from
the add-on's `kcl_parse.py` (GPL-2.0-or-later; keep attribution). Flag/type names come from one table
shared with the add-on's definitions (import the names by reading its source at build time or copy
with attribution — never retype from memory).
**Acceptance:** cross-validated against `wkclt` analyze/flags on the fixture (integration); corrupt
input raises `ParseError`; 500k triangles parsed < 0.5 s (benchmark with a generated KCL).

### [ ] P8-T02 — KCL node & card
Modes: auto (from Blender export, P6), manual `.kcl`, manual OBJ + `.flag` file → `wkclt` encode.
Options surfaced: un-bean mode, extra `wkclt` args. Card summary: triangles, per-type counts, extents.
Own checks → Issues: coordinates beyond ±131071, no road-like triangles, no walls, no fall boundary
(info level), unusually many types/triangles (threshold data-driven).
**Acceptance:** tests per mode; Issues on crafted bad fixtures.

### [ ] P8-T03 — Minimap node
Modes: auto from KCL (default), from Blender collection, manual file. Implement the S5-recommended
path; KCL type filter from manifest (`include_kcl_types`, sensible defaults: road-like, boost, jump,
excluding walls, invisible walls, fall boundaries, triggers). Always finish with
`wszst minimap --auto` unless the user disables it. Thumbnail: simple numpy→Pillow top-down
rasteriser (upgrade to GL preview in P9) saved to `.ts/thumbs/minimap.png`.
**Acceptance:** fixture minimap builds headless; changing the filter invalidates only minimap +
assemble; thumbnail generated < 300 ms.

### [ ] P8-T04 — Game files setup (optional feature, consent-gated)
Settings → Game files: user selects their extracted `Race/Course` folder (or an extracted game root).
Detect validity (expected file names from the slot catalogue). Explain what it unlocks (skybox/
post-effect templates, auto-add objects) and that nothing is uploaded or copied into git. Offer to
create the Wiimms auto-add library (`wszst autoadd <Race/Course>` per S1 findings) into the user data
dir.
**Acceptance:** tests with a fake folder structure (empty dummy files with correct names); real-data
tests marked `realdata`.

### [ ] P8-T05 — Skybox template & manual modes
Template: extract `vrcorn_model.brres` from a chosen original track SZS in the game files (via
`wszst` extract to `.ts/templates/<track>/`, cached). Manual: user file. Card shows source.
**Acceptance:** fake-tool tests; `realdata` integration test.

### [ ] P8-T06 — Post-effects
Template mode (copy `posteffect/` from a chosen original track, cached extraction), manual folder
mode, "Open in RiiStudio" for `.blight/.blmap/.bdof/.bblm/.bfg` files. Card lists files present.
If no game files are configured, explain the consequence of missing post-effects as reported by
`wszst check` and offer manual mode.
**Acceptance:** tests; external edits to post-effect files follow the P5 watcher rules (Manual lock).

### [ ] P8-T07 — Objects via auto-add
Assemble uses `--auto-add` when the library exists; parse which files were added (S1 output format)
into the Objects card ("12 object files added automatically"); warn when KMP references objects but
no library is configured.
**Acceptance:** fake-tool tests; `realdata` integration test.

### [ ] P8-T08 — Full auto fixture build
E2E test (`slow`): fixture `.blend` + fixture KMP → complete SZS with all auto components (templates
skipped without game files) → `wszst check` issues limited to the known list.
**Acceptance:** green on Linux + Windows integration CI.

### [ ] P8-GATE — Phase review
### [ ] P8-DEEPCLEAN — Deep Clean #2
