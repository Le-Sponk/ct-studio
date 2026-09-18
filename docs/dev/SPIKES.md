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
