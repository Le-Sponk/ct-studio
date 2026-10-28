"""Auto-add with a library built from the user's own game files (``realdata``, HC1).

Needs ``local_fixtures/auto-add/`` built with
``wszst autoadd <your Race/Course folder> --DEST local_fixtures/auto-add`` (see
``local_fixtures/README.md``). Skips when it is absent, so CI never needs, sees or
uploads game content. Nothing read here is written into the repository.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.wiimm import create_szs
from ctstudio.core.tools.wiimm_autoadd import autoadd_verify

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

LIBRARY = ROOT / "local_fixtures" / "auto-add"
KEPT = ROOT / "tests" / "fakes" / "recordings" / "wszst" / "2.42a" / "inputs"
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WSZST.is_file() or not LIBRARY.is_dir(),
        reason="Requires native Windows Wiimm 2.42a and local_fixtures/auto-add/",
    ),
]


def test_own_library_is_usable_and_supplies_the_missing_object(tmp_path: Path) -> None:
    library = autoadd_verify(LIBRARY, executable=tp.WSZST)
    assert library.unusable_reason() is None, library.unusable_reason()
    assert "BRRES itembox.brres" in library.found
    stage = tmp_path / "stage"
    stage.mkdir()
    shutil.copyfile(KEPT / "course.kcl", stage / "course.kcl")
    shutil.copyfile(KEPT / "objects.kmp", stage / "course.kmp")
    plain = create_szs(stage, tmp_path / "plain.szs", executable=tp.WSZST)
    added = create_szs(stage, tmp_path / "added.szs", executable=tp.WSZST, auto_add=library)
    assert added.stat().st_size > plain.stat().st_size
