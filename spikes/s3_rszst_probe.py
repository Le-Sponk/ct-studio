"""Record S3a CLI discovery output, not conversion correctness (S3b).

Build instructions: docs/dev/SPIKES.md S3. Refuses to overwrite existing evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINARY = ROOT / ".tools" / "riistudio-build-pinned" / "source" / "cli" / "rszst"
QUERIES = [
    ["--version"],
    ["--help"],
    ["import-brres", "--help"],
    ["brres-to-json", "--help"],
    ["json-to-brres", "--help"],
    ["dump-presets", "--help"],
    ["import-tex0", "--help"],
    ["nonsense"],
    ["import-brres"],
]


def record(binary: Path) -> list[dict]:
    environment = os.environ.copy()
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    results = []
    for argv in QUERIES:
        start = time.monotonic()
        result = subprocess.run(  # noqa: S603 - user-selected local executable, argv only.
            [str(binary), *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=20,
            check=False,
        )
        # Help and errors both exit 255 in this Linux build; preserve raw evidence.
        results.append(
            {
                "argv": argv,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "seconds": round(time.monotonic() - start, 4),
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = record(args.binary.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(results, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"Recorded {len(results)} CLI queries in {args.output}")


if __name__ == "__main__":
    main()
