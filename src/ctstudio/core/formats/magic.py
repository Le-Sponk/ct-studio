"""Recognise a file's type from its contents (P3-T05, ARCHITECTURE §4).

``identify(path)`` reads at most the first and last 64 KiB and returns a ``FileKind`` or
``None``. Kinds with a size field (BRRES, KMP, the post-effect files) only match when it
equals the real size, so a cut-off or padded file is not taken for a good one. KCL has no
magic: its header offsets must be in order and inside the file, and its grid masks/shifts
must have the shape Nintendo's format uses.

``.blend`` files come in three forms: plain (``BLENDER`` at the start), gzip (Blender 2.x
"compress") and Zstandard (Blender 3+). Python 3.12/3.13 cannot decompress Zstandard, so
that form is recognised by the seek table Blender writes at the end of the file: a skippable
frame (``5E 2A 4D 18``) ending in the magic ``B1 EA 92 8F`` (Zstandard seekable format).

Byte layouts were checked on 2026-11-02 against files made by Wiimm's tools, ABMatt and
Blender 5.2 (tests/unit/test_magic_files.py) and against original tracks (realdata test).
"""

from __future__ import annotations

import os
import re
import struct
import zlib
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from ctstudio.core.errors import ProjectError

HEAD_BYTES = 64 * 1024
TAIL_BYTES = 64 * 1024


class FileKind(StrEnum):
    YAZ0 = "yaz0"
    U8 = "u8"
    BRRES = "brres"
    KMP = "kmp"
    KCL = "kcl"
    BBLM = "bblm"
    BDOF = "bdof"
    BLIGHT = "blight"
    BLMAP = "blmap"
    PNG = "png"
    DAE = "dae"
    OBJ = "obj"
    BLEND = "blend"

    @property
    def label(self) -> str:
        """Plain words for messages such as "expected a BRRES model, found a PNG image"."""
        return _LABELS[self]


_LABELS = {
    FileKind.YAZ0: "compressed track file (SZS)",
    FileKind.U8: "uncompressed track file (U8)",
    FileKind.BRRES: "BRRES model",
    FileKind.KMP: "course data file (KMP)",
    FileKind.KCL: "collision file (KCL)",
    FileKind.BBLM: "bloom settings (BBLM)",
    FileKind.BDOF: "depth-of-field settings (BDOF)",
    FileKind.BLIGHT: "lighting settings (BLIGHT)",
    FileKind.BLMAP: "light map settings (BLMAP)",
    FileKind.PNG: "PNG image",
    FileKind.DAE: "COLLADA model (DAE)",
    FileKind.OBJ: "OBJ model",
    FileKind.BLEND: "Blender file",
}

type _Check = Callable[[bytes, bytes, int], FileKind | None]


def identify(path: Path) -> FileKind | None:
    """The kind of the file at ``path``, or ``None`` if it is none CT Studio knows."""
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            head = stream.read(HEAD_BYTES)
            stream.seek(max(0, size - TAIL_BYTES))
            tail = stream.read(TAIL_BYTES)
    except OSError as exc:
        raise ProjectError(
            f"Could not read {path.name}.",
            hint="Choose a file (not a folder) that exists and that you can open.",
            details=f"path={path}; error={exc}",
        ) from exc
    return _sniff(head, tail, size)


def identify_bytes(data: bytes) -> FileKind | None:
    """``identify`` for a whole file already in memory."""
    return _sniff(data[:HEAD_BYTES], data[-TAIL_BYTES:], len(data))


def _sniff(head: bytes, tail: bytes, size: int) -> FileKind | None:
    """A known magic decides: a damaged BRRES is "unknown", never retried as KCL/DAE/OBJ."""
    for magic, check in _BY_MAGIC:
        if head.startswith(magic):
            return check(head, tail, size)
    for check in _NO_MAGIC:
        kind = check(head, tail, size)
        if kind is not None:
            return kind
    return None


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _when(kind: FileKind, ok: bool) -> FileKind | None:
    return kind if ok else None


def _brres(head: bytes, _tail: bytes, size: int) -> FileKind | None:
    if len(head) < 0x14:
        return None
    ok = head[4:6] == b"\xfe\xff" and _u32(head, 8) == size and head[0x10:0x14] == b"root"
    return _when(FileKind.BRRES, ok and _u16(head, 0xC) == 0x10)


def _kmp(head: bytes, _tail: bytes, size: int) -> FileKind | None:
    if len(head) < 0x10:
        return None
    count, header_len = _u16(head, 8), _u16(head, 0xA)
    first = head[header_len : header_len + 4]
    # 0x10 header (with version); a few early files in the game have 0x0C (no version)
    ok = _u32(head, 4) == size and 0 < count <= 32 and header_len - 4 * count in (0x0C, 0x10)
    return _when(FileKind.KMP, ok and first == b"KTPT")


def _u8(head: bytes, _tail: bytes, size: int) -> FileKind | None:
    if len(head) < 0x10:
        return None
    root, nodes, data = _u32(head, 4), _u32(head, 8), _u32(head, 12)
    return _when(FileKind.U8, root == 0x20 and 0x20 + nodes <= data <= size)


def _yaz0(head: bytes, _tail: bytes, size: int) -> FileKind | None:
    return _when(FileKind.YAZ0, size > 16 and _u32(head, 4) > 0)


def _sized(kind: FileKind) -> _Check:
    """Post-effect files: magic, then the whole file's size."""

    def check(head: bytes, _tail: bytes, size: int) -> FileKind | None:
        return _when(kind, len(head) >= 8 and _u32(head, 4) == size)

    return check


def _png(head: bytes, _tail: bytes, _size: int) -> FileKind | None:
    return _when(FileKind.PNG, head[12:16] == b"IHDR")


def _blend(_head: bytes, _tail: bytes, _size: int) -> FileKind | None:
    return FileKind.BLEND


def _gzip_blend(head: bytes, _tail: bytes, _size: int) -> FileKind | None:
    try:
        start = zlib.decompressobj(wbits=31).decompress(head, 7)
    except zlib.error:
        return None
    return _when(FileKind.BLEND, start == b"BLENDER")


def _zstd_blend(_head: bytes, tail: bytes, _size: int) -> FileKind | None:
    """Blender 3+: a seekable Zstandard file (seek table in a skippable frame at the end)."""
    if len(tail) < 17 or tail[-4:] != b"\xb1\xea\x92\x8f":
        return None
    frames, descriptor = struct.unpack_from("<IB", tail, len(tail) - 9)
    table_len = frames * (12 if descriptor & 0x80 else 8) + 9
    start = len(tail) - table_len - 8
    if frames == 0 or start < 0:
        return None
    frame = struct.unpack_from("<4sI", tail, start)
    return _when(FileKind.BLEND, frame == (b"\x5e\x2a\x4d\x18", table_len))


def _is_mask(value: int) -> bool:
    """Ones followed by zeros (``0xFFFFE000``): KCL grid masks always look like this."""
    low = ~value & 0xFFFFFFFF
    return value != 0 and low & (low + 1) == 0


def _kcl(head: bytes, _tail: bytes, size: int) -> FileKind | None:
    if len(head) < 0x3C:
        return None
    points, normals, triangles, octree = struct.unpack_from(">4I", head, 0)
    masks = struct.unpack_from(">3I", head, 0x20)
    shifts = struct.unpack_from(">3I", head, 0x2C)
    ok = all(
        (
            0x38 <= points < normals < triangles < octree < size,
            (normals - points) % 12 == 0,  # whole x/y/z float vectors
            all(_is_mask(mask) for mask in masks),
            all(shift < 32 for shift in shifts),
        )
    )
    return _when(FileKind.KCL, ok)


_DAE = re.compile(
    r"\A\ufeff?\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--.*?-->\s*|<!DOCTYPE[^>]*>\s*)*<COLLADA[\s>/]",
    re.DOTALL,
)


def _dae(head: bytes, _tail: bytes, _size: int) -> FileKind | None:
    return _when(FileKind.DAE, bool(_DAE.match(head.decode("utf-8", "replace"))))


_OBJ_WORDS = frozenset(
    b"v vt vn vp f l p o g s usemtl mtllib cstype deg curv curv2 surf parm trim hole scrv sp "
    b"end con mg bevel c_interp d_interp lod shadow_obj trace_obj ctech stech".split()
)


def _obj(head: bytes, _tail: bytes, size: int) -> FileKind | None:
    """Text whose every statement is an OBJ keyword, with at least one vertex."""
    if b"\x00" in head:
        return None
    lines = head.split(b"\n")
    if size > len(head):
        lines.pop()  # cut off at the 64 KiB mark
    words = {line.split(None, 1)[0] for line in lines if line.strip() and not line.startswith(b"#")}
    return _when(FileKind.OBJ, b"v" in words and words <= _OBJ_WORDS)


_BY_MAGIC: tuple[tuple[bytes, _Check], ...] = (
    (b"Yaz0", _yaz0),
    (b"\x55\xaa\x38\x2d", _u8),
    (b"bres", _brres),
    (b"RKMD", _kmp),
    (b"PBLM", _sized(FileKind.BBLM)),
    (b"PDOF", _sized(FileKind.BDOF)),
    (b"LGHT", _sized(FileKind.BLIGHT)),
    (b"LMAP", _sized(FileKind.BLMAP)),
    (b"\x89PNG\r\n\x1a\n", _png),
    (b"BLENDER", _blend),
    (b"\x1f\x8b", _gzip_blend),
    (b"\x28\xb5\x2f\xfd", _zstd_blend),
)
_NO_MAGIC: tuple[_Check, ...] = (_dae, _obj, _kcl)
