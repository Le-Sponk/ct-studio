# Settings

Settings → Settings… (Ctrl+,) opens one Settings window: a list of pages on the left, the
page on the right. The pages are, in order: Tools, Build, Editors, Appearance, Advanced.
Settings → Tools… and Settings → Editors… open the same window at that page; Settings… opens it
at the page you looked at last. Each page reads its settings again every time you open it, so
it always shows what is saved now. Tab moves from the page list into the page and ends at
Close.

## Where settings are kept

Some settings belong to a project and travel with it; the rest belong to this computer and
are the same for every project.

| Kept in | What | Where |
| --- | --- | --- |
| The project | Build → This project | `ctstudio.toml` in the project folder ([project file](PROJECT_FILE.md)) |
| This computer | everything else | `settings.json` in CT Studio's settings folder |

The settings folder is `%LOCALAPPDATA%\ctstudio\ctstudio` on Windows and
`~/.config/ctstudio` on Linux (or `$XDG_CONFIG_HOME/ctstudio` when that is set).

Every save keeps a backup of the file it replaces, and keys CT Studio does not know are kept.
A settings file that cannot be used (not valid JSON, a value CT Studio does not accept, or
written by a newer version of CT Studio) is never overwritten: each page shows why, in full,
and turns its choices off or hides them until the file is fixed or deleted and the page is
opened again (on the Tools page, Re-check also reads it again). What CT Studio does meanwhile
is described in [When the settings file cannot be used](#when-the-settings-file-cannot-be-used).

## Tools

The Wiimm SZS Tools, Blender and the editors CT Studio can start, each with its status, where
it was found and how to fix a problem. Browse… sets a program's path, Clear forgets it,
Download page opens the tool's official page and Re-check looks again. A path you set is
saved in `settings.json` under `tools`.

## Build

Two tabs.

**This project** (needs an open project) is saved in the project's `ctstudio.toml` when you
press Save; Undo changes goes back to what is saved. Closing the window with unsaved changes
asks whether to save them. A read-only project is shown but cannot be changed, and Save is
off while a build runs.

| Setting | Choices | Default | Used by |
| --- | --- | --- | --- |
| Test builds | Best (smallest, slowest), Fast (larger, quicker), None (largest, quickest) | Fast | the next test build's `wszst create` command |
| Release builds | the same | Best | the next release build's `wszst create` command |
| Also make the track's _d copy | on, off | on | the next build |
| Auto-add missing object files | on, off | on | the next build, with this computer's auto-add library |

**This computer**: Build steps at once, how many build steps may run at the same time.
Automatic (the default) runs up to 4, fewer on a computer with fewer processors; the list
also offers the numbers from 1 to 8 (or to the number of processors, when that is more, up
to 64), and the file may hold any whole number from 1 to 64. Builds in CT Studio and `ctstudio build`
read it at the start of every build. A choice is saved at once.

## Editors

Which editor Open in… offers first for each kind of file, the editors you add yourself, and
the Wine prefixes used on Linux, on the tabs Order, Your editors and Wine (Linux). Each change
is saved at once. See [Opening part files in editors](OPEN_IN.md).

## Appearance

Colour scheme: Follow system (the default), Light or Dark. A choice is saved and used at
once where the system lets CT Studio change it (if not, the page says so), and every start
of CT Studio uses the saved scheme.

## Advanced

Two tabs.

**This computer**, each choice saved at once:

| Setting | Choices | Default | Takes effect |
| --- | --- | --- | --- |
| Tool commands in the build log | Shown, Hidden | Shown | the next build in CT Studio |
| Build logs kept per project | 20 (default), 5, 10, 50, 100 | 20 | after the next build, in CT Studio or by `ctstudio build` |
| Developer mode | Off, On | Off | the next start of CT Studio |

Tool commands are the program command lines a build runs. Hidden leaves them out of the
dashboard's build log only: the build log file in the project's `.ctstudio/logs` folder always
lists them.

After each build, only the newest build logs in the project's `.ctstudio/logs` folder are
kept; the log of the build just finished is always one of them. The file may hold any whole
number from 1 to 1000; a saved number outside the list is shown in the list too.

Developer mode makes CT Studio watch its own window: each time the window stops responding for
more than 100 ms, CT Studio's log (`ctstudio.log`) records where it was stuck, for bug
reports. Setting the environment variable `CTSTUDIO_DEV=1` also turns it on, whatever the
setting says.

**This project** shows the open project's extra arguments for `wszst`
(`[build] extra_wszst_args` in `ctstudio.toml`), read-only: CT Studio does not pass them to
Wiimm's SZS Tools yet.

## Keys in settings.json

You do not need to edit `settings.json` by hand; this table is for reading it.

| Key | Page | Values | When absent |
| --- | --- | --- | --- |
| `format` | (every save writes it) | `1` | counts as `1` |
| `tools` | Tools | program id → path | found automatically |
| `build_jobs` | Build → This computer | a whole number from 1 to 64 | Automatic |
| `auto_add_library` | (no page yet; set by hand) | a folder | nothing is added |
| `editor_preferences` | Editors → Order | file kind → editor | the default order |
| `custom_tools` | Editors → Your editors | your editors | none |
| `wine_prefixes` | Editors → Wine (Linux) | editor → prefix folder | none chosen |
| `colour_scheme` | Appearance | `"light"`, `"dark"` | follow the system |
| `show_tool_commands` | Advanced → This computer | `true`, `false` | shown |
| `build_logs_kept` | Advanced → This computer | a whole number from 1 to 1000 | 20 |
| `developer_mode` | Advanced → This computer | `true`, `false` | off |
| `recent_projects` | View → Recent projects | up to ten project folders | none |

A `format` higher than `1` means a newer CT Studio wrote the file; this version then leaves it
alone, as if it were damaged.

## When the settings file cannot be used

The file is left exactly as it is. Meanwhile:

- Builds in CT Studio and `ctstudio build` say so and go on without it: "Tool paths, the
  number of build steps at once and the number of build logs kept set in CT Studio are ignored
  for this build." They then use automatic tool finding, Automatic build steps and 20 build
  logs, the dashboard shows the tool commands, and no missing object files are added even
  with Auto-add on (the auto-add library is set in the file).
- Open in… shows why and starts no editor; it never falls back to another editor.
- CT Studio starts with the system's colour scheme and with developer mode off (unless
  `CTSTUDIO_DEV=1`), and says why in its log.
- The dashboard says so above the project buttons; when the reason has more to it (for
  example where the JSON stops being valid), Copy details copies it.
- Every page that uses the file shows the reason and turns its choices off or hides them;
  the Build page's This project tab is not affected, because it is saved in the project.
