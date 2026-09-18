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
- Repo: https://github.com/riidefi/RiiStudio (now served from github.com/snailspeed3/RiiStudio) · Licence: **[unverified — check before any redistribution]**
- Latest release seen: **Alpha 5.11.3** (adds `--model-name` to `import-brres`, macOS builds) **[doc]**.
  Last commits observed Oct 2024. Prebuilt Windows/macOS; **no Linux prebuilt** (build from source with
  CMake + assimp + glfw + freetype, plus Rust) **[doc]**.
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
