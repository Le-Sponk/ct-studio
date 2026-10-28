"""Windows-native Wiimm 2.42a conversions: the fakes write markers, not real KMP/TEX0 data."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.wiimm import WiimmError
from ctstudio.core.tools.wiimm_convert import img_encode, kmp_from_text, kmp_to_text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

FIXTURES = ROOT / "tests" / "fixtures" / "generated"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(120),
    pytest.mark.skipif(
        os.name != "nt" or not tp.WIMGT.is_file() or not (FIXTURES / "course.kmp").is_file(),
        reason="Requires native Windows Wiimm 2.42a and generated fixtures",
    ),
]


@pytest.fixture
def work(tmp_path: Path) -> Path:
    folder = tmp_path / "convert é"
    folder.mkdir()
    return folder


def test_real_kmp_round_trip(work: Path) -> None:
    kmp = work / "course.kmp"
    shutil.copyfile(FIXTURES / "course.kmp", kmp)
    text = kmp_to_text(kmp, work / "k.txt", executable=tp.WKMPT)
    assert text.read_bytes().startswith(b"#KMP")
    out = kmp_from_text(text, work / "k.kmp", executable=tp.WKMPT)
    assert out.read_bytes()[:4] == b"RKMD"
    with pytest.raises(WiimmError, match="already exists"):
        kmp_from_text(text, out, executable=tp.WKMPT)


def test_real_kmp_script_error_exit_zero_is_failure(work: Path) -> None:
    text = work / "bad.txt"
    text.write_text("#KMP\n[KTPT]\nbogus line here\n", encoding="utf-8", newline="\n")
    with pytest.raises(WiimmError, match="BOGUS") as caught:
        kmp_from_text(text, work / "bad.kmp", executable=tp.WKMPT)
    assert caught.value.exit_code == 0


@pytest.mark.parametrize(("fmt", "code"), [("CMPR", 14), ("I8", 1), ("RGB5A3", 5), ("RGBA32", 6)])
def test_real_img_encode_formats(work: Path, fmt: str, code: int) -> None:
    png = work / "road.png"
    shutil.copyfile(FIXTURES / "textures" / "road.png", png)
    tex = img_encode(png, work / "road.tex0", fmt, executable=tp.WIMGT)  # type: ignore[arg-type]
    assert (tex.format, tex.width, tex.height, tex.images) == (code, 64, 64, 4)
    no_mips = img_encode(png, work / "flat.tex0", fmt, mipmaps=0, executable=tp.WIMGT)  # type: ignore[arg-type]
    assert no_mips.images == 1


def test_real_img_encode_missing_png(work: Path) -> None:
    with pytest.raises(WiimmError) as caught:
        img_encode(work / "missing.png", work / "m.tex0", "CMPR", executable=tp.WIMGT)
    assert (caught.value.error_code, caught.value.exit_code) == (78, 78)
