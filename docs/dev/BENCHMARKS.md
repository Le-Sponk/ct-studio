# Benchmarks

## P1-T05 — streamed file hashing (Windows)

- Command: `uv run pytest -m "slow and benchmark" -q -s tests/benchmarks/test_hash_200mib.py`
- Environment: Windows 11 (10.0.26200), AMD64 Family 23 Model 96 Stepping 1, Python 3.12.14.
- Input: generated 200 MiB file under a path containing a space and `é`; 200 × 1 MiB writes.
- Result: `hash_file` streamed BLAKE2b in **0.394 s** (one pass, exit 0); digest matched a separately generated expected digest. No performance threshold yet. This measures a recently written file likely served by the OS cache, not cold-disk throughput. Linux remains unmeasured until CI or Mint.
- `tests/benchmarks/test_hash_200mib.py` owns the repeatable measurement; excluded from the local gate by `slow`, run it explicitly before a performance decision.

P1-T08 can expand this file to cover broader baselines; the initial skeleton is present because P1-T05 required a recorded 200 MiB hash measurement.
