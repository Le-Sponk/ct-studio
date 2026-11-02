# CT Studio command line

`ctstudio` with no command starts the app. These commands work without it and never start
the app or load Qt. Run `ctstudio <command> --help` for every option.

| Command | What it does | Exit status |
|---|---|---|
| `ctstudio new FOLDER` | Make a project | 0 made; 1 refused (see the message); 2 bad command line |
| `ctstudio status [FOLDER]` | Show each part's status and why | 0 nothing stops a build; 1 a part has a problem or no project; 2 bad command line |
| `ctstudio open FILE` | Start an editor on a file | 0 started; 1 not started; 2 bad command line |
| `ctstudio doctor` | Check the external tools | 0 the required tools are ready; 1 otherwise |
| `ctstudio setup rszst` | Get RiiStudio's command-line tool | see `--help` |

Errors go to stderr as "what is wrong" followed by "what to do". Tool versions are never
probed by `new`, `status` or `open`: they only look for the programs, so they are fast and
start nothing except, for `open`, the editor itself.

## `ctstudio new FOLDER [--name NAME] [--blend FILE] [--slot TRACK] [--force]`

- Makes FOLDER if needed, with `files/`, `overrides/`, `build/`, `.ctstudio/`, a `.gitignore`
  and `ctstudio.toml`. The project is not left locked.
- `--name`: default the folder's name.
- `--slot`: the original track or arena it replaces. Any of the three names works, in any
  letter case: `old_mario_gc`, `GCN Mario Circuit` or `gMC`. A mistyped one is refused with
  suggestions. Default `beginner_course` (Luigi Circuit).
- `--blend`: must exist. Stored relative to the project when it is inside it, otherwise as
  an absolute path.
- A folder that already has files is refused unless `--force`; a folder that already has a
  project is always refused, so a project is never overwritten.

## `ctstudio status [FOLDER] [--json]`

Reads the project without taking its lock, so it works while the app has it open. Tools are
the ones found on PATH, in the usual folders or set in CT Studio's settings (a damaged
settings file is reported on stderr and ignored).

```text
Sponk Raceway, replacing Moo Moo Meadows (Mushroom Cup, track 2)
Folder: C:/Tracks/Sponk

      Part          Status
----  ------------  ------------------------
[~]   Course model  out of date
        track.blend changed since course_model.brres was made
[ok]  Collision     ready
[ ]   Minimap       missing
        map_model.brres has not been made yet
[x]   Skybox        problem
        needs Blender, which was not found (see the Tools page)
...
3 of 8 parts are ready. Fix the parts marked [x] before building: Skybox.
```

| Icon | `state` | `label` | Meaning |
|---|---|---|---|
| `[ ]` | `missing` | missing | Not made yet, or your file is not there; a build makes it |
| `[~]` | `stale` | out of date | Made, but its inputs or settings changed; a build remakes it |
| `[ok]` | `ready` | ready | Up to date |
| `[ok]` | `manual` | your own file | You chose the file; it is the right type |
| `[!]` | `warning` | warning | Buildable, but worth a look |
| `[x]` | `error` | problem | A build cannot make it: a tool is missing, a file is the wrong type |
| `[*]` | `edited_externally` | edited outside CT Studio | A file CT Studio made was changed; it is kept until you decide |

### `--json` (format 1)

```json
{
 "format": 1,
 "ok": false,
 "project": {
  "name": "Sponk Raceway",
  "folder": "C:/Tracks/Sponk",
  "slot": "farm_course",
  "slot_name": "Moo Moo Meadows"
 },
 "parts": [
  {
   "id": "course_model",
   "name": "Course model",
   "state": "stale",
   "label": "out of date",
   "reasons": ["track.blend changed since course_model.brres was made"]
  }
 ]
}
```

- `format`: raised only when a field is renamed or removed or its meaning changes; new
  fields may appear in any version.
- `ok`: false exactly when the exit status is 1 because a part is in `error`.
- `project.folder`: absolute, with forward slashes on every OS.
- `parts`: always all eight, in this order: `course_model`, `kcl`, `minimap`, `skybox`,
  `kmp`, `posteffect`, `objects`, `track_info`. `state` is one of the seven values above.
  `label` and `reasons` are plain English for people, and may be reworded; scripts should
  use `id` and `state`.
- When the project cannot be read, nothing is printed to stdout and the reason goes to
  stderr (exit 1).

## `ctstudio open FILE [--with EDITOR] [--wine-prefix DIR]`

- Picks the first installed editor for the file type: `.blend` Blender; `.brres` BrawlCrate,
  then RiiStudio; `.kmp` Lorenzi's KMP Editor, then KMP Cloud. A path set in CT Studio's
  settings is the copy started.
- `--with`: one of `blender`, `brawlcrate`, `riistudio`, `kmp_editor_lorenzi`, `kmp_cloud`.
- `--wine-prefix`: Linux only, for a Windows editor run through Wine (TOOLS.md lists how to
  make one for each editor).
- Exit 0 means the editor started. It does not mean the file loaded: several editors stay
  open and empty when a file fails to load, and none say so (TOOLS.md "Launch contracts").
  Warnings, such as RiiStudio and non-ASCII paths on Windows, go to stderr.
