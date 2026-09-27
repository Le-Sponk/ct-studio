# Third-party notices (development inventory)

CT Studio's own code is [GPL-3.0-or-later](LICENSE). This file records what the source tree
references today; it is **not yet a complete packaged-distribution notice**. Phase 12 must audit
actual shipped wheels, Qt plugins, fonts and installers and include their required licence texts.
Do not infer redistribution permission for an external track tool from its appearance here.

## Pinned source submodule

- [Blender-MKW-Utilities](vendor/blender-mkw-utilities/NOTICE.md) is maintained in a separate,
  pinned git submodule. Its own notice describes the upstream author, its
  **GPL-2.0-or-later** basis and third-party material such as the OBJ exporter and Wiimm's
  `lower-walls.txt`; its full GPLv2 text is in
  [the submodule's LICENSE](vendor/blender-mkw-utilities/LICENSE). Retain those files and
  attribution when using the add-on. The app's GPL-3.0-or-later decision is recorded in
  [ADR-009](docs/DECISIONS.md#adr-009--licence-gpl-30-or-later).

## Direct Python runtime dependencies

These packages are resolved from [uv.lock](uv.lock), not vendored as source in this repo.
The labels below are from the installed packages' distribution metadata at P1-T08; consult
the actual distributions and their licence files when packaging:

| Package | Licence metadata / packaging note |
|---|---|
| PySide6 / Qt | PySide6 reports `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; Qt and bundled components need their own notices. |
| numpy | Reports `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`; inspect bundled third-party notices. |
| pillow | Reports `MIT-CMU`. |
| platformdirs | Reports `MIT`. |
| tomli-w | Reports an MIT classifier. |
| watchfiles | Reports `MIT`. |

The development-only tools are separately declared in `pyproject.toml`; their final packaging
and licences are not asserted here.

## External programs and game assets

Wiimms SZS Tools, RiiStudio, ABMatt, Blender, BrawlCrate, KMP editors and Dolphin are
**not bundled** with CT Studio. They are detected or launched separately; optional downloads
are user-initiated and installed under the gitignored `.tools/` folder during development.
RiiStudio's redistribution permission remains unconfirmed, so the installer must not contain
it. No Nintendo game files, derivatives or auto-add library content are included in this repo.
Users supply their own game-derived files only in the gitignored `local_fixtures/` or their
own project directories. See [the project brief](docs/PROJECT_BRIEF.md#8-legalethical-constraints).
