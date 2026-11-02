"""P3-T05: recognise a file's type from its contents, not its name.

Headers here are built in the test (no game data). Every kind has near misses that must
NOT be recognised (wrong size field, cut-off file, wrong second marker), so a renamed or
damaged file is never taken for the real thing. Real tool output is in test_magic_files.py.
"""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.formats.magic import HEAD_BYTES, FileKind, identify, identify_bytes

pytestmark = pytest.mark.timeout(30)


def brres(size: int = 0x80) -> bytes:
    head = b"bres\xfe\xff\x00\x00" + struct.pack(">IHH", size, 0x10, 1) + b"root"
    return head + bytes(size - len(head))


def kmp(size: int = 0x100, count: int = 15, fixed: int = 0x10) -> bytes:
    """``fixed`` = header bytes before the section offsets: 0x10, or 0x0C in early files."""
    header_len = fixed + 4 * count
    head = b"RKMD" + struct.pack(">IHH", size, count, header_len)
    head += struct.pack(">I", 2520) if fixed == 0x10 else b""
    head += bytes(header_len - len(head)) + b"KTPT"
    return head + bytes(size - len(head))


def kcl(
    offsets: tuple[int, int, int, int] = (0x3C, 0x3C + 12 * 4, 0x100, 0x200),
    masks: tuple[int, int, int] = (0xFFFF0000, 0xFFFFE000, 0xFFFF0000),
    shifts: tuple[int, int, int] = (13, 3, 3),
    size: int = 0x400,
) -> bytes:
    head = struct.pack(">4If3f", *offsets, 300.0, -1.0, -2.0, -3.0)
    head += struct.pack(">3I3If", *masks, *shifts, 250.0)
    return head + bytes(size - len(head))


def u8(size: int = 0x100) -> bytes:
    head = b"\x55\xaa\x38\x2d" + struct.pack(">III", 0x20, 0x40, 0x60)
    return head + bytes(size - len(head))


def yaz0(size: int = 0x40) -> bytes:
    head = b"Yaz0" + struct.pack(">I", 0x1000) + bytes(8)
    return head + b"\xff" * (size - len(head))


def postfx(magic: bytes, size: int = 0x50) -> bytes:
    head = magic + struct.pack(">I", size)
    return head + bytes(size - len(head))


def png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + bytes(17)


def dae(prolog: str = '<?xml version="1.0" encoding="utf-8"?>\n') -> bytes:
    return (prolog + '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema">\n').encode()


def obj(text: str = "# made by hand\no road\nv 0 0 0\nv 1 0 0\nv 0 0 1\nf 1 2 3\n") -> bytes:
    return text.encode()


def seekable_zstd(frames: int = 2, checksums: bool = False) -> bytes:
    """A Zstandard frame start + a seek-table footer, the way Blender 3+ saves compressed."""
    entry = 12 if checksums else 8
    table = bytes(entry * frames) + struct.pack("<IB", frames, 0x80 if checksums else 0)
    table += b"\xb1\xea\x92\x8f"
    return (
        b"\x28\xb5\x2f\xfd"
        + bytes(60)
        + b"\x5e\x2a\x4d\x18"
        + struct.pack("<I", len(table))
        + table
    )


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (brres(), FileKind.BRRES),
        (kmp(), FileKind.KMP),
        (kmp(count=1), FileKind.KMP),
        (kmp(count=6, fixed=0x0C), FileKind.KMP),  # no version field
        (kcl(), FileKind.KCL),
        (kcl(offsets=(0x44, 0x44 + 12, 0x100, 0x200)), FileKind.KCL),  # Wiimm's signature
        (u8(), FileKind.U8),
        (yaz0(), FileKind.YAZ0),
        (postfx(b"PBLM"), FileKind.BBLM),
        (postfx(b"PDOF"), FileKind.BDOF),
        (postfx(b"LGHT"), FileKind.BLIGHT),
        (postfx(b"LMAP"), FileKind.BLMAP),
        (png(), FileKind.PNG),
        (dae(), FileKind.DAE),
        (dae("\ufeff<?xml version='1.0'?>\r\n<!-- exported -->\n"), FileKind.DAE),
        (dae(""), FileKind.DAE),
        (obj(), FileKind.OBJ),
        (
            obj("mtllib a.mtl\r\nv 1 2 3\r\nvt 0 0\r\nvn 0 1 0\r\ng x\r\nusemtl m\r\ns off\r\n"),
            FileKind.OBJ,
        ),
        (b"BLENDER-v300RENDH", FileKind.BLEND),
        (b"BLENDER17-01v0502REND", FileKind.BLEND),
        (gzip.compress(b"BLENDER_v279REND" + bytes(100)), FileKind.BLEND),
        (seekable_zstd(), FileKind.BLEND),
        (seekable_zstd(frames=3, checksums=True), FileKind.BLEND),
    ],
    ids=lambda v: v.value if isinstance(v, FileKind) else None,
)
def test_each_kind_is_recognised(data: bytes, kind: FileKind) -> None:
    assert identify_bytes(data) is kind


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"hello world\n", id="text"),
        pytest.param(brres()[:-1], id="brres cut off"),
        pytest.param(brres().replace(b"root", b"rooT"), id="brres no root"),
        pytest.param(brres().replace(b"\xfe\xff", b"\xff\xfe", 1), id="brres little-endian"),
        pytest.param(brres()[:0xC] + b"\x00\x0c" + brres()[0xE:], id="brres header length"),
        pytest.param(kmp() + b"\x00", id="kmp size wrong"),
        pytest.param(kmp().replace(b"KTPT", b"ENPT"), id="kmp first section"),
        pytest.param(kmp(count=0), id="kmp no sections"),
        pytest.param(kmp(fixed=0x14), id="kmp header too long"),
        pytest.param(kmp(fixed=0x08), id="kmp header too short"),
        pytest.param(
            kmp()[:0x10].replace(b"\x00\x00\x01\x00", b"\x00\x00\x00\x10", 1), id="kmp too short"
        ),
        pytest.param(kcl(masks=(0xFFFF0000, 0xFF0FE000, 0xFFFF0000)), id="kcl odd mask"),
        pytest.param(kcl(shifts=(13, 40, 3)), id="kcl huge shift"),
        pytest.param(kcl(offsets=(0x3C, 0x3C + 13, 0x100, 0x200)), id="kcl normals not vectors"),
        pytest.param(kcl(offsets=(0x3C, 0x48, 0x100, 0x400)), id="kcl octree past end"),
        pytest.param(kcl(offsets=(0x3C, 0x48, 0x40, 0x200)), id="kcl out of order"),
        pytest.param(kcl(offsets=(0x10, 0x1C, 0x100, 0x200)), id="kcl points inside header"),
        pytest.param(kcl()[:0x3B], id="kcl header cut off"),
        pytest.param(u8()[:0x5F], id="u8 data past end"),
        pytest.param(u8().replace(b"\x00\x00\x00\x20", b"\x00\x00\x00\x24", 1), id="u8 root"),
        pytest.param(yaz0()[:16], id="yaz0 header only"),
        pytest.param(b"Yaz0" + bytes(28), id="yaz0 zero size"),
        pytest.param(postfx(b"LGHT")[:-1], id="blight cut off"),
        pytest.param(png().replace(b"IHDR", b"IDAT"), id="png no IHDR"),
        pytest.param(png()[:12], id="png cut off"),
        pytest.param(dae().replace(b"COLLADA", b"svg"), id="other xml"),
        pytest.param(b'<?xml version="1.0"?>\n<COLLADAX/>', id="xml lookalike root"),
        pytest.param(obj("newmtl road\nKd 1 1 1\n"), id="mtl file"),
        pytest.param(obj("# only comments\n\n"), id="obj no vertices"),
        pytest.param(obj("v 0 0 0\nhello there\n"), id="obj stray line"),
        pytest.param(b"v 0 0 0\n\x00\x01", id="obj binary"),
        pytest.param(b"v 0 0 0\x00\x00\n", id="obj nul bytes"),
        pytest.param(gzip.compress(b"PK\x03\x04 a zip in a gzip"), id="gzip not blend"),
        pytest.param(b"\x1f\x8b\x08\x00broken", id="gzip broken"),
        pytest.param(seekable_zstd()[:-1], id="zstd footer cut"),
        pytest.param(b"\x28\xb5\x2f\xfd" + bytes(60), id="zstd not seekable"),
        pytest.param(seekable_zstd()[:-4] + b"\xb1\xea\x92\x8e", id="zstd footer magic"),
        pytest.param(seekable_zstd(frames=0), id="zstd no frames"),
        pytest.param(
            seekable_zstd().replace(b"\x5e\x2a\x4d\x18", b"\x50\x2a\x4d\x18"),
            id="zstd bad skippable frame",
        ),
        pytest.param(b"BLENDE", id="blend cut off"),
    ],
)
def test_near_misses_are_not_recognised(data: bytes) -> None:
    assert identify_bytes(data) is None


def test_every_kind_has_a_plain_label() -> None:
    labels = [kind.label for kind in FileKind]
    assert len(set(labels)) == len(labels)
    assert FileKind.BRRES.label == "BRRES model"
    assert FileKind.YAZ0.label == "compressed track file (SZS)"
    assert all(label and label == label.strip() and not label.endswith(".") for label in labels)


def test_identify_reads_the_start_and_end_of_a_big_file(tmp_path: Path) -> None:
    """The seek table sits at the end; only the first and last 64 KiB are read."""
    data = seekable_zstd()
    big = data[:64] + bytes(5 * HEAD_BYTES) + data[64:]
    path = tmp_path / "scène é.blend"
    path.write_bytes(big)
    assert identify(path) is FileKind.BLEND


def test_a_big_obj_is_judged_on_whole_lines_only(tmp_path: Path) -> None:
    line = b"v 0.000000 1.000000 2.000000\n"
    path = tmp_path / "big.obj"
    path.write_bytes(line * (3 * HEAD_BYTES // len(line)))
    assert identify(path) is FileKind.OBJ


def test_an_obj_cut_off_mid_word_at_64_kib_is_still_an_obj(tmp_path: Path) -> None:
    """The last partial line is dropped: here the read stops inside "usemtl" ("us")."""
    body = b"v 0 0 0\n" * ((HEAD_BYTES - 2) // 8)
    body += b"#" * (HEAD_BYTES - 2 - len(body) - 1) + b"\n"
    path = tmp_path / "cut.obj"
    path.write_bytes(body + b"usemtl road\n" + b"f 1 2 3\n")
    assert len(body) == HEAD_BYTES - 2
    assert identify(path) is FileKind.OBJ


def test_identify_bytes_finds_the_seek_table_at_the_end_of_big_data() -> None:
    data = seekable_zstd()
    assert identify_bytes(data[:64] + bytes(2 * HEAD_BYTES) + data[64:]) is FileKind.BLEND


def test_a_missing_file_or_a_folder_is_a_project_error(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match=r"Could not read missing\.brres"):
        identify(tmp_path / "missing.brres")
    with pytest.raises(ProjectError, match="Could not read posteffect"):
        identify(tmp_path.joinpath("posteffect").mkdir() or tmp_path / "posteffect")


def test_the_name_does_not_matter(tmp_path: Path) -> None:
    path = tmp_path / "course_model.brres"
    path.write_bytes(png())
    assert identify(path) is FileKind.PNG
