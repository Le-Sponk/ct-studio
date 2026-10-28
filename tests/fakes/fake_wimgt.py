"""Fake ``wimgt encode``: PNG to TEX0 as the real 2.42a recordings show.

The fake writes a marked TEX0 whose header carries the format code, size and image count
the real tool produced for the same request (``recordings/wimgt/2.42a/windows-ops.json``),
not encoded pixels. Only 8-bit RGBA PNGs, the eight non-palette formats and the recorded
mipmap counts are modelled; anything else is ``Unmodelled``.
"""

from __future__ import annotations

import math
import struct

import fake_wiimm as fw
import wiimm_cli
from fake_runtime import Outcome, Refused, Unmodelled

FORMATS = {"I4": 0, "I8": 1, "IA4": 2, "IA8": 3, "RGB565": 4, "RGB5A3": 5, "RGBA32": 6, "CMPR": 14}
MAX_MIPMAPS = 20
DEFAULT_IMAGES = {(64, 64): 4, (48, 40): 3}  # recorded with wimgt's default --max-mipmaps 4
_HELP = "-> Type 'wimgt -h' or 'wimgt help' (pipe it to a pager like 'less') for more help.\n\n"


def _refuse(code: int, name: str, message: str) -> Refused:
    return Refused(
        Outcome(code, "", f"!! wimgt: ERROR #{code} [{name}]\n!!        {message}\n{_HELP}")
    )


def _format(parsed: wiimm_cli.Parsed) -> str:
    value = parsed.options.get("--transform", "TEX.RGB5A3")
    keyword = str(value).upper().removeprefix("TEX.")
    if keyword not in FORMATS:
        if "." in keyword or "," in keyword or "=" in keyword:
            raise Unmodelled(f"--transform {value}")
        raise _refuse(110, "SYNTAX ERROR", f"Invalid keyword for option --transform: {keyword}")
    return keyword


def _mipmaps(parsed: wiimm_cli.Parsed) -> int | None:
    value = parsed.options.get("--n-mipmaps")
    if value is None:
        return None
    if not str(value).isdigit():
        raise Unmodelled(f"--n-mipmaps {value}")
    if int(str(value)) > MAX_MIPMAPS:
        message = f"Value of --n-mipmaps too large (must not >{MAX_MIPMAPS}): {value}"
        raise _refuse(108, "SEMANTIC ERROR", message)
    return int(str(value))


def _check_size(fmt: int, width: int, height: int) -> None:
    """A non-power-of-two PNG (48x40) was recorded only for RGB5A3 and CMPR."""
    square = math.log2(width).is_integer() and math.log2(height).is_integer()
    if not square and fmt not in (FORMATS["RGB5A3"], FORMATS["CMPR"]):
        raise Unmodelled("non-power-of-two image in an unrecorded format")


def _images(width: int, height: int, forced: int | None) -> int:
    """Forced: N mipmaps -> N+1 images. Default counts only for the recorded PNG sizes."""
    if forced is not None:
        return forced + 1
    if (width, height) not in DEFAULT_IMAGES:
        raise Unmodelled(f"default mipmaps for an unrecorded {width}x{height} image")
    return DEFAULT_IMAGES[width, height]


def encode(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    fw.allow(parsed, {"--dest", "--DEST", "--overwrite", "--transform", "--n-mipmaps"})
    name, forced = _format(parsed), _mipmaps(parsed)
    raw = fw.one_source(parsed)
    data = fw.read_source(tool, raw)
    if data[:8] != fw.PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise Unmodelled(f"{raw} is not a PNG")
    if (data[24], data[25]) != (8, 6):
        raise Unmodelled("only 8-bit RGBA PNGs were recorded")
    where = fw.target(parsed)
    if where.path.suffix != ".tex0":
        raise Unmodelled("image output other than TEX0")
    code = FORMATS[name]
    width, height = struct.unpack(">II", data[16:24])
    _check_size(code, width, height)
    header = (
        b"TEX0"
        + bytes(24)
        + struct.pack(">HHII", width, height, code, _images(width, height, forced))
    )
    line = f"ENCODE PNG:{fw.show(raw)} -> TEX.{name}:{fw.show(where.raw)}\n"
    overwrite = "--overwrite" in parsed.options
    return fw.write_one(
        tool, line, where, header + fw.FAKE_MARK, overwrite=overwrite, exit_on_block=True
    )
