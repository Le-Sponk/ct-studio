# CT Studio command line

`ctstudio` with no command starts the app. These commands work without it and never start
the app or load Qt. Run `ctstudio <command> --help` for every option.

| Command | What it does | Exit status |
|---|---|---|
| `ctstudio new FOLDER` | Make a project | 0 made; 1 refused (see the message); 2 bad command line |
| `ctstudio status [FOLDER]` | Show each part's status and why | 0 nothing stops a build; 1 a part has a problem or no project; 2 bad command line |
| `ctstudio build [FOLDER]` | Build the track | 0 built; 1 failed or could not start; 2 bad command line; 3 cancelled |
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
the ones found on PATH, in the usual folders, in CT Studio's own tool folder, in a source
checkout's `.tools/`, or set in CT Studio's settings (a damaged settings file is reported on
stderr and ignored). Output is UTF-8, also when redirected to a file.

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

## `ctstudio build [FOLDER] [--release] [--force] [--only PART] [--json-events]`

Builds the project in FOLDER (default: this folder) into `build/<slot>.szs`, and
`build/<slot>_d.szs` when the project makes the `_d` copy. Parts you supply are copied in,
the track is packed with Wiimm's SZS tool and then checked; `.ctstudio/issues.json` gets
what the check found. Steps whose inputs did not change since the last build are skipped.

- Takes the project's lock, so it refuses (exit 1) while CT Studio has the project open.
- Tools are found as `ctstudio doctor` finds them; a path set in CT Studio wins. A missing
  tool stops the build before anything runs, naming it. The auto-add library set in CT
  Studio is used when the project has auto-add on. A damaged settings file is reported on
  stderr and ignored.
- `--release`: the release build: strongest compression, and the build fails when the
  check finds an error. Without it, a test build: quick compression, and findings never
  fail it.
- `--force`: rebuild every step, even unchanged ones.
- `--only PART`: just that part's steps, without packing the track. PART is one of
  `course_model`, `kcl`, `minimap`, `skybox`, `kmp`, `posteffect`.
- `--json-events`: instead of the text below, one JSON object per line as the build runs
  (schema below). Errors that stop the build before it starts still go to stderr only.
- Ctrl+C cancels: nothing new starts, running steps finish (a running tool is stopped),
  and the last good track is kept.
- Exit status: 0 the build succeeded; 1 it failed, or could not start (no project, project
  open elsewhere, a part CT Studio cannot make yet, a missing tool); 2 bad command line;
  3 cancelled.

```text
Building Pistë, replacing Mario Circuit (Flower Cup, track 1): test build, 8 steps
  done       Copy Collision (0.02 s)
  unchanged  Copy Course data
  done       Pack the track (0.31 s)
             castle_course.szs: 6 files (fast compression), and the _d copy
  done       Check the track (0.12 s)

Found while building:
  warning  Missing bones 'posLD' and 'posRU' in minimap MDL.
           Open map_model.brres in an editor and fix the reported problem.

Build succeeded: 3 done, 5 unchanged in 0.5 s.
Track: build/castle_course.szs
Log: .ctstudio/logs/build-2026-11-03T08-11-23.488115Z.log
```

### `--json-events` (format 1)

```text
{"format": 1, "event": "build_started", "steps": ["stage:kcl", "assemble", "validate"]}
{"format": 1, "event": "step_started", "step": "stage:kcl"}
{"format": 1, "event": "step_finished", "step": "stage:kcl", "duration": 0.02, "issues": []}
...
{"format": 1, "event": "build_finished", "outcome": "succeeded", "ran": [...], ...}
```

- Events, in order: one `build_started` (every step, in build order); per step that runs,
  `step_started`, any `log` lines, then `step_finished` or `step_failed`; per unchanged
  step, `step_skipped` with what it found when it last ran; one `build_finished` last.
  Steps run in parallel, so lines of different steps interleave.
- Step ids: `stage:<part>` (copy your file), `assemble` (pack), `validate` (check).
- `issues`: as in `.ctstudio/issues.json`; `file` is relative to the project (with "/")
  when inside it, otherwise absolute. `severity` is `error`, `warning`, `hint` or `info`.
- `step_failed.cancelled`: true when the step stopped because the build was cancelled.
- `build_finished.log`: this build's log, relative to the project; null if it could not
  be written.
- `format` rises only when a field is renamed or removed or its meaning changes; new
  fields and events may appear in any version.

Every line matches this JSON Schema (the tests check it):

<!-- build-events-schema -->
```json
{
 "$schema": "https://json-schema.org/draft/2020-12/schema",
 "title": "ctstudio build --json-events line (format 1)",
 "oneOf": [{"$ref": "#/$defs/build_started"}, {"$ref": "#/$defs/step_started"}, {"$ref": "#/$defs/log"}, {"$ref": "#/$defs/step_skipped"}, {"$ref": "#/$defs/step_finished"}, {"$ref": "#/$defs/step_failed"}, {"$ref": "#/$defs/build_finished"}],
 "$defs": {
  "issue": {"type": "object", "additionalProperties": false, "required": ["severity", "component", "code", "message", "hint", "source", "file", "wiki"], "properties": {"severity": {"enum": ["error", "warning", "hint", "info"]}, "component": {"type": "string"}, "code": {"type": "string"}, "message": {"type": "string"}, "hint": {"type": ["string", "null"]}, "source": {"type": "string"}, "file": {"type": ["string", "null"]}, "wiki": {"type": ["string", "null"]}}},
  "build_started": {"type": "object", "additionalProperties": false, "required": ["format", "event", "steps"], "properties": {"format": {"const": 1}, "event": {"const": "build_started"}, "steps": {"type": "array", "items": {"type": "string"}}}},
  "step_started": {"type": "object", "additionalProperties": false, "required": ["format", "event", "step"], "properties": {"format": {"const": 1}, "event": {"const": "step_started"}, "step": {"type": "string"}}},
  "log": {"type": "object", "additionalProperties": false, "required": ["format", "event", "step", "text"], "properties": {"format": {"const": 1}, "event": {"const": "log"}, "step": {"type": "string"}, "text": {"type": "string"}}},
  "step_skipped": {"type": "object", "additionalProperties": false, "required": ["format", "event", "step", "issues"], "properties": {"format": {"const": 1}, "event": {"const": "step_skipped"}, "step": {"type": "string"}, "issues": {"type": "array", "items": {"$ref": "#/$defs/issue"}}}},
  "step_finished": {"type": "object", "additionalProperties": false, "required": ["format", "event", "step", "duration", "issues"], "properties": {"format": {"const": 1}, "event": {"const": "step_finished"}, "step": {"type": "string"}, "duration": {"type": "number", "minimum": 0}, "issues": {"type": "array", "items": {"$ref": "#/$defs/issue"}}}},
  "step_failed": {"type": "object", "additionalProperties": false, "required": ["format", "event", "step", "message", "hint", "cancelled", "issues"], "properties": {"format": {"const": 1}, "event": {"const": "step_failed"}, "step": {"type": "string"}, "message": {"type": "string"}, "hint": {"type": ["string", "null"]}, "cancelled": {"type": "boolean"}, "issues": {"type": "array", "items": {"$ref": "#/$defs/issue"}}}},
  "build_finished": {"type": "object", "additionalProperties": false, "required": ["format", "event", "outcome", "ran", "skipped", "failed", "cancelled", "not_run", "issues", "duration", "log"], "properties": {"format": {"const": 1}, "event": {"const": "build_finished"}, "outcome": {"enum": ["succeeded", "failed", "cancelled"]}, "ran": {"type": "array", "items": {"type": "string"}}, "skipped": {"type": "array", "items": {"type": "string"}}, "failed": {"type": "array", "items": {"type": "string"}}, "cancelled": {"type": "array", "items": {"type": "string"}}, "not_run": {"type": "array", "items": {"type": "string"}}, "issues": {"type": "array", "items": {"$ref": "#/$defs/issue"}}, "duration": {"type": "number", "minimum": 0}, "log": {"type": ["string", "null"]}}}
 }
}
```

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
