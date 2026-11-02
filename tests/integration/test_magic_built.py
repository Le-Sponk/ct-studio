"""P3-T05: track files Wiimm builds are recognised, compressed (Yaz0) and not (U8).

Built from the committed synthetic KCL and KMP; runs wherever Wiimm 2.42a is installed
(both CI operating systems).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.formats.magic import FileKind, identify
from ctstudio.core.tools.wiimm import create_szs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

FIXTURES = ROOT / "tests" / "fixtures" / "generated"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(not tp.WSZST.is_file(), reason="Requires Wiimm 2.42a"),
]


@pytest.mark.parametrize(
    ("compression", "kind"),
    [("best", FileKind.YAZ0), ("fast", FileKind.YAZ0), ("none", FileKind.U8)],
)
def test_built_track_files_are_recognised(tmp_path: Path, compression: str, kind: FileKind) -> None:
    stage = tmp_path / "stage é"
    stage.mkdir()
    for name in ("course.kcl", "course.kmp"):
        shutil.copyfile(FIXTURES / name, stage / name)
    built = create_szs(
        stage,
        tmp_path / f"{compression}.szs",
        compression=compression,  # type: ignore[arg-type] - parametrized literal
        executable=tp.WSZST,
    )
    assert identify(built) is kind
