"""Record the time to stream-hash a real 200 MiB temporary file; no performance assertion."""

from __future__ import annotations

import hashlib
from pathlib import Path
from time import perf_counter

import pytest

from ctstudio.core.fsutil import hash_file


@pytest.mark.slow
@pytest.mark.benchmark
def test_hash_200_mib(tmp_path: Path) -> None:
    path = tmp_path / "200 MiB é.bin"
    chunk = b"a" * (1024 * 1024)
    expected = hashlib.blake2b()
    with path.open("wb") as stream:
        for _ in range(200):
            stream.write(chunk)
            expected.update(chunk)
    assert path.stat().st_size == 200 * 1024 * 1024
    start = perf_counter()
    digest = hash_file(path)
    elapsed = perf_counter() - start
    assert digest == expected.hexdigest()
    print(f"hash_file 200 MiB: {elapsed:.3f} s")
