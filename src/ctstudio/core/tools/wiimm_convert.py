"""Typed Wiimm conversions (P2-T05c): KMP text <-> binary and PNG -> TEX0 encoding.

Every writer refuses an existing destination itself (``wkmpt encode`` overwrites without
``--overwrite``), raises on any ``ERROR #`` or ``!`` script diagnostic even at exit 0, and
then verifies the written file rather than trusting the exit status.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from ctstudio.core.tools.process import CancelToken, Stream, run
from ctstudio.core.tools.wiimm import ERROR_LINE, WiimmError, executable_for

ImageFormat = Literal["CMPR", "I4", "I8", "IA4", "IA8", "RGB565", "RGB5A3", "RGBA32"]
# TEX0 header format codes, measured from wimgt 2.42a output (P2-T05c recordings).
TEX0_FORMAT = {
    "I4": 0,
    "I8": 1,
    "IA4": 2,
    "IA8": 3,
    "RGB565": 4,
    "RGB5A3": 5,
    "RGBA32": 6,
    "CMPR": 14,
}
MAX_MIPMAPS = 20  # wimgt rejects --n-mipmaps above 20 (ERROR #108)
_SCRIPT_ERROR = re.compile(r"(?m)^! \w+: (.+)$")  # wkmpt reports text errors this way, exit 0


@dataclass(frozen=True)
class Tex0:
    path: Path
    width: int
    height: int
    format: int
    images: int  # base image plus mipmaps


def _write(
    tool: str,
    args: list[str],
    source: Path,
    dest: Path,
    *,
    overwrite: bool,
    executable: Path | None,
    timeout: float,
    cancel: CancelToken | None,
) -> None:
    """Run a Wiimm writer from the source folder; fail unless it (re)wrote ``dest``."""
    if dest.exists() and not overwrite:
        raise WiimmError(
            dest, 0, f"{dest.name} already exists (not run)", error_code=None, details=""
        )
    before = dest.stat().st_mtime_ns if dest.exists() else None
    lines: dict[Stream, list[str]] = {"stdout": [], "stderr": []}
    result = run(
        [
            executable_for(tool, executable),
            *args,
            "--dest",
            str(dest),
            *(["--overwrite"] * overwrite),
        ],
        cwd=source.parent,
        timeout=timeout,
        cancel=cancel,
        on_line=lambda stream, line: lines[stream].append(line),
        check=False,
    )
    stdout, stderr = "\n".join(lines["stdout"]), "\n".join(lines["stderr"])
    details = stderr or stdout
    if match := ERROR_LINE.search(f"{stderr}\n{stdout}"):
        reason = f"ERROR #{match.group(1)} [{match.group(2)}]"
        raise WiimmError(
            source, result.exit_code, reason, error_code=int(match.group(1)), details=details
        )
    if match := _SCRIPT_ERROR.search(stderr):
        raise WiimmError(source, result.exit_code, match.group(1), error_code=None, details=details)
    if result.exit_code != 0 or not dest.is_file() or dest.stat().st_mtime_ns == before:
        reason = f"tool exited {result.exit_code} without writing {dest.name}"
        raise WiimmError(source, result.exit_code, reason, error_code=None, details=details)


def _require_magic(dest: Path, magic: bytes, what: str) -> bytes:
    data = dest.read_bytes()
    if not data.startswith(magic):
        raise WiimmError(dest, 0, f"{dest.name} is not {what}", error_code=None, details="")
    return data


def kmp_to_text(
    kmp: Path,
    dest: Path,
    *,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> Path:
    """Decode a binary KMP to Wiimm's ``#KMP`` text format."""
    kmp, dest = Path(kmp).resolve(), Path(dest).resolve()
    args = ["decode", kmp.name]
    _write(
        "wkmpt",
        args,
        kmp,
        dest,
        overwrite=overwrite,
        executable=executable,
        timeout=timeout,
        cancel=cancel,
    )
    _require_magic(dest, b"#KMP", "KMP text")
    return dest


def kmp_from_text(
    text: Path,
    dest: Path,
    *,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> Path:
    """Encode ``#KMP`` text to a binary KMP; script errors on stderr fail even at exit 0.

    wkmpt does not reject unknown sections or incomplete courses; run ``check`` on the
    built track for those findings.
    """
    text, dest = Path(text).resolve(), Path(dest).resolve()
    args = ["encode", text.name]
    _write(
        "wkmpt",
        args,
        text,
        dest,
        overwrite=overwrite,
        executable=executable,
        timeout=timeout,
        cancel=cancel,
    )
    _require_magic(dest, b"RKMD", "KMP")
    return dest


def img_encode(
    png: Path,
    dest: Path,
    format: ImageFormat,
    *,
    mipmaps: int | None = None,
    overwrite: bool = False,
    executable: Path | None = None,
    timeout: float = 120,
    cancel: CancelToken | None = None,
) -> Tex0:
    """Encode a PNG to TEX0 in ``format``; ``mipmaps`` forces that many (else wimgt's default).

    The written header must report the requested format; the result reports the real
    size and image count, since wimgt decides those.
    """
    if format not in get_args(ImageFormat):
        raise ValueError(f"unsupported image format {format!r}")
    if mipmaps is not None and not 0 <= mipmaps <= MAX_MIPMAPS:
        raise ValueError(f"mipmaps must be 0..{MAX_MIPMAPS}, not {mipmaps}")
    png, dest = Path(png).resolve(), Path(dest).resolve()
    args = ["encode", png.name, "-x", f"TEX.{format}"]
    if mipmaps is not None:
        args += ["--n-mipmaps", str(mipmaps)]
    _write(
        "wimgt",
        args,
        png,
        dest,
        overwrite=overwrite,
        executable=executable,
        timeout=timeout,
        cancel=cancel,
    )
    data = _require_magic(dest, b"TEX0", "TEX0")
    if len(data) < 0x28:
        raise WiimmError(dest, 0, "TEX0 header is truncated", error_code=None, details="")
    width, height, code, images = struct.unpack(">HHII", data[0x1C:0x28])
    if code != TEX0_FORMAT[format]:
        raise WiimmError(
            dest, 0, f"TEX0 format {code} is not {format}", error_code=None, details=""
        )
    if mipmaps is not None and images != mipmaps + 1:
        raise WiimmError(
            dest, 0, f"TEX0 has {images} images, not {mipmaps + 1}", error_code=None, details=""
        )
    return Tex0(dest, width, height, code, images)
