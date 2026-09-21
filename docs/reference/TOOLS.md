# External tool catalogue

Rules: every flag or output format an adapter relies on must appear here with the **tool version**
it was verified on and **how** (help text, doc URL, or real run). Pre-filled facts below came from
desk research on 2026-09-17 and are marked **[doc]** (from official docs/release notes) or **[unverified]**.
Upgrade them to **[verified vX, run]** during Phase 0/2.

---

## Wiimms SZS Tools (wszst, wkclt, wkmpt, wimgt, …)
- Site: https://szs.wiimm.de/ · Source: https://github.com/Wiimm/wiimms-szs-tools · Licence: GPL **[unverified: confirm]**
- Stable: **v2.42a (2024-03-26)** — builds for Linux x86_64/i386, Cygwin 64/32 (Windows), macOS x86_64 **[doc]**
- Syntax: `wszst [option]... command [option|parameter|@file]...` **[doc]**
- Commands we expect to use **[doc]**:
  - `CREATE` — create SZS/U8/BRRES… from a directory tree (default destination `%P/%N%T`)
  - `CHECK` — validity check for track files (KCL/KMP, unknown/modified/needed/unneeded files, cannons, slot proposals)
  - `SLOTS` — which slots will run a track
  - `MINIMAP` — print/patch minimap data; `--auto` computes translations from vertex min/max
  - `LIST`/`LL` — list archive contents · `EXTRACT`/`X` · `AUTOADD` — manage auto-add library
  - `TRACKS` — list the 32 track + 10 arena internal names (source for the slot catalogue)
  - `ANALYZE` — machine-readable analysis of track files
- Options **[doc]**: `-d/--dest path` (with `%`-escapes), `-D/--DEST` (creates dirs), `-o/--overwrite`,
  `-r/--remove-dest`, `-C/--compr level` (0–9, `FAST`=1, `BEST`=9 default, `ULTRA`=10), `--fast`,
  `--no-compress`, `--auto-add`/`--aadd`, `--autoadd-path dir`, `--minimap` (fix minimap like `minimap --auto`),
  `-n/--norm`, `--json` / `--sections` / `--bash` output modes for info dumps, `-q/-v`, `-t/--test`,
  `--kcl list`, `--kcl-script file`, `--kcl-flag joblist`, `--tri-area`, `--tri-height`, `--max-mipmaps` (default 4),
  `--mipmap-size` (default 8), `-x/--transform` image formats (e.g. `TEX.CMPR`), `--slot keyword`,
  `--speed-mod`, `--ktpt2`.
- `wkclt analyze course.kcl` (triangle count, bounds), `wkclt flags course.kcl` (per-flag breakdown) **[doc: add-on README]**
- `wkmpt` decode/encode KMP text; text format guide: https://szs.wiimm.de/info/kmp-guide.html **[doc]**
- `wimgt` converts TPL/TEX/BTI/BREFT/PNG **[doc]**; ABMatt requires it on PATH **[doc]**
- **Open questions (S1):** exact `create` invocation from a folder to a named `.szs`; whether `check`
  supports a machine-readable mode or which text format to parse; exit codes for warnings vs errors;
  how auto-add reports inserted files; Cygwin path handling on Windows with spaces/unicode.

## RiiStudio CLI (`rszst`)
- Repo: https://github.com/riidefi/RiiStudio (now served from github.com/snailspeed3/RiiStudio).
  Licence: **overall grant unconfirmed; do not redistribute yet**. At the S3a pin,
  no root licence grant was found; `source/gctex/Cargo.toml` declares GPL-2.0-or-later.
  Component MIT declarations do not license the entire CLI.
- Latest release verified in S3a: **Alpha 5.11.5**, commit
  `09e5754d56562219c87390c8d64ef31110725ccd`. GitHub release API lists Windows/macOS
  assets only. Linux CLI builds from source using the recipe in [SPIKES.md S3](../dev/SPIKES.md#s3-brres-backend-bake-off-p0-t06a--p0-t06b).
  Older desk research below describes 5.11.3; only S3a rows are verified on 5.11.5.
- Commands **[doc]**: `import-brres`, `import-bmd`, `decompress`, `compress --algorithm {nintendo,
  worst-case-encoding,mkw-sp,ctgp,haroohie,ct-lib,mk8,lib-yaz0}`, `extract`, `create`, `kmp-to-json`,
  `json-to-kmp`, `kcl-to-json`, `dump-presets <model> <folder>`, `optimize <brres|bmd>`,
  `import-tex0` (png/jpg → tex0), `brres-to-json` (WIP, format may change), `json-to-brres` (5.11.2+).
  `import-command` is deprecated.
- Import options seen in community docs (for `import-bmd`; **verify for `import-brres`**):
  `--mipmaps`, `--scale N`, `--merge-mats`, `--cull-degenerate`, `--cull-invalid`, `--preset-path=DIR`.
  Textures expected next to the DAE/FBX or in a `textures` folder.
- GUI importer default "Combine identical materials" can merge materials sharing a texture — relevant
  to material-name stability **[doc]**.
- **Open questions (S3/S4):** per-texture format control on import; transparency/cull flags; exit codes;
  whether presets survive BrawlCrate-edited files; JSON schema stability across versions.

### RiiStudio CLI discovery (S3a, verified Alpha 5.11.5 Linux build)

| Exact argv after executable | Exit | Observed output |
|---|---|---|
| `--version` | 255 | stdout: parser 0.1.6 **and** application Alpha 5.11.5 |
| `--help` | 255 | stdout: subcommands and application banner |
| `import-brres --help` | 255 | `<FROM> [TO]`; `--model-name`, mipmaps/min/max, `--auto-transparency`, `--preset-path`, `--cull-degenerates` |
| `brres-to-json --help`, `json-to-brres --help` | 255 | `<FROM> [TO]`; descriptions contain copy/paste errors |
| `dump-presets --help`, `import-tex0 --help` | 255 | positional input and optional destination |
| `nonsense`, `import-brres` (no input) | 255 | stdout: `error:` plus usage; stderr empty |

Recordings: [linux-cli.json](../../tests/fakes/recordings/rszst/5.11.5/linux-cli.json).
Discovery must require the application banner and expected help content, not exit 0
or the parser's version alone. All commands above ran without display variables.
This does **not** verify conversion effects, conversion failure codes or Windows.
S3b must characterize those before any backend/default decision.

### Verified conversion commands (S3b, rszst Alpha 5.11.5 / ABMatt 1.3.2, Linux)

| Tool | Operation | Exact argv template | Exit codes | Verified how |
|---|---|---|---|---|
| rszst | DAE → BRRES | `rszst import-brres IN.dae OUT.brres [--model-name NAME] [--mipmaps --min-mip N]` | 0 ok, 255 fail | real run, P0-T06b |
| rszst | BRRES → JSON | `rszst brres-to-json IN.brres OUT.json` | 0 ok, 255 fail | real run, P0-T06b |
| rszst | JSON → BRRES | `rszst json-to-brres IN.json OUT.brres` | 0 ok | real run, P0-T06b |
| rszst | dump material presets | `rszst dump-presets IN.brres OUTDIR` | 0 ok | real run, P0-T06b |
| rszst | reapply presets at import | `rszst import-brres IN.dae OUT.brres --model-name NAME --preset-path DIR` | 0 ok | real run, P0-T07 |
| abmatt | copy material between files | `abmatt -b SRC.brres -b DST.brres -f CMDS.txt -o` with `copy material for X in SRC.brres` / `paste material for X in DST.brres` | 0 ok | real run, P0-T07 |
| wkclt | KCL → filtered OBJ | `wkclt decode IN.kcl --dest OUT.obj --kcl-script FILTER.txt` | 0 ok, 64 if dest exists | real run, P0-T08 |
| abmatt | OBJ → minimap BRRES | `abmatt convert IN.obj to map_model.brres -o` (destination **must** contain lowercase `map`) | 0 ok | real run, P0-T08 |
| wszst | patch minimap translations | `wszst minimap --auto FILE` | 0 ok (also 0 when it does nothing) | real run, P0-T08 |
| abmatt | DAE → BRRES | `abmatt convert IN.dae to OUT.brres -o` | 0 ok, 1 fail | real run, P0-T06b |
| abmatt | edit materials | `abmatt -b FILE.brres -o -f COMMANDS.txt` | 0 ok, 1 fail | real run, P0-T06b |
| abmatt | inspect | `abmatt -b FILE.brres -c info` | 0 | real run, P0-T06b |

Unlike the help output above, **conversion exit codes are meaningful**: rszst returns 0
on success and 255 on a genuine failure (verified against garbage input).

#### Backend behaviour the adapter must encode (S3b)
- **rszst cannot read an ABMatt BRRES**: `Failed to read MDL0 course: Invalid
  quantization for normal data: U16`, exit 255. ABMatt reads rszst output fine. The
  pipeline direction is therefore fixed: rszst imports, ABMatt post-processes.
- **ABMatt has no model-name option.** The MDL0 name is taken from the source file stem
  up to the first `_` (`vrcorn_xyz.dae` → `vrcorn`). Writing to `<slot>_model.brres`
  whose stem disagrees fails with `Model name does not match file` and writes nothing.
  Stage the DAE under the intended name. rszst uses `--model-name` instead.
- **`abmatt -c "<multi-word command>"` is broken** (the argument is mangled and the run
  dies in the parser). Use a command file with `-f`.
- **`set tex0 format:IA8` exits 0 but changes nothing** — a silent no-op. Do not expose
  per-texture format control through ABMatt.
- **`--mipmaps` alone is a no-op** at the default `--min-mip 32` for 64x64 textures; pass
  `--min-mip` too. Default mipmap counts differ between backends (rszst 1, ABMatt 3).
- Material selectors use **material** names (`for water`), not object names; a bad
  selector fails loudly with `No items found in selection!`.

#### Material capture / reapply behaviour (S4, P0-T07)
- **Presets match on material name, and a miss is silent.** `import-brres --preset-path`
  skips any preset whose material is absent from the regenerated model and still exits 0.
  Renaming a material orphans its captured edits with no warning — the app must diff
  preset names against the model's materials itself.
- **`dump-presets` writes one opaque binary `<material>.rspreset` per material.** No
  published schema; treat as tool-version-coupled and re-verify after an rszst bump.
- **ABMatt's paste autofix deletes orphaned textures.** Pasting a material onto a file
  where the target name no longer exists applies the settings and then removes the
  unused texture (`Unused textures: {...}` / `(FIXED): Remove textures`), exit 0.
- **ABMatt's `-a`/`--auto-fix` cannot disable that in 1.3.2**: `-a 0` parses `0` as a
  command (`Unknown command '0'`, exit non-zero), `-a0` gives `option -0 not recognized`,
  and `--auto-fix=0` gives `option --auto-fix must not have an argument`.
- **`brres-to-json` output is not self-contained.** It writes a `<stem>.bin` sidecar
  (magic `RBUF`) holding geometry; `json-to-brres` reads it from beside the `.json` and
  exits **255** writing nothing if it is missing. Keep the pair together.
- **SRT0 animations live outside the material list.** `dump-presets` and ABMatt
  copy/paste carry them; a material-only JSON merge drops them unless the top-level
  `srts` array is copied too. `add srt0 for <material>` authors one headlessly.

#### Minimap generation (S5, P0-T08)
- **`wszst minimap FILE` prints a header and no data rows when `posLD`/`posRU` are
  missing, exit 0.** Absence of `Translation:` rows is the only failure signal.
- **ABMatt creates the `map`/`posLD`/`posRU` bones from the DESTINATION filename**, not
  the model name: it looks for a lowercase `map` substring in the output path
  (`map_model.brres`, `mymap.brres`, `roadmapping.brres` all match; `MAP.brres` does
  not). A *source* file named `map*` renames the MDL0 to `map` but creates **no bones**
  — a file that passes a name check and is useless in game. Always verify the bones.
- **rszst cannot produce minimap bones.** `import-brres --model-name map` names the MDL0
  and leaves a single `$MergedNode_0` bone; `wszst minimap --auto` then no-ops at exit 0.
  The minimap is the one component that must use ABMatt, not rszst (contra ADR-004's
  general default).
- **`wszst minimap --auto FILE` patches translations in place**, exit 0, rewriting the
  bone flags (observed `0x11c` → `0x31f`) and tightening the bounding box to the
  recommended values. Run it after every minimap conversion.
- **`wkclt decode --kcl-script SCRIPT`** filters triangles during decode; `tri$remove()`
  over wall/boundary types yields a drivable-surface OBJ for the minimap. Script syntax
  is Wiimms' own parser (`@for`, `@function`, `tri$*()`), documented at
  https://szs.wiimm.de/opt/kcl-script; `vendor/blender-mkw-utilities/lower-walls.txt` is
  a working reference.
- **ABMatt crashes on a DAE whose stem disagrees with a `*_model.brres` destination**:
  `AttributeError: 'Brres' object has no attribute 'srt0'`, exit 1. Stage the source
  under the intended stem first.

## ABMatt (ANoob's BRRES Material Tool)
- Repo: https://github.com/Robert-N7/abmatt · Licence: GPL-3.0 **[doc]** · Latest: **v1.3.2 (2022-06-06)** **[doc]**
- Releases for Linux and Windows; or `pip install git+https://github.com/Robert-N7/abmatt.git` **[doc]**
- **Pins old deps** (PyQt5 5.15, numpy 1.19, pillow 9, pycollada 0.7, lxml 4.6…) → run isolated,
  never import into the app (ADR-003) **[doc: requirements.txt]**
- CLI **[doc]**: `abmatt [command_line] [flags]`; `-b/--brres file`, `-d/--destination`, `-f/--file commands.txt`,
  `-o/--overwrite`, `-a/--auto-fix level`, `-l/--loudness 0-5`, `-i` interactive, `--moonview`.
- Command language **[doc]**: `convert file.dae to file.brres [include a,b] [exclude c] [patch] [no-colors]
  [no-normals] [single-bone] [no-uvs]`; `set material xlu:true for <regex>`; `set layer ...`;
  `add tex0:name.png format:ia8`; `copy material for * in a.brres` / `paste material for * in b.brres`;
  presets `[name]` blocks + `preset name for <material>`; material keys include `xlu, ref0, comp0,
  blend, blendsrc, blenddest, cullmode (all|inside|outside|none), constantalpha, lightchannel,
  drawpriority`; TEX0 formats `cmpr c14x2 c8 c4 rgba32 rgb5a3 rgb565 ia8 ia4 i8 i4`.
- Behaviour **[doc]**: when replacing an existing model, materials with matching names take on the
  previous material's properties. Known limits: non-standard files in BRRES unsupported; Windows
  installer may hang.
- Minimap: importing a DAE with ABMatt yields a `map` bone for map models **[doc: mkwiiki Creating a Minimap]**;
  the Blender add-on's minimap export uses ABMatt **[doc: add-on README]**.

## Blender + Blender-MKW-Utilities
- Add-on: https://github.com/Le-Sponk/Blender-MKW-Utilities (fork of Gabriela-Orzechowska's), GPL-2.0-or-later,
  verified on Blender 4.0.2, 4.1.1, 4.2.9 LTS, 4.5.9 LTS, 5.2.1 LTS with Wiimms v2.42a and ABMatt v1.3.2 **[doc]**
- Headless pattern used by the add-on's own tests **[doc]**:
  `blender -b --factory-startup --python verify.py -- <addon-dir>`
- KCL export: objects must end in `_F` + 4 uppercase hex digits; exporter reports exported/skipped
  objects and extents on stdout (`[MKW Utilities] KCL export: …`) **[doc]**; default un-bean mode
  `LOWER` passes `--kcl-script=<plugin dir>/lower-walls.txt` to `wkclt` **[doc]**.
- Collada export methods: FbxConverter (Windows default when present) or built-in writer (Linux/macOS,
  Blender 5.x); built-in writes `<triangles>` per material and can copy textures next to the DAE;
  strips Blender `.001` suffixes **[doc]**.
- Tool discovery inside the add-on: preference folder → PATH → standard locations; handles Flatpak/Snap **[doc]**.
- **Open questions (S2):** operator `bl_idname`s and parameters; which exports need a UI context; how to
  pass tool paths when `--factory-startup` ignores user preferences.

## BrawlCrate
- Windows .NET WinForms app; **32-bit only** **[doc: add-on README]**.
- Linux via Wine: separate prefix, `winetricks --unattended dotnet48`, then `winetricks win10` (plugins
  are disabled on Windows ≤ 7), run `wine BrawlCrate.exe`; Mono is not usable (unreadable UI) **[doc: Roadhog360/BrawlToolsSetupLinux]**
- VM/no-GPU error "Unable to find an entry point named 'glActiveTexture'" → needs a real GL driver or
  Mesa llvmpipe (system-wide) **[doc: add-on README]**
- Plugin system (BrawlAPI, Python scripts in Loaders/Plugins folders; e.g. EasyReplace automates model
  importing) → basis for optional P14 bridge **[doc]**
- **Open questions (S7):** file path as first argument opens the file? single-instance behaviour?

## RiiStudio (GUI)
- Opens BRRES/BMD/KMP and post-effect formats `.bblm .bdof .bfg .blight .blmap`; drag-drop DAE/FBX opens
  the importer **[doc]**. Material presets import/export in the GUI **[doc]**.
- **Open question (S7):** file path argument support.

## Lorenzi's KMP Editor
- https://github.com/hlorenzi/kmp-editor · Electron/Node · prebuilt releases (latest seen v0.7.7) **[doc]**
- Automatically loads `course.kcl` from the same folder as the KMP and shows it in 3D **[doc: mkwiiki]**
- **Open question (S7):** file path argument; save behaviour (in place? atomic?).

## KMP Cloud
- Windows, 2D editor with spreadsheet views **[doc: mkwiiki]** · **Open question:** CLI args, Wine viability.

## Dolphin / DolphinTool
- `dolphin-tool extract -i game.iso -o out [-p DATA|-g] [-s /sys/main.dol] [-l] [-q]` **[doc]**
- Riivolution content folder: `<Dolphin user dir>/Load/Riivolution` (Windows `%APPDATA%\Dolphin Emulator\Load\Riivolution`;
  Linux `~/.local/share/dolphin-emu/Load/Riivolution` or `~/.dolphin-emu/...`) **[doc]**; Riivolution
  patches are started from the GUI ("Start with Riivolution Patches…") **[doc]**
- **Open questions (S8):** booting an extracted game via `-e <dir>/sys/main.dol`; any CLI path to enable
  Riivolution; `-b` batch mode; user dir override `-u`.

## Wine / winetricks (Linux only)
- Pass Windows program arguments after the program; set `WINEPREFIX`; convert paths with `winepath -w` **[doc]**

---

## Launch contracts (fill in during S7; the `editors` adapter reads this table's decisions)
| Tool | OS | Launcher | File arg opens file? | Single instance? | Notes / evidence |
|---|---|---|---|---|---|
| BrawlCrate | Win | direct | ? | ? | |
| BrawlCrate | Linux | wine (prefix) | ? | ? | path via `winepath -w` |
| RiiStudio | Win/mac | direct | ? | ? | |
| Lorenzi KMP Editor | all | direct | ? | ? | KCL auto-load from folder |
| KMP Cloud | Win | direct | ? | ? | |
| Blender | all | direct/flatpak | yes (`blender file.blend`) **[doc: standard]** | no | |
| Dolphin | all | direct | `-e file` **[unverified]** | no | |

## Verified command table (fill in; adapters must only use rows marked verified)
| Tool | Version | Operation | Exact argv template | Exit codes | Output parsed? | Verified how |
|---|---|---|---|---|---|---|
| wszst | 2.42a r8989 | version banner | `wszst version` | 0 | not yet | real run, P0-T02 |
| wkclt | 2.42a r8989 | version banner | `wkclt version` | 0 | not yet | real run, P0-T02 |
| wkmpt | 2.42a r8989 | version banner | `wkmpt version` | 0 | not yet | real run, P0-T02 |
| wimgt | 2.42a r8989 | version banner | `wimgt version` | 0 | not yet | real run, P0-T02 |
| blender | 5.2.2 LTS | version | `blender --version` | 0 | not yet | real run, P0-T02 |
| abmatt | 1.3.2 (release) | usage banner | `abmatt --help` | 0 | not yet | real run, P0-T02 |
| wkclt | 2.42a r8989 | analyze KCL | `wkclt analyze FILE.kcl` | 0 | not yet | real run, P0-T03 |
| wkclt | 2.42a r8989 | per-flag triangle table | `wkclt flags FILE.kcl` | 0 | not yet | real run, P0-T03 |
| wkmpt | 2.42a r8989 | compile KMP text | `wkmpt encode SRC.txt --dest OUT.kmp --overwrite` | 0 (warnings do not fail) | not yet | real run, P0-T03 |
| wkmpt | 2.42a r8989 | decode KMP to text | `wkmpt decode FILE.kmp --dest OUT.txt --overwrite [--brief]` | 0 | not yet | real run, P0-T03 |
| wszst | 2.42a r8989 | build SZS from a stage dir | `wszst create DIR --dest OUT.szs --overwrite [--compr=LEVEL]` | 0 = ok | no | real run, P0-T04 |
| wszst | 2.42a r8989 | validate a track | `wszst check FILE.szs [--brief]` | **see warning below** | yes, text | real run, P0-T04 |
| wszst | 2.42a r8989 | structured analysis | `wszst analyze --json FILE.szs` | 0 | yes, JSON | real run, P0-T04 |
| wszst | 2.42a r8989 | list archive contents | `wszst list [--long] FILE.szs` | 0 | yes, text | real run, P0-T04 |
| wszst | 2.42a r8989 | slot proposals | `wszst slots FILE.szs` | 0 | yes, text | real run, P0-T04 |

### wszst check: the exit code is NOT pass/fail (P0-T04)
Verified by real runs; see [SPIKES.md §S1](../dev/SPIKES.md#s1--wiimms-assemble--check-p0-t04).

| Input | Exit | Prints `ERROR #`? |
|---|---|---|
| Valid track, and track with 5 warnings, and empty archive | **2** (`DIFFER`) | no |
| **Corrupt / unrecognised file** | **0** | **yes** (`ERROR #39`) |
| File not on disk | 78 (`CAN'T OPEN FILE`) | yes |

The adapter must parse output and treat `ERROR #` as failure regardless of exit code.
`wszst create` is normal (0 = success); only `check` behaves this way.

Output severities are prefixed `+ WARNING:`, `- HINT:`, `* INFO:`, and the run ends with
`=> N warnings, M hints and K info for <type>:<path>`. `-B/--brief` drops hints.
Missing components are only reported when a KMP is present:
`+ WARNING: Missing file:    ./course_model.brres (or '_d' variant)`.

### wszst machine-readable output (P0-T04)
`check --sections` and `slots --sections` are **rejected** (`ERROR #108`, exit 108).
Only `analyze` is structured: `--json` (one JSON object) or `--sections` (`key = value`).
Useful keys: `valid_track`, `valid`, `lap_count`, `n_ckpt0`, `slot_info`, `used_x_pos`/
`used_y_pos`/`used_z_pos` (range check), `missed_subfiles`, `warn`, and per-component
hashes `sha1_kcl`/`sha1_kmp`/`sha1_course`/`sha1_vrcorn`/`sha1_minimap` (empty string when
that component is absent — the reliable way to detect missing files).
Prefer `analyze --json` over `slots`: `slot_info` carries the same data.

### wszst create (P0-T04)
- Builds from a plain directory and **does not validate**: it produced an SZS from a
  KCL+KMP only, and from a completely empty directory. Always follow with `check`.
- Compression on the fixture (payload 16928 B): `--no-compress` 16928 B/0.001 s,
  `--fast` = `--compr=FAST` 10118 B/0.002 s, default = `--compr=BEST` 8486 B/0.007 s,
  `--compr=ULTRA` 8247 B/0.009 s. Re-measure on a real track before setting defaults.
- `-d/--dest` supports `%N` (source name) and `%T` (default extension); `-D/--DEST` also
  creates directories (`--DEST 'out/%N%T'` produced `out/minimal.szs`).
- `--auto-add` is a **silent no-op** without an auto-add library: no warning even with
  `-v`. The app must check for a configured library itself.

## KMP text format (P0-T03, verified against wkmpt 2.42a)
Hand-writing KMP text is easy to get wrong; these cost real debugging time:
- Sections are `[KTPT]`, `[ENPT]`, … in **square brackets**. `#SECT# NAME` is not the
  syntax and silently yields empty sections.
- The first line must be exactly `#KMP` (the magic). Directives inside a section start
  with `@`, e.g. `@AUTO-CONNECT`, `@AUTO-NEXT`.
- `[ENPH]`, `[ITPH]`, `[CKPH]` are **informational only** when reading: they are
  regenerated from the point sections. Writing a group table there has no effect.
- Group links come from `@AUTO-CONNECT = AC$PREV | ACF$FIX` (ENPT/ITPT) or an explicit
  `$GROUP G1,  next: G1` line inside the point section (CKPT, which rejects AUTO-CONNECT).
  `M` is **not** a valid link token in source files, despite appearing in decoded output.
- `CKPT` rows take **8** values: `left.x left.y right.x right.y respawn mode prev next`.
  Positions are 2D (game x,z). Mode `0` marks the lap counter; `-1` is a normal point.
  The first checkpoint of a group needs `prev = -1` and the last needs `next = -1`.
- `[CAME]` uses a **four-lines-per-camera** block. Getting it wrong makes wkmpt read each
  line as a separate camera. The fixture ships without a camera on purpose (see below).
- Useful when stuck: compile, then `wkmpt decode … --brief` and copy the syntax the tool
  itself emits. `wkmpt symbols` lists predefined constants. There is no `analyze` command.

## Blender-MKW-Utilities headless export (P0-T03, verified on Blender 5.2.2)
- Registering the add-on from a plain directory works: put its parent on `sys.path`,
  `import addon`, call `register()`. Operator `bpy.ops.kcl.export(filepath=…,
  kclExportScale=100.0)` then runs with no UI context and returns `{'FINISHED'}`.
- It finds `wkclt` through `PATH`, so exporting headlessly only needs
  `.tools/wiimms-szs-tools/bin` prepended to `PATH`.
- Stdout markers are stable and worth parsing in P6:
  `[MKW Utilities] KCL export: N object(s), M triangle(s)`,
  `[MKW Utilities] KCL extent (game units): X=… Y=… Z=…  (scale=100)`,
  `[MKW Utilities] SKIPPED (no valid KCL flag in name): …`.
- It invokes: `wkclt encode <tmp> --dest <out> -o --kcl=MEDIUM
  --kcl-script=<plugin>/lower-walls.txt --const lower=30,degree=45,`.
- `kclExportScale` default is **100** (confirmed in the add-on source), matching the
  project convention.

### Export operators (P0-T05 / S2, add-on v1.12.0, Blender 5.2.2)
All verified headless under `blender -b --factory-startup`; no GUI context needed.
Since add-on `ffa905f` the operators are wrappers around callable functions — prefer
those from automation (see "Callable export API" below).

| Export | Operator | Key arguments |
|---|---|---|
| Collision | `bpy.ops.kcl.export` | `filepath`, `kclExportScale=100.0`, `kclExportUnBeanCorner` (`NONE`/`WEAK`/`LOWER`) |
| Course model | `bpy.ops.export.autodesk_dae` | `filepath`, `daeExportScale=100.0`, `daeExportSelection`, `daeExportCollection`, `daeExportMethod` (`AUTO`/`BUILTIN`), `daeExportCopyTextures` |
| Collision as OBJ | `bpy.ops.export_scene.objkcl` | `filepath`, `use_selection`, `use_materials`, `use_normals`, `use_triangles`, `global_scale` |
| Minimap BRRES | `bpy.ops.export.minimap` | `filepath`, `exportScale=100.0`, `exportSelection`, `exportCollection` |

Preconditions that are easy to misdiagnose:
- `export.minimap` has `poll(): _detect_abmatt()`, so without `abmatt` on `PATH` it
  raises **`poll() failed, context is incorrect`** — a misleading message: the real cause
  is the missing tool, not the context. **Fixed in `ffa905f`:** `poll()` now sets a
  `poll_message_set()` naming ABMatt, and `export_minimap_brres` returns the same reason.
- The minimap export rejects meshes with no material:
  `ABMatt requires every exported mesh to have a material. Missing on: …`.
- `--factory-startup` discards add-on preferences, so tool discovery falls back to
  `PATH`: prepend both `.tools/wiimms-szs-tools/bin` and `.tools/abmatt/bin`.
  `_detect_abmatt()` runs `abmatt` and requires output starting `USAGE: abmatt`.
- `daeExportMethod=AUTO` prefers a bundled **`bin/FbxConverter.exe`** (Windows only) and
  otherwise falls back to the built-in writer, so on Linux AUTO and BUILTIN are
  byte-identical. Do not assume DAE bytes match across operating systems.
- The add-on package directory is `blender-mkw-utilities`, which is not a valid Python
  module name; stage or vendor it under an importable name before `import`.

### Callable export API (add-on `ffa905f`, verified on Blender 4.2.23 + 5.2.2)
Preferred entry points for the bridge. Options are plain dataclasses, not Blender
properties, so no operator instance is needed; `report` takes Blender's
`report(level, message)` signature.

| Function | Options dataclass | Format-specific result keys |
|---|---|---|
| `export_kcl(context, options, report)` | `KclExportOptions` | `extent` (game units, 3-tuple) |
| `export_collada(context, options, report)` | `ColladaExportOptions` | `method` (`builtin`/`fbx_converter`), `textures`, `texture_conflicts` |
| `export_minimap_brres(context, options, report)` | `MinimapExportOptions` | `method` |

Every result — success or failure — carries `ok`, `filepath`, `objects`, `triangles`,
`skipped_objects` and `error`. The functions never raise: exceptions are caught and
returned as `ok: False` with `error` set. `export_scene.objkcl` has **no** extracted
form; call it via `bpy.ops`.

Behaviour worth knowing:
- Counts come from the return value. Do **not** parse the `[MKW Utilities]` stdout lines;
  they remain for humans only.
- KCL encoding now runs `wkclt` as an argv list via `subprocess.run` with a 120 s timeout
  and a checked exit code (it previously used `os.popen` on a quoted string, which broke
  on paths containing quotes or shell metacharacters).
- A failed ABMatt conversion no longer republishes an existing BRRES: the destination is
  restored and the result reports the tool's own error text.
- `exportCollection=True` includes meshes in **child** collections.
- `kclExportSelection=True` counts only mesh objects.

## Bootstrap pins (P0-T02, verified 2026-09-17 by real download + run)
Machine-readable source of truth: `scripts/tool_catalogue.py`. Installed into `.tools/`
by `uv run python scripts/bootstrap_tools.py` (idempotent; second run ≈0.35 s, no network).

| Tool | Version | Linux asset | SHA-256 | Publishes checksums? |
|---|---|---|---|---|
| Wiimms SZS Tools | 2.42a (r8989) | `szs-v2.42a-r8989-x86_64.tar.gz` | `45c07b8e…393ccc` | **No** — ours recorded on first download |
| Blender | 5.2.2 LTS | `blender-5.2.2-linux-x64.tar.xz` | `84098912…06a168` | Yes, `blender-5.2.2.sha256` (verified match) |
| Blender (compat) | 4.5.14 LTS | `blender-4.5.14-linux-x64.tar.xz` | `9ba871ff…06da3` | Yes; optional, `--only blender-4.5` |
| ABMatt | 1.3.2 | `abmatt_linux-5.13.0-44-generic_x64-1.3.2.tar.gz` | `7a2b03dd…15fe3` | **No** — ours recorded on first download |

Windows assets are pinned in the same file (Wiimms Cygwin64 zip, Blender windows-x64 zip,
ABMatt windows-10 zip) but have not been run — Windows CI (P1-T07) is where they get proved.

Facts worth knowing (all from real runs, not docs):
- **Both Wiimms and ABMatt put their executables in `bin/`**, not at the archive root.
  Wiimms ships 10 tools (`wszst wkclt wkmpt wimgt wbmgt wstrt wctct wlect wmdlt wpatt`).
- **ABMatt v1.3.2's binary reports `Version 1.3.1`** in its own banner. Trust the release
  tag, not the banner. `abmatt --help` exits **0** (an earlier assumption of non-zero was wrong).
- Wiimms tools use `wszst version`, not `--version`; the banner line is
  `wszst: Wiimms SZS Tool v2.42a r8989 x86_64 - Dirk Clemens - 2024-03-26`.
- szs.wiimm.de publishes **no checksums or signatures** anywhere on the download page, so
  integrity rests on HTTPS plus our recorded hash; a changed upstream file fails the next run.
- The ABMatt Linux build is a PyInstaller bundle named for the **5.13 kernel** it was built
  on (2022). It runs fine on this container's 7.0 kernel.
- Python 3.12 is not in the image; `uv python install 3.12` fetches 3.12.13 in ~4 s.

### Lorenzi's KMP Editor — no Linux build (plan change)
v0.7.7 (2025-01-14) ships only `Lorenzi.s.KMP.Editor.0.7.7.exe` and a macOS arm64 zip.
Checked every release back to v0.7.0: no Linux asset has ever been published. The phase
file assumed a Linux release, so the editor is **not** auto-installed; P0-T10 must test it
under Wine, and the Linux launch contract depends on that. Evidence: GitHub releases API.
