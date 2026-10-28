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

# P2-T05c2: KCL analysis/flags and minimap patching. Inputs beyond the generated fixture
# are retained whole under recordings/<tool>/<version>/inputs: an ABMatt map BRRES (with
# posLD/posRU bones), the same model without bones, Wiimm's own patched result, and a KCL
# re-encoded with variant bits set. The fakes replay these only for identical bytes.
RETAINED = {
    "objects.kmp": "wszst",
    "map_model.brres": "wszst",
    "map_model_patched.brres": "wszst",
    "no_bones_model.brres": "wszst",
    "variant.kcl": "wkclt",
}


def _kcl(command: str, label: str, source: str, setup: tuple[tuple[str, ...], ...]) -> Case:
    return Case(f"kcl {command} {label}".strip(), ("wkclt", command, source), setup)


def _minimap(label: str, source: str, setup: tuple[tuple[str, ...], ...] = ()) -> Case:
    return Case(f"minimap auto {label}", ("wszst", "minimap", "--auto", source), setup)


_KCL_INPUTS = (
    ("", "stage/course.kcl", (_STAGE,)),
    ("variant", "variant.kcl", (("@retained", "variant.kcl"),)),
    ("junk", "junk.kcl", (("@junk", "junk.kcl"),)),
    ("missing", "missing.kcl", ()),
)
KCL_CASES: tuple[Case, ...] = (
    *(
        _kcl(command, label, source, setup)
        for command in ("analyze", "flags")
        for label, source, setup in _KCL_INPUTS
    ),
    _minimap("brres", "map_model.brres", (("@retained", "map_model.brres"),)),
    _minimap(
        "brres patched", "map_model_patched.brres", (("@retained", "map_model_patched.brres"),)
    ),
    _minimap("no bones", "no_bones_model.brres", (("@retained", "no_bones_model.brres"),)),
    _minimap("junk", "junk.brres", (("@junk", "junk.brres"),)),
    _minimap("missing", "missing.brres"),
)

# P2-T05d: auto-add with synthetic inputs only. ``@objstage`` is the fixture KCL with
# ``objects.kmp`` (one itembox object, 0x65); ``@synlib`` is a library folder holding a
# synthetic BRRES under the itembox name, which Wiimm lists as found but invalid; and
# ``_COURSE`` is a ``Course/`` folder whose ``beginner_course.szs`` is built from that
# stage plus the synthetic BRRES (``@stagebrres``). Nothing here is, or derives from,
# game content.
_OBJ = ("@objstage",)
_LIB = ("@synlib",)
_COURSE = (
    ("@objstage",),
    ("@stagebrres",),
    ("wszst", "create", "stage", "--DEST", "Course/beginner_course.szs"),
)
_AA = ("wszst", "autoadd")
AUTOADD_CASES: tuple[Case, ...] = (
    Case("autoadd status", _AA),
    Case("autoadd status dest", (*_AA, "--dest", "lib"), (_LIB,)),
    Case("autoadd verify synthetic", (*_AA, "--dest", "lib", "-vv"), (_LIB,)),
    Case("autoadd verify empty", (*_AA, "--dest", "empty", "-vv"), (_EMPTY,)),
    Case("autoadd verify missing", (*_AA, "--dest", "nolib", "-vv")),
    Case("autoadd build", (*_AA, "Course", "--DEST", "newlib"), _COURSE),
    Case(
        "autoadd build again",
        (*_AA, "Course", "--dest", "newlib"),
        (*_COURSE, (*_AA, "Course", "--DEST", "newlib")),
    ),
    Case("autoadd build empty source", (*_AA, "empty", "--DEST", "newlib"), (_EMPTY,)),
    Case("autoadd build missing source", (*_AA, "NoSuch", "--DEST", "newlib")),
    Case("autoadd build missing dest", (*_AA, "Course", "--dest", "nolib/x"), _COURSE),
    Case(
        "create auto-add",
        ("wszst", "create", "stage", "--dest", "a.szs", "--auto-add", "--autoadd-path", "lib"),
        (_OBJ, _LIB),
    ),
    Case(
        "create auto-add empty library",
        ("wszst", "create", "stage", "--dest", "a.szs", "--auto-add", "--autoadd-path", "empty"),
        (_OBJ, _EMPTY),
    ),
)
