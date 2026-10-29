"""Windows-native Blender 5.2.2 runs through the P2-T05f adapter, in a ``é 日本`` folder.

Self-made scripts only; ``good.blend`` is the recorded empty scene from the fake inputs.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from ctstudio.core.errors import ToolTimedOut
from ctstudio.core.tools.blender import FAILURE_EXIT, BlenderError, run_script

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import tool_paths  # type: ignore[reportMissingImports] - scripts path inserted above

INPUTS = (
    Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "blender" / "5.2.2" / "inputs"
)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        not tool_paths.BLENDER.is_file(), reason="local Blender 5.2.2 not installed"
    ),
]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    path = tmp_path / "dossier é 日本"
    path.mkdir()
    shutil.copyfile(INPUTS / "good.blend", path / "scène.blend")
    return path


def _write(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def test_script_writes_beside_itself_with_arguments(folder: Path) -> None:
    script = _write(
        folder,
        "écrire.py",
        "import sys, bpy\nfrom pathlib import Path\n"
        "args = sys.argv[sys.argv.index('--') + 1:]\n"
        "Path('résultat.txt').write_text('|'.join(args) + '|' + Path(bpy.data.filepath).name,"
        " encoding='utf-8')\n",
    )
    run_script(
        folder / "scène.blend", script, ["a b", "日本", "--", "-b"], executable=tool_paths.BLENDER
    )
    assert (folder / "résultat.txt").read_text(encoding="utf-8") == "a b|日本|--|-b|scène.blend"


def test_failures_are_typed(folder: Path) -> None:
    boom = _write(folder, "échec.py", "def f():\n    raise ValueError('mauvais é')\n\nf()\n")
    with pytest.raises(BlenderError, match="ValueError: mauvais é") as caught:
        run_script(None, boom, executable=tool_paths.BLENDER)
    assert caught.value.exit_code == FAILURE_EXIT
    (folder / "cassé.blend").write_bytes(b"not a track file\n" * 4)
    ok = _write(folder, "ok.py", "print('ran')\n")
    with pytest.raises(BlenderError, match=r"could not open cassé\.blend") as caught:
        run_script(folder / "cassé.blend", ok, executable=tool_paths.BLENDER)
    assert caught.value.exit_code == 1


def test_timeout_stops_blender(folder: Path) -> None:
    marker = folder / "still running.txt"
    script = _write(
        folder,
        "lent.py",
        "import time\nfrom pathlib import Path\ntime.sleep(8)\n"
        f"Path({str(marker)!r}).write_text('late', encoding='utf-8')\n",
    )
    started = time.monotonic()
    with pytest.raises(ToolTimedOut):
        run_script(None, script, executable=tool_paths.BLENDER, timeout=3)
    assert time.monotonic() - started < 8
    time.sleep(8)
    assert not marker.exists(), "Blender kept running after the timeout"
    if os.name == "nt":
        shutil.rmtree(folder)  # no handle left open by a surviving process
