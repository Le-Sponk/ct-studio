# Benchmarks

## P1-T05 — streamed file hashing (Windows)

- Command: `uv run pytest -m "slow and benchmark" -q -s tests/benchmarks/test_hash_200mib.py`
- Environment: Windows 11 (10.0.26200), AMD64 Family 23 Model 96 Stepping 1, Python 3.12.14.
- Input: generated 200 MiB file under a path containing a space and `é`; 200 × 1 MiB writes.
- Result: `hash_file` streamed BLAKE2b in **0.394 s** (one pass, exit 0); the digest
  matched an independently generated expected digest. No performance threshold yet.
  The file had just been written and was likely served by the OS cache, not cold storage.
  A human's Mint run passed this benchmark, but its Linux timing was not in the report.
- `tests/benchmarks/test_hash_200mib.py` owns the repeatable measurement. It is excluded
  from the local gate by `slow`; run it explicitly before a performance decision.
- P1-T08 command re-run on this Windows workstation (Python 3.12): **0.397 s**, digest
  assertion passed, one pass. This is another recently written, cache-sensitive sample,
  not a new cross-platform threshold.

## P3-T04 — component status (Windows)

- Command: `uv run pytest -m "slow and benchmark" -q -s tests/benchmarks/test_status_speed.py`
- Environment: same workstation as P1-T05 (Windows 11, AMD64 Family 23 Model 96, Python 3.12.14).
- Input: 5 synthetic projects x 4 made parts = 20 parts; 25 files of 1 MiB (outputs + `.blend`).
  "Cold": every file touched since it was made and the hash cache cleared, so each file is
  hashed once. "Warm": the next evaluation; size+mtime match the cache, nothing is hashed.
- Result (6 runs): cold **68.5–72.3 ms**, warm **10.0–11.5 ms**; limits (phase file) 300 ms
  and 30 ms, asserted by the test. Files had just been written (OS cache), so cold is not a
  cold-disk number.

## P3-GATE — whole `ctstudio status --json` process (Windows)

- Command: time `.venv/Scripts/python.exe -m ctstudio status <new project> --json` (5 runs),
  same workstation; `python -X importtime` for the split.
- Result: **382–418 ms** per run: Python start ~110 ms (`-c pass`), CT Studio imports
  ~210 ms (`--version` alone ~320 ms), evaluation ~75 ms. Not a phase limit (the 300 ms
  limit is for evaluation, above); TD-011 / P13-T02 trims the imports.

## P4-T08 — build engine (Windows)

- Command: `uv run pytest -m "slow and benchmark" -q -s tests/benchmarks/test_build_speed.py`
  (all benchmarks: `uv run pytest -m benchmark -q -s`).
- Machine: AMD Ryzen 7 4800H (8 cores / 16 threads), 15 GiB RAM, KIOXIA 512 GB NVMe SSD,
  Windows 11 Pro, Python 3.12.14, Wiimm's SZS Tools 2.42a (Cygwin build). Commit: P4-T08.
- Inputs: synthetic only. "Typical track": the committed synthetic KCL and KMP, BRRES
  stand-ins of 3 MiB (course), 1 MiB (skybox) and 256 KiB (minimap), four post-effect files;
  all six parts in manual mode, test build (fast compression). Freshly written files (OS cache).
- Results (3 runs each; limits from ARCHITECTURE §15, asserted):

| What | Runs | Limit |
|---|---|---|
| Typical track, first test build (copy 6 parts, pack, check) | 0.67–0.72 s | < 10 s |
| Same, rebuild with nothing changed, in-process | 41–48 ms | < 1 s |
| Same, as a whole `ctstudio build` process | 474–515 ms | < 1 s |
| One 100 MiB part: copied into the stage | 0.51–0.52 s | — |
| One 100 MiB part: unchanged next build | 21–23 ms | < 1 s |
| Cache key of one step with 1,000 × 4 KiB inputs, cold (all hashed) | 782–838 ms | — |
| Same, warm (size and mtime match, nothing hashed) | 252–260 ms | < 1 s |

- The process figure is mostly start-up (P3-GATE: ~110 ms Python, ~210 ms imports); the build
  itself is ~45 ms. TD-011 / P13-T02 trims the imports.
- **Fixed by this benchmark**: the warm 1,000-input check first took **0.94 s**, almost all in
  `Path.resolve` (five calls per file, slow on Windows). Each input is now resolved once and
  the project folder once per cache (`BuildCache._keyed`, `components.state.resolved_key`):
  0.94 s → 0.25 s, keys unchanged (`tests/unit/test_build_cache_speed.py`).
- Stand-in BRRES bodies are zeros: wszst 2.42a crashed (Cygwin stack dump, exit 35584) on
  random-byte bodies of any size from 128 KiB. Zeros pack faster than real models, so the
  first-build time above is a lower bound. A real track, below, is the honest figure.
- Real track, local only (`tests/realdata/test_build_original_tracks.py`, the user's own
  disc copy in git-ignored `local_fixtures/`, extracted to a temporary folder): castle_course's
  six parts (3.9 MiB unpacked, 2.1 MiB packed) as manual files. 3 runs: test build
  **1.11–1.19 s**, no change **39–50 ms**, release build (best compression, pack + check)
  **2.83–2.89 s**. This run also found that the track check could not read Wiimm's report
  for most real tracks (fixed in P4-T08; see TOOLS.md "wszst check").

## P5-T03e31 — bounded Qt build log model (Windows)

- Scope: the data model only, not a painted dashboard log panel (e32). Synthetic strings;
  Python 3.12.14 on the Windows workstation. These are local samples, not a CI speed limit
  or Linux desktop evidence. Input strings are made before timing the oversized append.
- A single `LogLine("n", "x\r\n" * 1_000_000)` into a model with `max_rows=31`,
  `max_chars=1024`, `max_line_chars=64`: **0.287 s** with a Python loop over every newline,
  **0.0064 s** after C-level counts and cached reverse newline cursors. Both retained 31
  newest rows and counted 999,970 omitted rows. The reverse iterator visits only the bounded
  newest tail; exact total-row counting still scans input in C without copying it.
- With `tracemalloc` active, 50,000 sequential `line {i:06d}` appends under default limits
  took **2.21 s**; reading all 20,000 retained indexes took **0.60 s**. Final message count
  220,000 characters, 30,000 omitted rows; traced Python peak **5,583,092 bytes** after model
  construction. This excludes the caller's input strings and Qt/native allocations.
- Two oversized appends (3,000,000 non-BMP characters, then 1,000,000 CRLF rows) into the
  small model took **0.013 s** with tracing. Python peak **1,004,979 bytes**, including the
  synthetic million-character step ID constructed during the measured loop. No full split
  list, normalized input copy or hidden full original is stored.
- Reproduce the untraced large-event probe from the checkout after `uv sync --locked`:

  ```sh
  uv run python -c "import time; from ctstudio.core.build.events import LogLine; from ctstudio.gui.build_log_model import BuildLogModel; e=LogLine('n','x\r\n'*1000000); m=BuildLogModel(max_rows=31,max_chars=1024,max_line_chars=64); t=time.perf_counter(); m.append(e); print(time.perf_counter()-t, m.rowCount(), m.dropped_rows); assert m.rowCount()==31 and m.dropped_rows==999970"
  ```

- Committed regressions: `tests/gui/test_build_log_model.py` checks peak Python allocation
  bounds for oversized events and sustained eviction, default caps, Unicode and exact-limit
  truncation. `test_build_log_model_protocol.py` checks a real list selection and Qt's model
  protocol against a separate retained-history reference. No machine-time threshold is set.

## Reproducing and comparing a baseline

Run the command above from the repo root with `uv sync --locked` first. The test writes a fresh
200 MiB synthetic file containing no game data, starts `perf_counter()` only after the write,
streams a BLAKE2b digest, verifies it against the independently accumulated expected digest,
and prints `hash_file 200 MiB: <seconds> s`. If the assertion fails, discard the time.

For a baseline, record the commit, OS, CPU, Python version, storage/filesystem and whether
antivirus or other I/O was active. Run it several times on the **same machine**, retaining
individual values and a median; compare like-for-like runs with the same environment and
file size. A fresh write usually leaves the file in the OS cache, so do not call this a
cold-disk benchmark or compare it directly with a differently cached run. CI runners vary;
a single noisy CI timing is diagnostic evidence, not a performance regression.

There is **no performance threshold** in this test today. The review checklist's 10% rule
requires comparable before/after baselines, not an assertion against the Windows 0.394 s
sample on arbitrary hardware. Linux timing not recorded yet; the Mint pass proves digest
correctness and execution, not an equivalent speed. Add later baselines here with measured
command output, never extrapolate from the Windows value.
