"""P2-GATE Should fix 6: every input retained beside a recording is accounted for.

``tests/fakes/recordings/inputs_provenance.json`` lists each file under
``recordings/<tool>/<version>/inputs/`` with its SHA-256 and origin. A new, changed or
unlisted file fails here, so nothing reaches the repo without a stated, synthetic source.
Generated inputs are compared with ``make_fixtures.py`` output when it is present locally.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fakes" / "recordings"
GENERATED = ROOT / "tests" / "fixtures" / "generated"
MANIFEST = json.loads((RECORDINGS / "inputs_provenance.json").read_text(encoding="utf-8"))
ORIGINS = {"generated", "authored", "rebuilt", "tool-output"}


def _on_disk() -> dict[str, str]:
    return {
        path.relative_to(RECORDINGS).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in RECORDINGS.glob("*/*/inputs/**/*")
        if path.is_file()
    }


def test_every_retained_input_is_listed_with_its_exact_bytes() -> None:
    listed = {name: entry["sha256"] for name, entry in MANIFEST["inputs"].items()}
    assert _on_disk() == listed


def test_every_entry_says_where_it_came_from() -> None:
    for name, entry in MANIFEST["inputs"].items():
        assert entry["origin"] in ORIGINS, name
        assert entry["how"].strip(), name
        if entry["origin"] == "generated":
            assert "make_fixtures.py" in entry["how"], name


def test_generated_inputs_match_make_fixtures_output() -> None:
    entries = [e for e in MANIFEST["inputs"].values() if e["origin"] == "generated"]
    fixtures = [GENERATED / e["how"].split("tests/fixtures/generated/", 1)[1] for e in entries]
    if not all(path.is_file() for path in fixtures):
        pytest.skip("run scripts/fixtures/make_fixtures.py to compare generated inputs")
    for entry, path in zip(entries, fixtures, strict=True):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path
