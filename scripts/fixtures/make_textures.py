"""Generate the synthetic fixture textures as PNGs (P0-T03).

Pure stdlib (zlib + struct): Blender 5.2 ships numpy but no Pillow, and the fixtures must
be reproducible outside Blender too, so the PNG encoder lives here rather than depending
on either. Everything is deterministic: same inputs, byte-identical outputs.

Texture set mirrors the material cases the course model pipeline has to handle:
  road.png     opaque colour, power of two
  grass.png    opaque colour, power of two
  fence.png    binary alpha (alpha-test / cutout case)
  water.png    smooth alpha (translucent case)
  detail.png   grayscale (I8/IA8 candidate)
  sky.png      vertical gradient for the skybox
  bad_npot.png deliberately NOT a power of two, for warning tests
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# (name, width, height) - all powers of two except the deliberate bad variant.
TEXTURE_SIZES: dict[str, tuple[int, int]] = {
    "road": (64, 64),
    "grass": (64, 64),
    "fence": (32, 64),
    "water": (64, 64),
    "detail": (32, 32),
    "sky": (64, 64),
    "bad_npot": (48, 40),
}

# Texture that must trigger a "not a power of two" warning downstream.
NON_POWER_OF_TWO = "bad_npot"


def write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    """Write a non-interlaced 8-bit RGBA PNG.

    Deterministic: fixed zlib level and no timestamp chunks, so regenerating a fixture
    produces identical bytes and the cache key in TESTING_STRATEGY §3 stays stable.
    """
    if len(rgba) != width * height * 4:
        raise ValueError(f"{path.name}: expected {width * height * 4} bytes, got {len(rgba)}")

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0 (None) keeps the encoder trivial and stable
        raw.extend(rgba[y * stride : (y + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _checker(width: int, height: int, a: tuple[int, int, int], b: tuple[int, int, int]) -> bytes:
    """Opaque checkerboard; the 8 px cells make UV orientation obvious in a viewer."""
    out = bytearray()
    for y in range(height):
        for x in range(width):
            colour = a if ((x // 8) + (y // 8)) % 2 == 0 else b
            out.extend((*colour, 255))
    return bytes(out)


def _binary_alpha_stripes(width: int, height: int) -> bytes:
    """Fence: alpha is only ever 0 or 255, which is exactly the alpha-test case."""
    row = bytearray()
    for x in range(width):
        solid = (x % 16) < 10
        row.extend((190, 190, 200, 255) if solid else (0, 0, 0, 0))
    return bytes(row) * height  # vertical bars: every row is identical


def _gradient_alpha(width: int, height: int) -> bytes:
    """Water: partial alpha throughout, so it must be treated as translucent."""
    out = bytearray()
    for y in range(height):
        alpha = 80 + (110 * y) // max(height - 1, 1)
        for x in range(width):
            blue = 150 + (x * 40) // max(width - 1, 1)
            out.extend((40, 90, blue, alpha))
    return bytes(out)


def _grayscale(width: int, height: int) -> bytes:
    out = bytearray()
    for y in range(height):
        for x in range(width):
            value = (x * 255) // max(width - 1, 1)
            value = value if (y // 4) % 2 == 0 else 255 - value
            out.extend((value, value, value, 255))
    return bytes(out)


def _vertical_gradient(width: int, height: int) -> bytes:
    """Sky: dark at the bottom, bright at the top."""
    out = bytearray()
    for row in range(height):
        t = row / max(height - 1, 1)
        r = int(40 + 120 * (1 - t))
        g = int(70 + 130 * (1 - t))
        b = int(150 + 105 * (1 - t))
        for _ in range(width):
            out.extend((r, g, b, 255))
    return bytes(out)


def generate_textures(out_dir: Path) -> dict[str, Path]:
    """Write every fixture texture into out_dir; returns name -> path."""
    builders = {
        "road": lambda w, h: _checker(w, h, (70, 70, 76), (96, 96, 104)),
        "grass": lambda w, h: _checker(w, h, (54, 112, 46), (66, 132, 54)),
        "fence": _binary_alpha_stripes,
        "water": _gradient_alpha,
        "detail": _grayscale,
        "sky": _vertical_gradient,
        "bad_npot": lambda w, h: _checker(w, h, (200, 40, 40), (240, 200, 60)),
    }
    written: dict[str, Path] = {}
    for name, (width, height) in TEXTURE_SIZES.items():
        path = out_dir / f"{name}.png"
        write_png(path, width, height, builders[name](width, height))
        written[name] = path
    return written


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("textures")
    for name, path in sorted(generate_textures(target).items()):
        print(f"{name:10} {path} ({path.stat().st_size} bytes)")
