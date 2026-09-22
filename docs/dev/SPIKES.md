# Phase 0 spikes

Evidence gathered before committing to a design. Each section records what was run, what
came back, and what it means for the app. Spike scripts live in `spikes/` and are never
imported by `src/` (AGENTS.md rule 3); adapters are written fresh from these notes.

---

## S1 — Wiimms assemble & check (P0-T04)

**Script:** `spikes/s1_wszst.py` (re-run: `uv run python spikes/s1_wszst.py`)
**Tool:** wszst 2.42a r8989, Linux x86_64
**Input:** the P0-T03 fixtures (`course.kcl` 16250 B, `course.kmp` 552 B). No BRRES files
exist yet, since those need S2/S3 — which turned out to be useful, because it shows
exactly how an incomplete track is reported.

### Headline: `check`'s exit code is not a pass/fail signal

This is the finding the adapter must be built around.

| Input | Exit | Prints `ERROR #`? |
|---|---|---|
| Incomplete track (no BRRES, 5 warnings) | **2** | no |
| Track with all required files present | **2** | no |
| Empty archive (no files at all) | **2** | no |
| **Corrupt/unrecognised file** | **0** | **yes** |
| Missing file on disk | 78 | yes |

`wszst error 2` is `DIFFER` and `78` is `CAN'T OPEN FILE`. So a clean track and a broken
track both exit 2, while a *corrupt* file exits **0** with `ERROR #39 [INVALID FILE
FORMAT]` on stdout. **Never treat `wszst check`'s exit code as success or failure.**
The adapter must parse the output, and must treat `ERROR #` in the text as a hard failure
regardless of the exit code. (`wszst create` does behave normally: 0 on success.)

### What `check` reports, and when

Missing components are only reported when a KMP is present — an archive containing just a
KCL reports nothing missing. Format is stable and parseable:

```
    + WARNING: Missing file:    ./course_model.brres (or '_d' variant)
    + WARNING: Missing file:    ./map_model.brres
    + WARNING: Missing file:    ./vrcorn_model.brres
 => 5 warnings, 2 hints and 1 info for YAZ0.U8:<path>
```

Severity is encoded in the line prefix: `+ WARNING:`, `- HINT:`, `* INFO:`. The `=>`
summary line gives totals and is the cheapest thing to assert on. `-B/--brief` prints
only warnings (drops hints); `-N/--no-check` skips the KCL/KMP validation entirely.

### Machine-readable output: use `analyze`, not `check`

`check --sections` and `slots --sections` are **rejected** (`ERROR #108`, exit 108).
Only `analyze` supports structured output, and it is excellent — one call replaces
`check` + `slots` + hashing for status purposes:

```json
{"file_type":"YAZ0.U8","size":16928,"sha1":"e80f…","sha1_kcl":"4177…","sha1_kmp":"13fc…",
 "sha1_course":"","sha1_vrcorn":"","sha1_minimap":"","valid_track":0,"is_arena":"0 no",
 "n_ckpt0":1,"lap_count":3,"speed_factor":1.000,"slot_info":"-4.2,-6.1,-6.2",
 "used_x_pos":"2=ok -12000.00 12000.00 24000.00 0.00","ktpt2":"ok 0.00 0.00",
 "missed_subfiles":"2b","warn":"4=no-minimap","ct_attributes":"miss=2b,warn=no-minimap",
 "valid":1,"duration_usec":387}
```

Notable fields: `valid_track` (0 here because the BRRES files are absent), `lap_count`,
`n_ckpt0` (lap-counter checkpoints — confirms the fixture's checkpoint 0), `slot_info`,
per-component SHA1s (empty string when the component is missing), and `used_[xyz]_pos`
which carries the coordinate-range check the app would otherwise implement itself.
`--sections` gives the same data as `key = value` lines. `missed_subfiles` is a compact
code (`2b`) whose encoding is not documented in `--help`; prefer the empty-SHA1 fields to
detect missing components.

### `create`

`wszst create <dir> --dest <file.szs> --overwrite` works from a plain directory and
**does not require a complete track** — it happily built an SZS from just a KCL and a
KMP, and even from a completely empty directory. Validation is `check`'s job, not
`create`'s.

Compression, measured on the fixture (uncompressed payload 16928 B):

| Flags | Bytes | Seconds |
|---|---|---|
| `--no-compress` | 16928 | 0.001 |
| `--fast` / `--compr=FAST` | 10118 | 0.002 |
| default / `--compr=BEST` | 8486 | 0.007 |
| `--compr=ULTRA` | 8247 | 0.009 |

BEST is the default and is 16 % smaller than FAST for ~3x the time. At fixture scale the
absolute times are meaningless; re-measure on a real track before choosing the test-build
default (`build.test_compression` in the manifest). ULTRA buys another 3 % and is aimed at
size-limited competitions.

Other verified flags: `-d/--dest` (accepts `%N`/`%T` escapes — `--DEST 'out/%N%T'` created
`out/minimal.szs` and the directory), `-D/--DEST` (creates directories), `-o/--overwrite`,
`-r/--remove-dest`, `--u8`, `--szs`, `--no-compress`, `-C/--compr`, `--fast`.
`--auto-add` is accepted but is a **silent no-op** without an auto-add library — no
warning, no message even with `-v`. The app must tell the user when auto-add is requested
but no library is configured, because wszst will not.

### `list` and `slots`

`wszst list <szs>` prints one path per line after a header; `list --long` adds size and a
4-character magic per file, which is a cheap way to sanity-check an archive's contents:

```
size/dec  magic file or directory
   16250  ...D  course.kcl
     552  RKMD  course.kmp
```

`wszst slots <szs>` prints one status line per source: `-4.2 -6.1 -6.2 : <path>`. The same
string appears as `slot_info` in `analyze --json`, so the adapter should prefer `analyze`
and skip `slots` entirely.

### Consequences for the design

1. **`core/tools/wiimm.py` must not use exit codes for `check`.** Parse the output; treat
   `ERROR #` as failure. This deserves a contract test with a recorded corrupt-file run.
2. **Status/validation should be built on `analyze --json`**, falling back to `check` text
   only for the human-readable issue list. One `analyze` call covers slots, lap count,
   coordinate ranges and per-component hashes.
3. **P4's validate node** can map `+ WARNING:` / `- HINT:` / `* INFO:` straight onto Issue
   severities, and the `=> N warnings, M hints` line gives a quick assertion for tests.
4. **Auto-add needs an app-side guard** (library present?) because wszst stays silent.
5. `create` never validates, so "build succeeded" must never be reported from `create`
   alone — always follow with `check`/`analyze`.

### Open questions for later

- `missed_subfiles` / `warn` / `ct_attributes` code encodings (`2b`, `4=no-minimap`) are
  undocumented in `--help`; decode them in P4 if the empty-SHA1 fields prove insufficient.
- Compression timings need re-measuring on a real track (P4 benchmark).
- Auto-add behaviour *with* a real library is untestable here: it needs the user's own
  game files (HC0 question).
- Cygwin path handling on Windows with spaces/unicode: Windows CI (P1-T07).

---

## S2 — Headless Blender exports with Blender-MKW-Utilities (P0-T05)

**Scripts:** `spikes/s2_blender.py` (driver) → `spikes/blender_export_spike.py` (runs
inside Blender). Re-run: `uv run python spikes/s2_blender.py`
**Versions:** Blender 5.2.2 LTS, add-on v1.12.0 pinned as the submodule
`vendor/blender-mkw-utilities` (commit 244ecfd).

### Result: every export works headlessly

All six run under `blender -b --factory-startup` with no GUI context. Timings are on
the P0-T03 fixture (292 collision triangles, 4 course meshes):

| Export | Operator | Seconds | Output |
|---|---|---|---|
| Collision | `kcl.export` (`kclExportUnBeanCorner=LOWER`) | 0.007 | 16250 B `.kcl` |
| Collision, no un-bean | `kcl.export` (`=NONE`) | 0.006 | 16250 B `.kcl` |
| Course model | `export.autodesk_dae` (`method=AUTO`) | 0.003 | 36485 B `.dae` + 4 PNGs |
| Course model | `export.autodesk_dae` (`method=BUILTIN`) | 0.003 | identical bytes |
| Collision as OBJ | `export_scene.objkcl` | 0.003 | 19123 B `.obj` |
| Minimap | `export.minimap` | 1.0 | 17088 B `.brres` |

Blender itself starts in ~0.9 s, which dominates: **one launch per build** (ARCHITECTURE
§7) is the right call, not one per export.

### Operator vs internal function

Calling the operators directly is enough — no `context.window` juggling, no
`bpy.ops.object.mode_set` dance. Two preconditions do apply, and both are ordinary
`poll()`/validation failures rather than context problems:

- `export.minimap` has `poll(): return _detect_abmatt()`. With ABMatt absent the call
  raises `RuntimeError: ... poll() failed, context is incorrect`, **which is misleading**:
  the fix is putting `abmatt` on `PATH`, not fixing the context.
- The minimap export refuses meshes without a material, with a clear message from the
  add-on: `ABMatt requires every exported mesh to have a material. Missing on: …`.

So the bridge should call operators, and should surface these two preconditions as
its own checks so the user gets a real explanation instead of a Blender error.

### Tool discovery under `--factory-startup`

The add-on resolves tools in the order **preference folder → `PATH` → standard install
locations** (`_resolve_tool`, `_build_tool_search_dirs`). `--factory-startup` discards
user preferences, so the first source is unavailable and the bridge must pass tools via
the environment: prepend `.tools/wiimms-szs-tools/bin` **and** `.tools/abmatt/bin` to
`PATH` before launching Blender. Detection is a real subprocess call: `_detect_abmatt()`
runs `abmatt` and requires the output to start with `USAGE: abmatt`.
The add-on also handles Flatpak/Snap (`flatpak-spawn --host`), which does not apply here
but will on the human's Flatpak Blender.

### Findings worth designing around

1. **`kclExportUnBeanCorner` genuinely changes the output.** LOWER and NONE produce the
   same byte *count* but different content (verified by hash), so the option is live and
   worth exposing; do not compare sizes to detect a change.
2. **`method=AUTO` equals `BUILTIN` on Linux.** AUTO prefers a bundled
   `bin/FbxConverter.exe`, a Windows binary that is absent here, so it silently falls back
   to the add-on's own COLLADA writer. Expect Windows CI to produce *different* DAE bytes
   via the FBX route — do not write tests that assume byte-identical DAEs across OSes.
3. **The DAE export copies its textures next to the file** (`road.png`, `grass.png`,
   `fence.png`, `water.png`) with `daeExportCopyTextures=True`, which is what the BRRES
   importers expect in S3.
4. **The minimap BRRES is correct out of the box.** `wszst list` shows a single MDL0
   named `map`, and `wszst minimap` finds `posLD`/`posRU` and prints recommended
   translations — the whole minimap path in MKW_DOMAIN §5 works headlessly today.
5. **Stdout markers are stable and worth parsing** (already recorded in TOOLS.md):
   `[MKW Utilities] KCL export: N object(s), M triangle(s)`, the `KCL extent` line, and
   `SKIPPED (no valid KCL flag in name): …`.

### Fixture change this forced

The P0-T03 KCL meshes had no materials, so the minimap export failed. `build_kcl` now
gives every collision mesh a material. Collision has no visual appearance, so this is
purely to satisfy ABMatt; the test `test_minimap_export_produces_a_brres` keeps it honest.

### Recommended bridge approach (P6)

- Launch once: `blender -b <blend> --factory-startup --python run_job.py -- <job.json>`,
  with `PATH` extended to the tools, as `spikes/s2_blender.py` does.
- Register the add-on from the submodule by putting its **parent** on `sys.path` and
  importing it by directory name. Note the checkout is `blender-mkw-utilities`, which is
  **not a valid Python module name**: the spike copies it to `mkw_utilities` first. P6
  should either keep that staging step or vendor it under an importable name.
- Call the operators (not internals) and parse the `[MKW Utilities]` markers.
- Check ABMatt and materials up front so minimap failures are explained properly.

### Add-on changes that would help (for the human to decide)

None are required — everything needed works today. In rough order of value:

1. ~~**Make `export.minimap`'s unavailability legible.**~~ **Done** (add-on PR #1,
   merged as `ffa905f`): `poll()` now sets a `poll_message_set()` naming ABMatt, and
   the callable path returns the same reason instead of "context is incorrect".
2. ~~**Return counts from the operators**~~ **Done** (same PR): the add-on exposes
   `export_kcl`, `export_collada` and `export_minimap_brres`, each returning a result
   dictionary with `ok`, `filepath`, `objects`, `triangles`, `skipped_objects` and
   `error`. The bridge (P6) calls these directly and never scrapes stdout.
3. **A module-name-safe package directory** (or an `__init__.py` shim) would remove the
   copy-to-`mkw_utilities` step. **Declined** by the human; the bridge keeps the copy.

The refactor also fixed five defects the extraction exposed: a shell-injection path via
`os.popen` in KCL encoding (now argv + exit-code check + timeout), ABMatt exit codes
being ignored so a failed conversion republished a stale BRRES, active-collection
minimap exports skipping child collections, selection-only KCL counting non-mesh
objects, and the three `blender -b` scripts exiting 0 on failure.

### Open questions

- Windows: the FBX/FbxConverter DAE route is untested here (Windows CI, P1-T07).
- Flatpak Blender on the human's host uses `flatpak-spawn --host`; the bridge's `PATH`
  injection needs re-checking there (HC1/HC2).

---

## S3: BRRES backend bake-off (P0-T06a / P0-T06b)

### S3a: Linux CLI build and discovery (P0-T06a)

RiiStudio **Alpha 5.11.5**, source commit
`09e5754d56562219c87390c8d64ef31110725ccd`, builds a working Linux CLI without
source patches. This proves startup and command discovery, **not BRRES conversion**.
The course/skybox comparison, material controls and ADR-004 decision remain P0-T06b.

Prerequisites tested: Debian 13, CMake 3.31.6, Clang 19.1.7 with GCC 14's libstdc++,
Cargo/Rust 1.85.1, Assimp 5.4.3. Install build-only packages:

```sh
apt-get update
apt-get install -y build-essential cmake clang cargo rustc pkg-config \
  mesa-common-dev libglfw3-dev libassimp-dev libfreetype-dev libbz2-dev libssl-dev
```

From the repository root, with fresh destination directories:

```sh
git clone --branch Alpha-5.11.5 --depth 1 https://github.com/snailspeed3/RiiStudio.git .tools/riistudio-source
git -C .tools/riistudio-source checkout --detach 09e5754d56562219c87390c8d64ef31110725ccd
git clone --branch v0.4.10 --depth 1 https://github.com/corrosion-rs/corrosion.git .tools/corrosion-0.4.10
git -C .tools/corrosion-0.4.10 checkout --detach 9943de73df25ddb06bf6105baeca002ae54e45f3
cmake -S .tools/riistudio-source -B .tools/riistudio-build-pinned \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  '-DCMAKE_CXX_FLAGS=-include memory' -DCMAKE_CXX_STANDARD_LIBRARIES=-lstdc++exp \
  -DCPM_corrosion_SOURCE="$PWD/.tools/corrosion-0.4.10"
CXXFLAGS='-include memory' cmake --build .tools/riistudio-build-pinned --target cli --parallel 4
python spikes/s3_rszst_probe.py --output spikes/out/s3a/linux-cli.json
```

The probe refuses to overwrite a recording. Use a fresh output path on subsequent runs.
The source checkout, dependencies and executable stay under ignored `.tools/`; do not
copy upstream sample assets into CT Studio fixtures. CMake downloads CPM 0.36.0; Cargo
uses the upstream lockfiles. This is a verified development recipe, not an offline or
bit-reproducible distribution build. The dynamically linked executable needs Assimp,
GLFW, FreeType, OpenSSL and their system dependencies even for CLI use.

| Attempt | Result | Evidence / correction |
|---|---|---|
| Initial upstream HEAD `c5a7cd8` + current Corrosion master | build exit 2 | Missing `std::unique_ptr` declaration in bundled BRRES code; switched to released source. |
| Alpha 5.11.5, ordinary CMake configuration | configure 0, build 2 | `source/oishii/reader/binary_reader.hxx:166` uses `std::unique_ptr` without `<memory>`. |
| Explicit `<memory>` with Corrosion master `c4786e7` | build 2 | Cargo 1.85.1 panics in fingerprinting after duplicate static-library output warnings. |
| Corrosion v0.4.10, explicit `<memory>` | compilation reaches final link | Undefined `std::__stacktrace_impl::_S_current` / `_Info::_M_populate`; GCC 14 needs `libstdc++exp`. |
| Above plus `-DCMAKE_CXX_STANDARD_LIBRARIES=-lstdc++exp` | configure 0, build 0 | `source/cli/rszst` launches; source checkout remains clean. |

The main compile took approximately nine minutes with four build jobs; linking was
then retried successfully. Local diagnostic logs: `.tools/release-build*.log`.
No conversion timing is claimed here.

Licence: **overall grant unconfirmed; mixed component licences**. The pinned tree
has no root LICENSE/COPYING and its README has credits but no blanket grant.
`source/gctex/Cargo.toml:3` declares GPL-2.0-or-later; several other Rust components
have MIT declarations. Those do not establish a licence for the whole CLI.
Do not bundle or redistribute this build until the overall grant and linked-component
obligations have been reviewed. This does not block the local S3b comparison.

Nine real query outputs, argv and exit codes are committed in
[linux-cli.json](../../tests/fakes/recordings/rszst/5.11.5/linux-cli.json).
They cover version, top-level help, five subcommand help queries, an unknown command
and missing import arguments. All exit **255** and write to **stdout**, not stderr.
`--version` prints both `rszst_arg_parser 0.1.6` and `RiiStudio CLI Alpha 5.11.5`;
the parser version alone is not the application version. The banner follows help text.
Do not treat 255 as general success: conversion exit codes remain unmeasured.

The help verifies `--model-name`, `--mipmaps`, `--min-mip`, `--max-mip`,
`--auto-transparency`, `--preset-path` and **`--cull-degenerates` (plural)**.
Their effects require fixture runs in S3b. JSON help contains misleading descriptions
(`brres-to-json` calls its input `.kmp`; `json-to-brres` reverses its summary).
Test actual round-trips rather than relying on those descriptions.

Verification: `tests/integration/test_rszst_cli.py` runs all nine queries with display
variables removed, from a directory containing spaces and non-ASCII text, comparing
exit codes and output to the recordings while excluding the variable build banner.
An initial assertion that help exits 0 failed twice against the live CLI.

Windows remains untested. Upstream Alpha-5.11.5 publishes `RiiStudio_Windows.zip`
and a macOS DMG, not a Linux release asset. P2-T08 (integration CI after P1-T07)
must pin the Windows ZIP checksum,
keep its bundled DLLs with `rszst.exe`, record its help/exit codes independently and
repeat S3b's synthetic fixture tests. Do not impose Linux's 255 status on Windows.

### S3b: fixture bake-off and backend decision (P0-T06b)

**Script:** `uv run python spikes/s3_backend_bakeoff.py` → `spikes/out/s3b/s3b_findings.json`.
Both backends import the same S2 fixture DAE (`course_builtin.dae` + its four PNGs).
Tests: `tests/integration/test_brres_backends.py` (14 tests, 4/4 mutations caught).

| | rszst (Alpha 5.11.5) | ABMatt 1.3.2 |
|---|---|---|
| Import exit / size | 0 · 25728 B | 0 · 25440 B |
| Median import time | **0.013 s** | 0.293 s (~22x slower) |
| MDL0 name | `--model-name course\|vrcorn\|map` | **from the source filename stem** |
| Textures | 4/4, CMPR | 4/4, CMPR |
| Default mipmaps (road) | 1 | **3** |
| Reads the other's BRRES | **no** | yes |
| Material editing | `--preset-path` / `dump-presets` only | full command language |
| JSON round-trip | `brres-to-json` → `json-to-brres`, both exit 0 | n/a |
| `wszst create` + `check` | clean (2 known fixture camera warnings) | clean (same 2) |

**The decisive finding: the interop wall is one-way.** ABMatt opens an rszst BRRES and
reports its materials fine, but rszst **cannot read an ABMatt BRRES** at all:

```
Failed to read MDL0 course: Invalid quantization for normal data: U16   (exit 255)
```

So the order matters: **rszst imports, ABMatt post-processes**. The reverse pipeline is
impossible with these versions, not merely slower. Note this also means `brres-to-json`
is only available for models rszst itself produced.

**Traps that cost real time here:**

1. **ABMatt has no model-name flag.** The MDL0 name comes from the *source file stem* up
   to the first `_` (`vrcorn_xyz.dae` → `vrcorn`, `zzz.dae` → `zzz`, `coursey.dae` →
   `course`). It then *validates* that against a `<slot>_model.brres` destination:
   `course_builtin.dae` → `map_model.brres` fails with `Model name does not match file`
   and writes nothing. An adapter must stage the DAE under the right name, not just pick
   an output path. `-o` does not override this.
2. **`abmatt -c "set material xlu:true for *"` is broken.** The argument gets mangled into
   `'set material xlu:true for *  for *'` and the run dies with a parse error. A command
   **file** (`-f cmds.txt`) with the same text works and the change verifiably lands
   (`xlu:0` → `xlu:1`). The Blender add-on uses the same file-based route.
3. **`set tex0 format:IA8` is a silent no-op.** It exits 0, prints `Wrote file`, and the
   stored format is still CMPR (confirmed by both `wimgt list` and ABMatt's own `info`).
   Per-texture format control therefore is *not* available through this path — texture
   formats must be decided at import time or via `wimgt`.
4. **rszst's `--mipmaps` alone does nothing** on 64x64 textures, because `--min-mip`
   defaults to 32. `--mipmaps --min-mip 8` gives 3 mip levels. Passing `--mipmaps` and
   assuming mipmaps exist would be wrong.
5. **Material selectors use material names, not object names** (`for water`, not
   `for course_water`); a wrong selector fails loudly with `No items found in selection!`.
6. Unlike the help output recorded in S3a, rszst's **conversion commands do use exit
   codes meaningfully**: 0 on success, 255 on a real failure (verified with garbage input).

**Recommendation for ADR-004 (both platforms the same):** `rszst` is the import backend
and ABMatt is the material/minimap post-processor. This is driven by the one-way read
wall and the 22x speed difference, not by preference. Because Linux rszst must be built
from source (S3a) and its licence is unresolved, the `BrresBackend` interface must keep
ABMatt viable as a standalone fallback: it converts, packs and validates perfectly well
on its own, it just cannot hand its output to rszst.

**Interface confirmed by this spike** — `import_model(dae, out, *, model_name, mipmaps)`,
`inspect(brres)`, `apply_materials(brres, commands)`, `capture_presets(brres, dir)`.
`set_texture_formats` must **not** be part of the ABMatt implementation (trap 3); it
belongs to import options or a `wimgt` path.

**Open questions for S4/P5:** whether presets survive a BrawlCrate-edited file; whether
the JSON schema is stable across rszst releases; Windows behaviour of both backends.

---

## S4 — Preserving external material edits (P0-T07)
**Script:** `spikes/s4_material_edits.py` → `spikes/out/s4/s4_findings.json`.
Re-run: `uv run python spikes/s4_material_edits.py`
**Versions:** RiiStudio CLI Alpha 5.11.5 (`09e5754`), ABMatt 1.3.2, fixture
`spikes/out/s2/course_builtin.dae` (4 materials: fence, grass, road, water).
**Tests:** `tests/integration/test_material_preservation.py` — 10 tests, 5/5 mutations caught.

### The premise, confirmed
A regenerate throws the user's work away. Editing `water` to
`xlu:1 blend:1 cullmode:none` and re-importing the DAE returns it to
`xlu:0 blend:0 cullmode:inside`. Something must capture and reapply.

### All three routes restore the edit
| Route | Mechanism | Restores edit | SRT0 survives | Textures | Speed |
|---|---|---|---|---|---|
| **A** | `dump-presets` → `import-brres --preset-path` | yes | **yes** | 4, no dupes | 0.006 s dump + 0.013 s import |
| **B** | ABMatt `copy`/`paste material` between two BRRES | yes | **yes** | 4, no dupes | 0.198 s |
| **C** | `brres-to-json` → merge in Python → `json-to-brres` | yes | only if `srts` copied too | 4, no dupes | 0.005 s + 0.005 s |

No route duplicated a texture. Route A is ~15x faster than B and needs no
second tool; A and C are within noise of each other.

### What separates them
1. **Route B has a destructive failure mode.** Paste to a name that no longer
   exists and ABMatt's autofix removes the now-unused texture: pasting `water`
   onto a regenerate whose material was renamed `waterB` leaves the material
   holding the edit but **deletes the `waterB` texture**, exit code 0. The
   `-a`/`--auto-fix` flag that would disable this is **broken in 1.3.2** —
   `-a 0` parses `0` as a command and aborts, `-a0` and `--auto-fix=0` are both
   rejected. There is no way to turn the autofix off from the CLI.
2. **Route A fails safe on the same input.** An unmatched preset is skipped
   silently: the renamed material comes back pristine, nothing is deleted,
   exit 0. Silent, but non-destructive.
3. **Presets are matched by material name** — the same coupling S3b found for
   MDL0 naming. Renaming a material in Blender orphans its captured edits under
   every route; the app must detect this and tell the user, because no tool will.
4. **Route C's JSON is not self-contained.** `brres-to-json` writes a `<stem>.bin`
   sidecar (magic `RBUF`) holding geometry. `json-to-brres` reads it from beside
   the `.json`; without it the write fails with exit **255** and produces no file.
   Loudly, at least. Any capture format based on this must keep both files.
5. **Animations live outside the material list.** SRT0 is authorable headlessly
   (`add srt0 for water`). Routes A and B carry it automatically. A material-only
   JSON merge **silently drops it** — `srts` must be copied as a separate step.

### Recommendation for ADR-012
**Route A (rszst presets) as the capture/reapply mechanism**, with route C
(JSON merge) as the inspection and diffing format. Route A is the fastest, needs
one tool, carries animations for free, and its failure mode is a no-op rather
than data loss. Route B is rejected as the primary mechanism specifically because
its autofix can delete textures and cannot be disabled in 1.3.2.

Capture = `dump-presets` into `overrides/captured/<component>/`; reapply =
`--preset-path` on the next import. Because an unmatched preset is silent, the
app must diff captured preset names against the regenerated material list and
warn on any orphan — that check is ours to write, not the tool's.

### Must be re-verified at HC2 with a real BrawlCrate-edited file
- Whether `dump-presets` captures **everything** BrawlCrate can change. This spike
  exercised xlu, blend mode, cull mode and one SRT0 on a 4-material synthetic
  model. TEV stages, indirect textures, PAT0/CLR0 animations, multi-layer
  materials and LightSet/FogSet indices are **unverified**.
- Whether a BrawlCrate-saved BRRES re-imports into rszst at all (S3b already found
  rszst rejects ABMatt output: `Invalid quantization for normal data: U16`). If
  BrawlCrate output hits the same wall, capture must happen before the edit, not
  after — a significant change to the §8 reconciliation flow.
- Whether `.rspreset` files are stable across rszst releases (they are opaque
  binary; no schema is published).
- Real-world material counts and timings; 4 materials is not a track.

---

## S5 — Headless minimap (P0-T08)
**Script:** `spikes/s5_minimap.py` → `spikes/out/s5/s5_findings.json`.
Re-run: `uv run python spikes/s5_minimap.py`
**Versions:** Wiimms SZS Tools 2.42a, ABMatt 1.3.2, RiiStudio CLI Alpha 5.11.5.
**Tests:** `tests/integration/test_minimap_paths.py` — 8 tests, 5/5 mutations caught.

### The three paths
| Path | Route | MDL0 `map` | `posLD`/`posRU` | Usable minimap | Speed |
|---|---|---|---|---|---|
| **1** | `course.kcl` → filtered OBJ → ABMatt | yes | **yes** | **yes** | 0.003 s decode + 0.277 s convert |
| **2** | Blender DAE → `rszst --model-name map` | yes | **no** | **no** | 0.011 s |
| **3** | add-on `export_minimap_brres` (S2) | yes | **yes** | **yes** | one Blender launch |

Paths 1 and 3 both work; path 2 does not, and fails in a way that looks like success.

### The trap that decides this
**`wszst list` showing `3DModels(NW4R)/map` does not mean you have a minimap.**
The game needs the `posLD`/`posRU` bones, and ABMatt creates them based on the
**destination filename**, not the model name:

| source → destination | MDL0 name | position bones |
|---|---|---|
| `drivable.obj` → `map_model.brres` | `map` | **yes** |
| `drivable.obj` → `mymap.brres` | `map` | **yes** |
| `mapsource.obj` → `plain.brres` | `map` | **no** |
| `drivable.obj` → `MAP.brres` | `drivable` | no |
| `drivable.obj` → `vrcorn_model.brres` | `vrcorn` | no |

So a *source* file called `map*.obj` renames the MDL0 and produces **no bones** —
a file that passes a name check and is silently useless in game. The match is
lowercase-only (`MAP.brres` does not count) and is a substring test, not a prefix:
`roadmapping.brres`, `premap.brres` and `xmapx.brres` all trigger it.
`wszst minimap` on a boneless file prints a header and **no data rows**, exit 0 —
absence of output is the only signal.

### Other findings
1. **rszst cannot make minimap bones at all.** `--model-name map` names the MDL0
   and nothing else; the single bone is `$MergedNode_0`. `wszst minimap --auto`
   then has nothing to patch and exits 0 having done nothing. This is the one
   component where **ADR-004's "rszst imports" default does not apply** — the
   minimap must go through ABMatt.
2. **`wszst minimap --auto` works and is worth running.** On the path-1 fixture it
   tightened the translations from the model's bounding box (`±20600`) to the
   recommended values (`±15284`), rewriting flags `0x11c` → `0x31f`.
3. **KCL type filtering works via `--kcl-script`.** `wkclt decode --kcl-script`
   with `tri$remove()` over the wall/boundary types dropped 98 of 292 triangles,
   leaving the 194 drivable ones. This is how path 1 gets a minimap outline that
   is the track surface rather than its surrounding walls. The script language is
   Wiimms' own (`@for`, `@function`, `tri$*()`); `lower-walls.txt` in the add-on is
   the reference example.
4. **ABMatt crashes converting a DAE to a mismatched `*_model.brres`** with
   `AttributeError: 'Brres' object has no attribute 'srt0'`, exit 1, on top of the
   expected `Model name does not match file`. Stage the source under the intended
   stem first (`map.dae` → `map_from_dae.brres` works and produces bones).
5. **The add-on's export (path 3) is the same ABMatt route** with Blender doing the
   mesh selection, which is why it also produces correct bones.

### Recommendation for P9
**Offer both working paths, defaulting to path 1 (KCL-derived).** It needs no
Blender launch, follows the MKW convention of deriving the minimap from collision
(MKW_DOMAIN §5), and the KCL is already built by then. Path 3 stays available for
users who model a dedicated minimap collection in Blender. Path 2 is dead — record
it so nobody retries `--model-name map` expecting it to work.

Whichever path runs, the pipeline must **verify `posLD`/`posRU` exist** after
conversion rather than trusting the MDL0 name, and then run `wszst minimap --auto`.

### Not verified here
- Whether the minimap *looks* right: the fixture is a synthetic 194-triangle plane,
  so orientation, grayscale and vertex-colour shading are untested. HC3.
- The KMP **Minimap Control AREA** (type 0x05) alternative to `posLD`/`posRU`
  (MKW_DOMAIN §5) — not exercised; still the documented fallback.
- Real track scale: 292 triangles is not a track, and ABMatt's 0.277 s will grow.

---

## S6 — Preview rendering stack (P0-T09)
**Script:** `spikes/s6_preview.py` → `spikes/out/s6/s6_findings.json` +
`spikes/out/s6/s6_standalone_200k.png`.
Re-run: `uv run --with moderngl --with numpy --with pillow --with PySide6 --no-project
python spikes/s6_preview.py`
**Versions:** Mesa 25.0.7 (llvmpipe, LLVM 19.1.7), moderngl 5.12.0, PySide6 6.x,
numpy 2.5.3, Pillow 12.3.0.
**Tests:** `tests/integration/test_preview_stack.py` — 6 tests, 4/4 mutations caught.

### ADR-008 confirmed: moderngl + QOpenGLWidget works
| Check | Result |
|---|---|
| Headless GL version | **4.5 core** (Mesa/llvmpipe) — exceeds the 3.3 core target |
| Standalone EGL context | created in **0.026 s** |
| 200k triangles, one interleaved VBO | **13.7 MB**, uploaded in **0.006–0.035 s** |
| Offscreen render of 200k triangles | **719 263 of 921 600 pixels** drawn (1280×720) |
| Qt `QOpenGLWidget` + moderngl sharing a context | **works under Xvfb** |

The screenshot is a genuine dense triangle soup, confirmed by eye, not a cleared
buffer — the check counts pixels differing from the clear colour, because
"non-black" would pass trivially against a non-black clear colour.

### The finding that changes how P9 is tested
**`QT_QPA_PLATFORM=offscreen` cannot create a GL context at all:**
`QOpenGLWidget is not supported on this platform.` / `Failed to create context`.
Under `xvfb-run` with `QT_QPA_PLATFORM=xcb` the same code gets GL 4.5 core and a
valid framebuffer, in ~0.2 s.

This contradicts the standing convention (AGENTS.md, TESTING_STRATEGY §1) that GUI
tests run with `QT_QPA_PLATFORM=offscreen`. That convention still holds for ordinary
widget tests; **preview/viewport tests are the exception and need `xvfb-run` + `xcb`.**
P9-T01 and the GUI test harness must account for this, and it is also exactly the
condition P9-T01's "graceful fallback panel" exists to handle — a user on a machine
without a usable GL context hits the same failure.

`libGL.so` (the dev symlink, from `libgl-dev`) is required in addition to
`libGL.so.1`: moderngl loads it by that name, so a container with only the runtime
package gets `OSError: libGL.so: cannot open shared object file` *after* Qt has
successfully created the context.

### Performance: what these numbers do and do not mean
Median frame at 200k triangles: **0.10 s ≈ 10 fps**, 1280×720, on **llvmpipe**.

That is a software rasteriser with no GPU in this container. It is a **floor, not a
measurement of the budget**: ARCHITECTURE §15 asks for ≥60 fps at 200k triangles on an
*integrated GPU*, which cannot be confirmed or refuted here. What the number does show
is that the CPU-side pipeline (numpy → single VBO → one `vao.render()`) is not the
bottleneck: upload is ~0.03 s and the remaining cost is fragment shading, which is
precisely the part hardware does thousands of times faster.

**Do not treat 10 fps as a failure of ADR-008, and do not treat it as passing §15.**
The budget must be re-measured on the human's RTX 4070 host at HC3 (P9 exit).

### Not verified here
- Real GPU frame times, hence the §15 preview budget (HC3).
- Windows GL behaviour and the Qt/ANGLE path.
- `QOpenGLWidget` resize/reallocation behaviour and multi-widget context sharing,
  which P9-T01 needs but which a single 64×64 probe cannot exercise.

---

## S7 — External editor launch contracts (P0-T10)
**Script:** `spikes/s7_editor_launch.py` → `spikes/out/s7/s7_findings.json` + screenshots.
Re-run: `uv run --with numpy --with pillow python spikes/s7_editor_launch.py`
**Tests:** `tests/integration/test_editor_launch.py` — 9 tests, 6/6 mutations caught.
**Versions:** BrawlCrate v0.42h1 (x86, net472), RiiStudio Alpha 5.11.5 (Windows x86-64),
Lorenzi's KMP Editor v0.7.7 (built from source, `34b7016`), KMP Cloud v1.2.0.1 (2012,
.NET 4.0), Blender 5.2.2 LTS, Dolphin (source `2603a`, read only).
All GUI probes ran on a private Xvfb display with software GL; the Windows tools ran
under Wine 10.0 prefixes built outside the repo.

### Every editor takes one file path, and none of them is single-instance
| Tool | Launch | File arg opens it? | Evidence | Second launch |
|---|---|---|---|---|
| BrawlCrate 0.42h1 | `wine BrawlCrate.exe <win path> [/audio:none]` | **yes** | window title *is* the path | **new window** |
| RiiStudio 5.11.5 | `wine RiiStudio.exe <win path>` | **yes** | `File: <path>` on stdout **(tty only)** | new window |
| Lorenzi 0.7.7 | `<exe> <path>` | **yes** | title `[<path>] -- Lorenzi's KMP Editor` | new window |
| KMP Cloud 1.2.0.1 | `wine "KMP Cloud.exe" <win path>` | **yes** | file name in its tree pane only | new window |
| Blender 5.2.2 | `blender <file.blend>` | **yes** | `bpy.data.filepath` | new process |

So "Open in…" must assume a **new process per launch** and must never pass two documents
in one invocation. Each tool reads exactly one path, and the extra arguments mean
something else entirely:
- **BrawlCrate's second argument is a node path inside the first file**
  (`ResourceNode.FindNode`), not a second document — passing two files pops
  `Error: Unable to find node or path '<file2>'`.
- **Blender's second positional replaces the first** in the same process.
- **RiiStudio reads only `argv[1]`**; `--update` is the one reserved value.
- **Lorenzi reads only `process.argv[1]`**, with no flag parsing at all.

### The three traps worth designing around
1. **Options must come *after* the path for Lorenzi's editor.** It opens `argv[1]`
   whatever it is, so `editor --no-sandbox track.kmp` opens `--no-sandbox`, fails
   silently and shows `[New File]`. Verified both ways.
2. **A live process is not a loaded file.** RiiStudio opened ABMatt's BRRES, failed with
   `Failed to read MDL0 course: Invalid quantization for normal data: U16` — the same wall
   S3b hit on the CLI side — and **kept running with an empty editor**. The GUI shows no
   dialog. So the adapter cannot report success from a healthy process; for BRRES this is
   another reason ADR-004 stages through rszst.
3. **Two of the five never name the file in the window title.** RiiStudio's title is the
   version banner and KMP Cloud's is `VulcSoft KMP Cloud`; KMP Cloud only shows the name
   in its tree pane (confirmed by screenshot diff, 0.13 % of pixels). Any "did it open?"
   check in the GUI must not be title-based.

### Wine, measured
| Fact | Value |
|---|---|
| BrawlCrate prefix | **win32 + `winetricks dotnet48`** (Wine Mono is not enough: `CLRRuntimeInfo_GetRuntimeHost Wine Mono is not installed`, exit 255) |
| BrawlCrate Windows version | **win10** — under the default `win7` it starts but the API is disabled by design (v0.42h1 release note) |
| KMP Cloud prefix | the same win32 + dotnet48 prefix; it targets .NET 4.0 |
| RiiStudio prefix | **win64** (`PE32+ x86-64`): in a win32 prefix Wine refuses with `ShellExecuteEx failed: Bad EXE format` |
| Path conversion | `winepath -w` works and is what the adapter should use — **but BrawlCrate also opened a raw POSIX path**, because Wine maps `/` onto `Z:`. Convert anyway; do not rely on the accident |
| Paths with spaces | fine everywhere, as one argv element |

`dotnet48` installs unattended under Xvfb and takes ~5 minutes; the prefix must be built
before any of this works. Exact commands are in
[ENVIRONMENT.md](ENVIRONMENT.md#wine-prefixes-for-the-windows-only-editors-s7-p0-t10).

### Lorenzi's editor: `course.kcl` auto-load confirmed
With a `course.kcl` beside the KMP the viewport draws the coloured collision mesh; without
it the editor silently falls back to a default box. **58 % of the screen differs** between
the two runs (`spikes/out/s7/lorenzi-path.png` vs `lorenzi-nokcl.png`). The filename is a
hard-coded lowercase `course.kcl` in the KMP's own directory
(`src/mainWindow.js` `openKmp`), which matters on Linux. CT Studio should therefore make
sure the KCL is next to the KMP before offering "Edit KMP", or the user silently edits
against a featureless box.

### Linux packaging reality
Lorenzi's editor publishes **no Linux binary** (checked every release back to v0.7.0:
Windows `.exe` + macOS arm64 only), confirming the P0-T02 correction. Two routes work:
the Windows `.exe` under Wine — note its installer unpacks an **x86-64** Electron app, so
it needs the win64 prefix, not the win32 one — or an Electron build from source
(`npm install && npx electron-builder --linux dir`), which is what the probes used because
it needs no prefix. The built app needs `libnss3` and either `--no-sandbox` **after** the
path or `ELECTRON_DISABLE_SANDBOX=1` (preferred, since the flag position is a trap).

### Dolphin (source only, `2603a`)
Confirmed from `Source/Core/UICommon/CommandLineParse.cpp` and `DolphinQt/Main.cpp`:
`-e/--exec` is repeatable and takes precedence; a bare positional is only used when
`--exec` is absent, and only the first one is read. `-u/--user` overrides the user
directory per invocation. `-b/--batch` hides the UI and requires a game. There is no
single-instance path: every launch builds its own `QApplication`. Prefer
`--exec=<absolute path>` and treat P0-T11 as the place where boot/lifecycle is settled.

### Not verified here
- **Native Windows behaviour** for all four Windows tools, including whether an
  association/`ShellExecute` launch differs from a direct argv launch (P2-T08).
- **Non-ASCII paths** — only spaces were exercised; RiiStudio's narrow `std::string`
  path handling makes it the likely failure.
- **Save behaviour** (in place? atomic? backups?), which P5-T06's change-detection needs.
- BrawlCrate's second argument as a node selector, and whether its OpenGL model preview
  works under Wine at all (llvmpipe here; the add-on README reports
  `glActiveTexture` failures in VMs).
- macOS entirely.

---

## S8 — Getting a built SZS into a running game (P0-T11)
**Question:** P11-T02 promises "Build & launch". Which route from a built `<slot>.szs`
to racing it can CT Studio actually start without the user clicking through Dolphin's
GUI, and what does each cost?

**Script:** `spikes/s8_dolphin_launch.py` · **Output:** `spikes/out/s8/s8_findings.json`
**Mutation check:** `spikes/s8_mutation_check.sh` · **Tests:** `tests/integration/test_dolphin_launch.py`
**Re-run:** `uv run python spikes/s8_dolphin_launch.py` (needs `dolphin-emu` on PATH;
on Debian the binaries live in `/usr/games`).

**Fixture:** no Mario Kart Wii data exists here and none may be obtained, so every probe
runs against a synthetic disc-shaped directory built by the spike: a `sys/boot.bin`
header carrying only the *shape* of a game id, a stub `sys/main.dol`, and a fake
`Race/Course/beginner_course.szs`. That exercises Dolphin's boot-path selection,
descriptor parsing and exit codes. It cannot show a patched file reaching the game.

**Version:** `Dolphin [master] 2503` (Debian `dolphin-emu 2503+dfsg-1+deb13u1`);
source read at tag `2603a` = `5e7cc91d8c9a43ca189b288937f65c9763af9c22`.

### Route 1 — extracted game folder
Works, and is the cheap one. `--exec=<game>/sys/main.dol` boots as a disc
(`DiscIO/DirectoryBlob.cpp` `IsValidDirectoryBlob`: `sys/boot.bin` must sit beside the
DOL and be at least 0x20 bytes). Paths with spaces are fine. Installing a build is a
plain file copy over `files/Race/Course/<slot>.szs` — no packing, no repack of the ISO.
`dolphin-tool extract -i <game>/sys/main.dol -l` lists the same tree, which gives a
pre-launch check that boots nothing.

**Trap:** `--exec=<game folder>` is rejected (`Could not recognize file`, exit 1). The
app must append `sys/main.dol` itself.

### Route 2 — Dolphin's game-mod descriptor (Riivolution)
Also works, leaves the user's game untouched, and needs no GUI. CT Studio writes a JSON
(`DiscIO/GameModDescriptor.cpp`): `{"type": "dolphin-game-mod-descriptor", "version": 1,
"base-file": ..., "riivolution": {"patches": [{"xml": ..., "root": ..., "options": [...]}]}}`
and passes it to `--exec`. Both `type` and `version` are enforced: get either wrong and
the whole file is rejected with `Could not recognize file`, exit 1. A relative `base-file`
resolves against the descriptor's own directory.

**The finding that matters:** a *broken* patch is invisible. A descriptor whose XML is
missing, malformed, or scoped to a different game id still boots, exit 0, with zero log
output at max verbosity across BOOT/DISCIO/OSHLE/FILEMON — `RiivolutionParser.cpp:352-354`
does `if (!parsed || !parsed->IsValidForGame(...)) continue;`. The only Riivolution log
lines in the codebase are memory-patch/HLE overlap warnings. So:
- CT Studio must validate the XML it generates itself, before launching.
- "Dolphin launched" must never be presented as "your track is in the game".

### Route 3 — MKW-SP "My Stuff"
Not probed: it needs the MKW-SP distribution, not plain Mario Kart Wii, so it cannot be
characterized without the user's own setup. Documented as a manual path, not automation.

### Exit codes and the GUI trap
`dolphin-emu-nogui --exec=<missing>` exits **1** and prints `The specified file "..." does
not exist` / `Could not boot the specified file`. `dolphin-emu --batch --exec=<missing>`
does **not**: `--batch` hides the UI but not the panic dialog, so the GUI binary sits on a
modal `Warning` box forever (probe timed out; screenshot confirmed the dialog).
A successful boot never exits on its own — emulation runs until killed.

**Consequence for P11:** drive `dolphin-emu-nogui` when CT Studio needs to *know* the
result, and when launching the GUI for the user, either pass
`-C Main.Interface.UsePanicHandlers=False` or accept that failures are silent.
`-u <dir>` isolates the user directory and creates it on demand, including
`Load/Riivolution`; the nogui binary creates fewer subdirectories than the GUI (no
`Config` until something writes one), so do not probe for `Config` to validate a user dir.

### Not verified here
- That a patched slot file actually loads in-game — needs the real game (HC3).
- MKW-SP "My Stuff" entirely.
- Native Windows and macOS Dolphin builds.
- Save-state and movie options (`--save_state`, `--movie`), which a future regression
  harness might want.
