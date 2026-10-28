"""Measured Wiimm cases for the P2-T05 adapters, kept out of the 400-line base table."""

from __future__ import annotations

from ops_cases import Case

_STAGE = ("@stage",)
_EMPTY = ("@empty_stage",)
_SZS = ("wszst", "create", "stage", "--dest", "t.szs")

CHECK_CASES: tuple[Case, ...] = (
    Case("check directory", ("wszst", "check", "stage"), (_STAGE,), "findings"),
    Case("check empty directory", ("wszst", "check", "empty"), (_EMPTY,), "findings"),
    Case(
        "check empty archive",
        ("wszst", "check", "empty.szs"),
        (_EMPTY, ("wszst", "create", "empty", "--dest", "empty.szs")),
        "findings",
    ),
)

# P2-T05b: ``analyze --json`` reports per-file analysis in one JSON object. The fake
# models only the directory/junk/missing rows; it never invents analysis of an archive.
ANALYZE_CASES: tuple[Case, ...] = (
    Case("analyze json", ("wszst", "analyze", "--json", "t.szs"), (_STAGE, _SZS), "unmodelled"),
    Case(
        "analyze json uncompressed",
        ("wszst", "analyze", "--json", "u.szs"),
        (_STAGE, ("wszst", "create", "stage", "--dest", "u.szs", "--no-compress")),
        "unmodelled",
    ),
    Case(
        "analyze json empty archive",
        ("wszst", "analyze", "--json", "empty.szs"),
        (_EMPTY, ("wszst", "create", "empty", "--dest", "empty.szs")),
        "unmodelled",
    ),
    Case("analyze json directory", ("wszst", "analyze", "--json", "stage"), (_STAGE,)),
    Case("analyze json empty directory", ("wszst", "analyze", "--json", "empty"), (_EMPTY,)),
    Case("analyze json junk", ("wszst", "analyze", "--json", "junk.szs"), (("@junk", "junk.szs"),)),
    Case("analyze json missing", ("wszst", "analyze", "--json", "missing.szs")),
)

# P2-T05c: image formats and mipmap counts the adapter exposes, plus KMP text faults that
# wkmpt accepts with exit 0 (a script error is only a stderr line; an unknown section is
# silent). The fake cannot parse KMP text, so it refuses those texts.
KMP_TEXTS = {
    "script_error.txt": "#KMP\n[KTPT]\nbogus line here\n",
    "unknown_section.txt": "#KMP\n[NOSUCH]\n1 2 3\n",
}
IMG_FORMATS = ("CMPR", "I4", "I8", "IA4", "IA8", "RGB565", "RGB5A3", "RGBA32")


def _img(name: str, *args: str, png: str = "road.png") -> Case:
    argv = ("wimgt", "encode", png, *args, "--dest", "t.tex0")
    return Case(name, argv, (("@texture", png),))


ENCODE_CASES: tuple[Case, ...] = (
    *(_img(f"img encode {fmt}", "-x", f"TEX.{fmt}") for fmt in IMG_FORMATS),
    _img("img encode no mipmaps", "--n-mipmaps", "0"),
    _img("img encode 2 mipmaps", "--n-mipmaps", "2"),
    _img("img encode CMPR 2 mipmaps", "-x", "TEX.CMPR", "--n-mipmaps", "2"),
    _img("img encode npot CMPR", "-x", "TEX.CMPR", png="bad_npot.png"),
    _img("img encode bad format", "-x", "TEX.BOGUS"),
    _img("img encode too many mipmaps", "--n-mipmaps", "21"),
    *(
        Case(
            f"kmp encode {name.removesuffix('.txt').replace('_', ' ')}",
            ("wkmpt", "encode", name, "--dest", "k.kmp"),
            (("@kmptext", name),),
            "unmodelled",
        )
        for name in KMP_TEXTS
    ),
)
