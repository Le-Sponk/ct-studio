"""P2-T05c: KMP text and image encoding verify their outputs, never the exit status alone."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.tools.process import RunResult

ROOT = Path(__file__).resolve().parents[1] / "fakes" / "recordings"
KMP = ROOT / "wkmpt" / "2.42a" / "inputs" / "course.kmp"
PNG = ROOT / "wimgt" / "2.42a" / "inputs" / "textures"


def _png(tmp_path: Path, name: str = "road.png") -> Path:
    shutil.copyfile(PNG / name, tmp_path / name)
    return tmp_path / name


@pytest.mark.parametrize(
    ("fmt", "code"),
    [
        ("CMPR", 14),
        ("I4", 0),
        ("I8", 1),
        ("IA4", 2),
        ("IA8", 3),
        ("RGB565", 4),
        ("RGB5A3", 5),
        ("RGBA32", 6),
    ],
)
def test_img_encode_writes_requested_tex0_format(
    fake_tools_path, tmp_path: Path, fmt: str, code: int
) -> None:
    from ctstudio.core.tools.wiimm_convert import img_encode

    dest = tmp_path / "road.tex0"
    tex = img_encode(_png(tmp_path), dest, fmt)  # type: ignore[arg-type]
    assert (tex.path, tex.format, tex.width, tex.height, tex.images) == (dest, code, 64, 64, 4)
    assert fake_tools_path.calls() == [
        {
            "tool": "wimgt",
            "argv": ["encode", "road.png", "-x", f"TEX.{fmt}", "--dest", str(dest)],
            "cwd": str(tmp_path),
        }
    ]


@pytest.mark.parametrize(("mipmaps", "images"), [(0, 1), (2, 3)])
def test_img_encode_forces_mipmap_count(
    fake_tools_path, tmp_path: Path, mipmaps: int, images: int
) -> None:
    from ctstudio.core.tools.wiimm_convert import img_encode

    tex = img_encode(_png(tmp_path), tmp_path / "r.tex0", "RGB5A3", mipmaps=mipmaps)
    assert tex.images == images
    assert fake_tools_path.calls()[0]["argv"][-4:-2] == ["--n-mipmaps", str(mipmaps)]


def test_img_encode_rejects_values_outside_the_measured_range(
    fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.wiimm_convert import img_encode

    with pytest.raises(ValueError, match="mipmaps"):
        img_encode(_png(tmp_path), tmp_path / "r.tex0", "CMPR", mipmaps=21)
    with pytest.raises(ValueError, match="format"):
        img_encode(_png(tmp_path), tmp_path / "r.tex0", "BOGUS")  # type: ignore[arg-type]
    assert fake_tools_path.calls() == []


def test_img_encode_refuses_existing_dest_unless_overwrite(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_convert import img_encode

    dest = tmp_path / "r.tex0"
    dest.write_bytes(b"keep")
    with pytest.raises(WiimmError, match="already exists"):
        img_encode(_png(tmp_path), dest, "CMPR")
    assert dest.read_bytes() == b"keep"
    assert fake_tools_path.calls() == []
    assert img_encode(_png(tmp_path), dest, "CMPR", overwrite=True).format == 14
    assert "--overwrite" in fake_tools_path.calls()[0]["argv"]


def test_img_encode_missing_png_raises(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_convert import img_encode

    with pytest.raises(WiimmError) as caught:
        img_encode(tmp_path / "missing.png", tmp_path / "m.tex0", "CMPR")
    assert (caught.value.error_code, caught.value.exit_code) == (78, 78)


def test_img_encode_wrong_format_written_is_failure(monkeypatch, tmp_path: Path) -> None:
    import struct

    import ctstudio.core.tools.wiimm_convert as conv

    dest = tmp_path / "r.tex0"

    def fake_run(cmd, **_kwargs) -> RunResult:
        header = b"TEX0" + bytes(24) + struct.pack(">HHII", 64, 64, 5, 4)  # RGB5A3, not CMPR
        dest.write_bytes(header)
        return RunResult(0, 0.0, "", "", None)

    monkeypatch.setattr(conv, "run", fake_run)
    with pytest.raises(conv.WiimmError, match="format"):
        conv.img_encode(_png(tmp_path), dest, "CMPR", executable=tmp_path / "wimgt")


def test_img_encode_no_file_written_is_failure(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm_convert as conv

    monkeypatch.setattr(conv, "run", lambda cmd, **_kwargs: RunResult(0, 0.0, "", "", None))
    with pytest.raises(conv.WiimmError, match="without writing"):
        conv.img_encode(_png(tmp_path), tmp_path / "r.tex0", "CMPR", executable=tmp_path / "x")


def test_overwrite_that_leaves_the_old_file_is_failure(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm_convert as conv

    old = tmp_path / "k.kmp"
    old.write_bytes(b"RKMD old but valid")  # a stale file would pass a magic-only check
    monkeypatch.setattr(conv, "run", lambda cmd, **_kwargs: RunResult(0, 0.0, "", "", None))
    text = tmp_path / "k.txt"
    text.write_text("#KMP\n", encoding="utf-8")
    with pytest.raises(conv.WiimmError, match="without writing"):
        conv.kmp_from_text(text, old, overwrite=True, executable=tmp_path / "wkmpt")


def test_kmp_round_trip_through_text(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm_convert import kmp_from_text, kmp_to_text

    kmp = tmp_path / "course.kmp"
    shutil.copyfile(KMP, kmp)
    text = kmp_to_text(kmp, tmp_path / "k.txt")
    assert text.read_bytes().startswith(b"#KMP")
    out = kmp_from_text(text, tmp_path / "k.kmp")
    assert out.read_bytes()[:4] == b"RKMD"
    assert [call["argv"][0] for call in fake_tools_path.calls()] == ["decode", "encode"]


def test_kmp_to_text_requires_kmp_text_output(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm_convert as conv

    dest = tmp_path / "k.txt"

    def fake_run(cmd, **_kwargs) -> RunResult:
        dest.write_bytes(b"RKMD binary, not text")
        return RunResult(0, 0.0, "", "", None)

    monkeypatch.setattr(conv, "run", fake_run)
    kmp = tmp_path / "course.kmp"
    shutil.copyfile(KMP, kmp)
    with pytest.raises(conv.WiimmError, match="not KMP text"):
        conv.kmp_to_text(kmp, dest, executable=tmp_path / "wkmpt")


def test_kmp_from_text_refuses_existing_dest(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_convert import kmp_from_text

    # Recorded: wkmpt encode replaces an existing KMP even without --overwrite.
    text = tmp_path / "k.txt"
    text.write_text("#KMP fake text\n", encoding="utf-8")
    dest = tmp_path / "k.kmp"
    dest.write_bytes(b"keep")
    with pytest.raises(WiimmError, match="already exists"):
        kmp_from_text(text, dest)
    assert dest.read_bytes() == b"keep"
    assert fake_tools_path.calls() == []


def test_kmp_from_text_script_error_on_stderr_is_failure(monkeypatch, tmp_path: Path) -> None:
    import ctstudio.core.tools.wiimm_convert as conv

    dest = tmp_path / "k.kmp"

    def fake_run(cmd, *, on_line, **_kwargs) -> RunResult:
        on_line("stderr", "! wkmpt: Variable 'BOGUS' not found [k.txt @3]: bogus line here")
        dest.write_bytes(b"RKMD" + bytes(8))
        return RunResult(0, 0.0, "", "", None)

    monkeypatch.setattr(conv, "run", fake_run)
    text = tmp_path / "k.txt"
    text.write_text("#KMP\n", encoding="utf-8")
    with pytest.raises(conv.WiimmError, match="BOGUS"):
        conv.kmp_from_text(text, dest, executable=tmp_path / "wkmpt")


def test_kmp_to_text_not_a_kmp_raises(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_convert import kmp_to_text

    bad = tmp_path / "bad.kmp"
    bad.write_bytes(b"not a kmp at all")
    with pytest.raises(WiimmError) as caught:
        kmp_to_text(bad, tmp_path / "k.txt")
    assert (caught.value.error_code, caught.value.exit_code) == (36, 36)


def test_fake_refuses_unrecorded_png_size(fake_tools_path, tmp_path: Path) -> None:
    import struct
    import zlib

    from ctstudio.core.tools.wiimm import WiimmError
    from ctstudio.core.tools.wiimm_convert import img_encode

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 128, 128, 8, 6, 0, 0, 0)
    raw = zlib.compress(b"".join(b"\0" + bytes(128 * 4) for _ in range(128)))
    png = tmp_path / "big.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")
    )
    # Default mipmaps were only measured for 64x64 and 48x40; the fake must not guess.
    with pytest.raises(WiimmError, match="without writing") as caught:
        img_encode(png, tmp_path / "big.tex0", "CMPR")
    assert caught.value.exit_code == 121  # the fake's Unmodelled exit
    assert "unrecorded 128x128" in caught.value.details
    assert not (tmp_path / "big.tex0").exists()
