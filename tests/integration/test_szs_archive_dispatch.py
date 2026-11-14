"""Build a real synthetic SZS, then dispatch it to fake editors on either CI host.

This proves archive construction and actual process argv/cwd, not editor loading or Wine.
No desktop, generated-fixture folder, game data or new retained binary is required.
"""

import json
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fakes.install import install_program

from ctstudio.core.tools import editors
from ctstudio.core.tools.editors import Launched
from ctstudio.core.tools.wiimm import create_szs, list_files

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from tool_paths import WSZST

pytestmark = [pytest.mark.integration, pytest.mark.timeout(90)]
INPUTS = ROOT / "tests/fakes/recordings/wszst/2.42a/inputs"


def _outcome[T](action: Callable[[], T]) -> T | Exception:
    try:
        return action()
    except Exception as error:
        return error


@pytest.mark.parametrize("tool", ["brawlcrate", "riistudio"])
def test_real_synthetic_szs_two_requests_dispatch_two_fake_editors(
    tmp_path: Path, tool: str
) -> None:
    stage = tmp_path / "synthetic stage"
    stage.mkdir()
    names = {
        "course.kmp": "course.kmp",
        "course.kcl": "course.kcl",
        "map_model.brres": "course_model.brres",
    }
    for source, target in names.items():
        shutil.copyfile(INPUTS / source, stage / target)
    source_bytes = {name: (stage / name).read_bytes() for name in names.values()}
    folders = [tmp_path / "first é 日本", tmp_path / "second é 日本"]
    for folder in folders:
        folder.mkdir()
    first = create_szs(stage, folders[0] / "first.szs", executable=WSZST)
    assert first.read_bytes().startswith(b"Yaz0")
    assert set(list_files(first, executable=WSZST)) == set(names.values())
    second = folders[1] / "second.SZS"
    shutil.copyfile(first, second)
    documents = [first, second]
    originals = [document.read_bytes() for document in documents]
    exe = install_program(
        tmp_path / "fake editor é" / "editor",
        "import json, os, sys\nfrom pathlib import Path\n"
        "target = Path.cwd() / 'receipt.json'\n"
        "pending = target.with_suffix('.pending')\n"
        "pending.write_text(json.dumps({'argv': sys.argv[1:], 'cwd': str(Path.cwd()), "
        "'pid': os.getpid()}), encoding='utf-8')\n"
        "pending.replace(target)\n",
    )
    results = [_outcome(lambda p=p: editors.open_in(tool, p, executable=exe)) for p in documents]
    assert all(isinstance(result, Launched) for result in results), results
    assert len({result.pid for result in results if isinstance(result, Launched)}) == 2
    receipts = [folder / "receipt.json" for folder in folders]
    deadline = time.monotonic() + 8
    while not all(path.is_file() for path in receipts) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert all(path.is_file() for path in receipts), "both actual children must publish receipts"
    rows: list[dict[str, object]] = [
        json.loads(path.read_text(encoding="utf-8")) for path in receipts
    ]
    assert len({row["pid"] for row in rows}) == 2
    for document, result, row, original in zip(documents, results, rows, originals, strict=True):
        assert isinstance(result, Launched) and result.tool_id == tool
        assert result.document == document.resolve() and result.pid > 0
        assert row["argv"] == [
            str(document.resolve()),
            *(["/audio:none"] if tool == "brawlcrate" else []),
        ]
        assert row["cwd"] == str(document.parent.resolve())
        assert bool(result.warnings) == (tool == "riistudio")
        assert document.read_bytes() == original
    assert {name: (stage / name).read_bytes() for name in names.values()} == source_bytes
