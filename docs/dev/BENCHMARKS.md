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
