# Mario Kart Wii domain notes

Purpose: enough domain knowledge to build the app correctly. Items marked **(verify)** must be
confirmed against an authoritative source or a real tool run before code depends on them; record
the confirmation (source link or command output) next to the item.
Primary references: mkwiiki.org (formerly wiki.tockdom.com) — *Custom Track Tutorial*, *Creating a
Minimap*, *Creating a BRRES with RiiStudio*, *KMP*, *KCL*, *Common Crash Causes*; szs.wiimm.de guides
(KMP text format, KCL guide, wszst command reference).

## 1. Track file (SZS)
- `.szs` = Yaz0-compressed U8 archive. Original tracks live at `Race/Course/<name>.szs`.
- Per the Custom Track Tutorial, these are required for a track to load: `course_model.brres`
  (visual model), `vrcorn_model.brres` (skybox/background), `map_model.brres` (minimap), `course.kcl`
  (collision), `course.kmp` (course data), `posteffect/` (fog, bloom, lighting, etc.).
- Tracks often also contain object files (BRRES/KCL for objects referenced by KMP GOBJ), `effect/`
  and `brasd/` folders; Wiimms' **auto-add** can insert missing object files automatically when the
  user has built an auto-add library from their own game files.
- Each original track has a `_d.szs` sibling (e.g. `beginner_course_d.szs`) that the game loads in
  some modes **(verify which modes)**; custom tracks commonly ship identical content in both.
- The slot (which original file name is replaced) matters: some objects/behaviours only work in
  certain slots. `wszst slots` analyses a track and proposes compatible slots.
- `wszst create <dir>` builds an SZS from a directory tree; `wszst check` validates KCL/KMP and
  finds unknown/missing/unneeded files; `wszst list` shows contents.

## 2. Course model (BRRES)
- BRRES is an archive containing MDL0 (models), TEX0 (textures), SRT0 (texture animations), CHR0,
  CLR0, PAT0, VIS0. The course model's MDL0 is conventionally named `course`; skybox `vrcorn`; minimap
  `map` (see §5).
- Converters: BrawlCrate/BrawlBox (GUI, Windows), RiiStudio (GUI + `rszst` CLI), ABMatt (CLI/GUI).
- **Facepoints / primitives:** the Wii GPU draws display lists; triangle strips/fans reduce indices.
  RiiStudio tries several stripification algorithms per mesh (incl. triangle fans) and typically
  produces fewer facepoints than BrawlBox's TriStripper. Too much geometry / too many draw calls
  contributes to the **Slow Motion Bug** (lag).
- **Materials:** culling (front-only default; double-sided only when needed — it costs performance),
  pixel mode/alpha: *opaque*, *alpha test* ("stencil alpha"/"outline", binary alpha), *translucent*
  (blending). Translucent materials can suffer draw-order problems known as the **Harry Potter
  Effect**; prefer alpha test when the texture's alpha is binary.
- Material presets: RiiStudio `.rspreset` (material, shader, textures, animations) can be exported
  from one model and applied to materials with matching names; `rszst import-brres --preset-path`
  applies a folder of presets on import; `rszst dump-presets` exports all.
- ABMatt: replacing a model keeps settings for materials with matching names; commands like
  `set xlu:true for xlu.*` (transparency) and TEX0 `format:` settings.

## 3. Textures
- Common TEX0 formats: **CMPR** (4 bpp, block-compressed, 1-bit alpha) — default for most colour
  textures incl. binary alpha; **RGB5A3** (16 bpp, colour with alpha, alpha precision reduced when
  translucent); **RGBA32** (32 bpp, best quality, large); **IA8/IA4** (grayscale + alpha); **I8/I4**
  (grayscale); **RGB565** (16 bpp, no alpha); palette formats C4/C8/C14X2 (rare for tracks).
- Mipmaps reduce shimmering and moiré on tiled surfaces viewed at distance; they cost ~33 % extra
  memory. Wiimms default max mipmaps is 4 with minimal mipmap size 8 (per wszst option docs).
- Use power-of-two dimensions **(verify hard requirement vs recommendation; warn either way)**;
  keep ≤ 1024 px per side **(verify limit)**.
- Recommendation defaults in `core/textures/recommend.py` are data; the human validates them at HC2.

## 4. Collision (KCL)
- Blender-MKW-Utilities exports objects whose names end in `_F` + exactly 4 uppercase hex digits
  (e.g. `road_F0000`, `wall_F000C`); others are skipped by default (the exporter reports them).
- A KCL flag = base type (lowest 5 bits, values 0x00–0x1F per wszst's `T<type>` syntax) + variant/
  other bits. The add-on's own `labelDict` in `__init__.py` is the authoritative name table;
  `decodeFlag()` there shows the bit layout (type = low 5 bits, variant = next 3, then shadow,
  depth, trickable, drivable, soft-wall). **Verified P0-T03** against both the add-on source and
  `wkclt flags` output on the generated fixture:

  | Flag | Base type | Add-on label | `wkclt flags` description |
  |---|---|---|---|
  | `0x0000` | T00 | ROAD | Road |
  | `0x0003` | T03 | OFFROAD | Off-road |
  | `0x0006` | T06 | BOOST_PANEL | Boost Pad |
  | `0x000C` | T0C | WALL | Wall |
  | `0x0010` | T10 | FALL_BOUNDARY | Fall Boundary |

  Other base types in the add-on's table (names not yet cross-checked against wkclt):
  T01 SLIPPERY1, T02 WEAK_OFFROAD, T04 HEAVY_OFFROAD, T05 SLIPPERY2, T07 BOOST_RAMP,
  T08 JUMP_PAD, T09 ITEM_ROAD, T0A SOLID_FALL, T0B/T15/T1D MOVING_ROAD, T0D INVISIBLE_WALL,
  T0E ITEM_WALL, T0F WALL_3, T11 CANNON, T12 FORCE_RECALCULATION, T13 HALFPIPE, T14 WALL_4,
  T16 STICKY_ROAD, T17 ROAD, T18 SOUND_TRIGGER, T19 WEAK_WALL, T1A EFFECT_TRIGGER,
  T1B ITEM_STATE_MODIFIER, T1C HALFPIPE_WALL, T1E SPECIAL_WALL, T1F WALL_5.
- The add-on's "un-bean corner" default mode passes `--kcl-script=lower-walls.txt` to `wkclt`.
- **Coordinate limit:** keep drivable geometry within ±131071 on each axis, otherwise items misbehave
  (LEX `HIPT` can work around it but not all distributions support it).
  The fixture track asserts this (`tests/unit/test_fixtures.py`); at export scale 100 its ring
  reaches 36000 game units, comfortably inside the limit.
- Inspect with `wkclt analyze course.kcl` (triangles, bounds) and `wkclt flags course.kcl`.

## 5. Minimap (`map_model.brres`)
- The in-game minimap is a 3D model rendered top-down. Usually derived from the optimised collision
  model: keep main road (optionally shortcuts/objects), remove walls, fall boundaries, off-road.
- Scale must match the KCL.
- Required structure (RiiStudio route per mkwiiki): MDL0 named `map`, bone `map` with two children
  `posLD` and `posRU`; fix their positions with `wszst minimap --auto FILE` (FILE = SZS, U8, BRRES or
  MDL0). Alternatively, a KMP **Minimap Control AREA** (type 0x05) lets minimaps load without
  `posLD`/`posRU`.
- **Verified in S5 (P0-T08):** ABMatt creates `map`/`posLD`/`posRU` when the **destination
  filename** contains a lowercase `map` — not when the model or source is named `map`. rszst
  cannot create these bones at all, so the minimap is the one component that must go through
  ABMatt. `wszst minimap` on a boneless file prints no data rows and still exits 0, so the
  pipeline must check for the bones rather than trust the MDL0 name. Details in
  [SPIKES.md §S5](../dev/SPIKES.md) and TOOLS.md.
- Racing minimaps are forced grayscale; darker areas via vertex colours (recommended) or textures.

## 6. Course data (KMP)
Sections (four-letter IDs): **KTPT** start position(s) · **ENPT/ENPH** enemy (CPU) route points and
groups · **ITPT/ITPH** item route points and groups · **CKPT/CKPH** checkpoints and groups ·
**GOBJ** objects · **POTI** routes (for moving objects/cameras) · **AREA** areas (cameras, effects,
minimap control, etc.) · **CAME** cameras (opening pan, replay) · **JGPT** respawn points · **CNPT**
cannon destinations · **MSPT** end positions (battle/mission) · **STGI** stage info (lap count, pole
position, speed modifier bytes).
- A checkpoint with mode 0 is a **lap counter** (per wszst's `--ktpt2` documentation). Checkpoint
  mistakes cause lap counting problems and the **Position Jump Bug**; a missing/skippable first key
  checkpoint enables **ultra shortcuts**.
- Cannons need KCL cannon activator triggers + KMP CNPT destination.
- Editors: **Lorenzi's KMP Editor** (Electron; Windows/Linux/macOS; 3D; auto-loads `course.kcl` from
  the KMP's folder; recommended by the tutorial), **KMP Cloud** (Windows, 2D, spreadsheet-like),
  `wkmpt` text decode/encode (scriptable).

## 7. Post-effects (`posteffect/`)
Binary files for lighting and screen effects (e.g. `.blight` lighting, `.blmap` light maps/matcaps,
`.bdof` depth of field, `.bblm` bloom, `.bfg` fog **(verify exact file names per track)**). RiiStudio
can open/save these formats. Custom tracks usually copy a suitable original track's set.

## 8. Testing in an emulator
Dolphin runs the user's own copy of the game. Common ways to test a track: Riivolution patches,
extracted game folders with replaced files, or distribution frameworks (e.g. MKW-SP "My Stuff").
Phase 0 spike S8 picks the approach; the app never distributes game files.

## 9. Known failure patterns worth surfacing as hints
Missing required files · wrong slot for used objects · coordinates beyond limits · too many
facepoints/draw calls (slowdown) · translucent sorting (Harry Potter effect) · moiré (no mipmaps) ·
z-fighting (coplanar faces) · checkpoint errors (position jumps, lap count) · underground camera bug
(camera areas) · KCL glitches from thin/degenerate triangles (wkclt drops tiny/slim triangles by
default thresholds). Link each hint to its mkwiiki page.

## 10. Legal/ethical
Original game files are copyrighted. The app works with the user's own extracted files, stores them
only locally (user data dir or the user's chosen folder), never commits or uploads them, and asks
before copying anything out of them.
