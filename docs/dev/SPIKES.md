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

1. **Make `export.minimap`'s unavailability legible.** A `poll()` returning False turns
   into "context is incorrect", which sends you looking in the wrong place. Either report
   the reason via `poll_message_set()` or move the ABMatt check into `execute()`.
2. **Return counts from the operators** (objects, triangles, skipped names) instead of
   only printing them, so a bridge does not have to scrape stdout.
3. **A module-name-safe package directory** (or an `__init__.py` shim) would remove the
   copy-to-`mkw_utilities` step.

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
