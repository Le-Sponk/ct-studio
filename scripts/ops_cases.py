"""The real-tool operation cases recorded by ``scripts/record_tool_outputs.py``.

Each case runs in a fresh work folder: ``setup`` steps first (``@`` steps place fixture
files, other steps run a tool), then ``argv``. The tests replay the same cases against the
fakes, so these tables are the fakes' specification. ``compare`` says how much of stdout a
fake must reproduce: ``exact``; ``prefix``, where the real tool goes on to print findings
from analysing file contents (KMP/KCL checks) that a fake cannot compute, so the fake prints
only the real opening lines; or ``findings``, which is ``prefix`` where the exit code also
reflects those findings (``wszst check`` exits 2 on warnings) and is therefore not compared;
or ``unmodelled``: kept as evidence of what the real tool does, but the fake refuses it
(exit 121) because one sample does not pin down the rule.

``native_only`` cases depend on how one OS build treats a path (rszst reads argv through
the Windows ANSI code page): a fake models them only for recordings from its own OS.
"""

from __future__ import annotations

from dataclasses import dataclass

WIIMM = ("wszst", "wkclt", "wkmpt", "wimgt")


@dataclass(frozen=True)
class Case:
    name: str
    argv: tuple[str, ...]  # tool name first
    setup: tuple[tuple[str, ...], ...] = ()  # ("tool", args...) or ("@sentinel", path), ...
    compare: str = "exact"
    native_only: bool = False
    without_wimgt: bool = False  # ABMatt's import path when its image converter is absent


_STAGE = ("@stage",)
_SZS = ("wszst", "create", "stage", "--dest", "t.szs")
_KMP_TXT = ("wkmpt", "decode", "stage/course.kmp", "--dest", "k.txt")
WIIMM_CASES: tuple[Case, ...] = (
    *(Case(f"{tool} version", (tool, "version")) for tool in WIIMM),
    Case("create", ("wszst", "create", "stage", "--dest", "t.szs"), (_STAGE,)),
    Case("create default dest", ("wszst", "create", "stage"), (_STAGE,)),
    Case(
        "create uncompressed",
        ("wszst", "create", "stage", "--dest", "u.szs", "--no-compress"),
        (_STAGE,),
    ),
    Case(
        "create fast",
        ("wszst", "create", "stage", "--dest", "t.szs", "--fast", "--overwrite"),
        (_STAGE,),
    ),
    Case("create keeps existing", _SZS, (_STAGE, ("@sentinel", "t.szs"))),
    Case("create -o replaces", (*_SZS, "-o"), (_STAGE, ("@sentinel", "t.szs"))),
    Case(
        "create compr template",
        (*_SZS, "--overwrite", "--compr=9"),
        (_STAGE, ("@sentinel", "t.szs")),
    ),
    Case("create no folder", ("wszst", "create", "stage", "--dest", "sub/t.szs"), (_STAGE,)),
    Case("create -D makes folder", ("wszst", "create", "stage", "-D", "sub/t.szs"), (_STAGE,)),
    Case("create missing source", ("wszst", "create", "nodir", "--dest", "t.szs")),
    Case("create unknown long flag", (*_SZS, "--bogus-flag"), (_STAGE,)),
    Case("create unknown short flag", (*_SZS, "-Z"), (_STAGE,)),
    Case("create foreign flag", (*_SZS, "--brief"), (_STAGE,)),
    Case("create foreign long-only flag", (*_SZS, "--touch"), (_STAGE,)),
    Case(
        "create absolute paths",
        ("wszst", "create", "{work}{sep}stage", "--dest", "{work}{sep}a.szs"),
        (_STAGE,),
    ),
    Case(
        "kcl decode no folder",
        ("wkclt", "decode", "stage/course.kcl", "--dest", "sub/c.obj"),
        (_STAGE,),
        "prefix",
    ),
    Case(
        "kcl decode -D makes folder",
        ("wkclt", "decode", "stage/course.kcl", "-D", "sub/c.obj"),
        (_STAGE,),
        "prefix",
    ),
    Case(
        "kmp decode no folder",
        ("wkmpt", "decode", "stage/course.kmp", "--dest", "sub/k.txt"),
        (_STAGE,),
        "prefix",
    ),
    Case("kcl unknown flag", ("wkclt", "decode", "x.kcl", "--bogus-flag")),
    Case("kmp unknown flag", ("wkmpt", "decode", "x.kmp", "--bogus-flag")),
    Case("img unknown flag", ("wimgt", "encode", "x.png", "--bogus-flag")),
    Case("unknown command", ("wszst", "frobnicate")),
    Case("list", ("wszst", "list", "t.szs"), (_STAGE, _SZS)),
    Case("list long", ("wszst", "list", "--long", "t.szs"), (_STAGE, _SZS)),
    Case("list missing", ("wszst", "list", "missing.szs")),
    Case("check", ("wszst", "check", "t.szs"), (_STAGE, _SZS), "findings"),
    Case("check brief", ("wszst", "check", "--brief", "t.szs"), (_STAGE, _SZS), "findings"),
    Case(
        "check brief after file", ("wszst", "check", "t.szs", "--brief"), (_STAGE, _SZS), "findings"
    ),
    Case("check missing", ("wszst", "check", "missing.szs")),
    Case("check junk", ("wszst", "check", "junk.szs"), (("@junk", "junk.szs"),)),
    Case("minimap auto", ("wszst", "minimap", "--auto", "t.szs"), (_STAGE, _SZS)),
    Case(
        "kcl decode",
        ("wkclt", "decode", "stage/course.kcl", "--dest", "c.obj"),
        (_STAGE,),
        "prefix",
    ),
    Case(
        "kcl decode exists",
        ("wkclt", "decode", "stage/course.kcl", "--dest", "c.obj"),
        (_STAGE, ("@sentinel", "c.obj")),
        "prefix",
    ),
    Case("kcl decode missing", ("wkclt", "decode", "missing.kcl", "--dest", "c.obj")),
    Case(
        "kcl decode -o replaces",
        ("wkclt", "decode", "stage/course.kcl", "--dest", "c.obj", "--overwrite"),
        (_STAGE, ("@sentinel", "c.obj")),
        "prefix",
    ),
    Case(
        "kmp decode template",
        (*_KMP_TXT, "--overwrite", "--brief"),
        (_STAGE, ("@sentinel", "k.txt")),
        "prefix",
    ),
    Case(
        "kmp encode template",
        ("wkmpt", "encode", "k.txt", "--dest", "k.kmp", "--overwrite"),
        (_STAGE, _KMP_TXT, ("@sentinel", "k.kmp")),
        "prefix",
    ),
    Case(
        "img encode -o replaces",
        ("wimgt", "encode", "road.png", "--dest", "road.tex0", "--overwrite"),
        (("@texture", "road.png"), ("@sentinel", "road.tex0")),
    ),
    Case("kmp decode", _KMP_TXT, (_STAGE,), "prefix"),
    Case("kmp decode default dest", ("wkmpt", "decode", "stage/course.kmp"), (_STAGE,), "prefix"),
    Case("kmp decode exists", _KMP_TXT, (_STAGE, ("@sentinel", "k.txt")), "prefix"),
    Case(
        "kmp decode not kmp",
        ("wkmpt", "decode", "bad.kmp", "--dest", "k.txt"),
        (("@junk", "bad.kmp"),),
    ),
    Case("kmp decode missing", ("wkmpt", "decode", "missing.kmp", "--dest", "k.txt")),
    Case(
        "kmp encode", ("wkmpt", "encode", "k.txt", "--dest", "k.kmp"), (_STAGE, _KMP_TXT), "prefix"
    ),
    Case(
        "kmp encode overwrites",
        ("wkmpt", "encode", "k.txt", "--dest", "k.kmp"),
        (_STAGE, _KMP_TXT, ("@sentinel", "k.kmp")),
        "prefix",
    ),
    Case(
        "kmp encode no folder",
        ("wkmpt", "encode", "k.txt", "--dest", "sub/k.kmp"),
        (_STAGE, _KMP_TXT),
        "prefix",
    ),
    Case(
        "kmp encode not kmp",
        ("wkmpt", "encode", "bad.txt", "--dest", "k.kmp"),
        (("@junk", "bad.txt"),),
    ),
    Case("kmp encode missing", ("wkmpt", "encode", "missing.txt", "--dest", "k.kmp")),
    Case(
        "img encode",
        ("wimgt", "encode", "road.png", "--dest", "road.tex0"),
        (("@texture", "road.png"),),
    ),
    Case(
        "img encode npot",
        ("wimgt", "encode", "bad_npot.png", "--dest", "n.tex0"),
        (("@texture", "bad_npot.png"),),
    ),
    Case(
        "img encode exists",
        ("wimgt", "encode", "road.png", "--dest", "road.tex0"),
        (("@texture", "road.png"), ("@sentinel", "road.tex0")),
    ),
    Case(
        "img encode no folder",
        ("wimgt", "encode", "road.png", "--dest", "sub/r.tex0"),
        (("@texture", "road.png"),),
    ),
    Case("img encode missing", ("wimgt", "encode", "missing.png", "--dest", "m.tex0")),
)


# --- rszst 5.11.5 (P2-T04c) -----------------------------------------------------------------
# "@dae" places the fixture course.dae with its four textures. Bare names throughout: rszst
# cannot open a non-ASCII absolute path on Windows (TOOLS.md, P0-T13) and the work folder
# has an "é" on purpose; "import absolute paths" records that failure.
_DAE = ("@dae",)
_IMPORT = ("rszst", "import-brres", "course.dae", "out.brres")
_TO_JSON = ("rszst", "brres-to-json", "out.brres", "out.json")
RSZST_CASES: tuple[Case, ...] = (
    Case("import", _IMPORT, (_DAE,)),
    Case("import existing", _IMPORT, (_DAE, ("@sentinel", "out.brres"))),
    Case("import default dest", ("rszst", "import-brres", "course.dae"), (_DAE,)),
    Case("import model name", (*_IMPORT, "--model-name", "vrcorn"), (_DAE,)),
    Case("import mipmaps", (*_IMPORT, "--mipmaps", "--min-mip", "64"), (_DAE,)),
    Case("import missing", ("rszst", "import-brres", "missing.dae", "x.brres")),
    Case("import junk", ("rszst", "import-brres", "junk.dae", "j.brres"), (("@junk", "junk.dae"),)),
    Case("import no folder", ("rszst", "import-brres", "course.dae", "sub/x.brres"), (_DAE,)),
    Case(
        "import presets",
        ("rszst", "import-brres", "course.dae", "pre.brres", "--preset-path", "presets"),
        (_DAE, _IMPORT, ("rszst", "dump-presets", "out.brres", "presets")),
    ),
    Case("import presets missing", (*_IMPORT, "--preset-path", "nothere"), (_DAE,)),
    Case(
        "import absolute paths",
        ("rszst", "import-brres", "{work}{sep}course.dae", "{work}{sep}abs.brres"),
        (_DAE,),
        native_only=True,
    ),
    Case("import unknown flag", (*_IMPORT, "--bogus-flag"), (_DAE,)),
    Case("import misspelt flag", (*_IMPORT, "--model-na", "v"), (_DAE,)),
    Case("import value missing", (*_IMPORT, "--model-name"), (_DAE,)),
    Case("import misspelt short suggestion", (*_IMPORT, "--x", "1"), (_DAE,)),
    Case("import unknown flag first", ("rszst", "import-brres", "--bogus-flag", "course.dae")),
    Case("import unknown flag after source", ("rszst", "import-brres", "course.dae", "--nametag")),
    Case("import unknown short", (*_IMPORT, "-z"), (_DAE,)),
    Case("import extra positional", (*_IMPORT, "extra"), (_DAE,)),
    Case("import repeated option", (*_IMPORT, "--model-name", "a", "--model-name", "b"), (_DAE,)),
    Case("import bad number", (*_IMPORT, "--min-mip", "abc"), (_DAE,)),
    Case("import equals value", (*_IMPORT, "--model-name=vrcorn"), (_DAE,)),
    Case("import no source", ("rszst", "import-brres")),
    Case("to json unknown flag", (*_TO_JSON, "--bogus-flag"), (_DAE, _IMPORT)),
    Case("unknown subcommand", ("rszst", "IMPORT-BRRES", "course.dae", "x.brres"), (_DAE,)),
    Case("to json", _TO_JSON, (_DAE, _IMPORT)),
    Case("to json default dest", ("rszst", "brres-to-json", "out.brres"), (_DAE, _IMPORT)),
    Case("to json existing", _TO_JSON, (_DAE, _IMPORT, ("@sentinel", "out.json"))),
    Case("to json missing", ("rszst", "brres-to-json", "missing.brres", "m.json")),
    Case(
        "to json junk",
        ("rszst", "brres-to-json", "j.brres", "j.json"),
        (("@junk", "j.brres"),),
        "unmodelled",  # the message hex-dumps the bytes at the failing offset
    ),
    Case(
        "to json no folder", ("rszst", "brres-to-json", "out.brres", "sub/o.json"), (_DAE, _IMPORT)
    ),
    Case(
        "from json",
        ("rszst", "json-to-brres", "out.json", "back.brres"),
        (_DAE, _IMPORT, _TO_JSON),
    ),
    Case("from json missing", ("rszst", "json-to-brres", "missing.json", "b.brres")),
    Case(
        "from json without bin",
        ("rszst", "json-to-brres", "j.json", "b.brres"),
        (("@junk", "j.json"),),
    ),
    Case("dump presets", ("rszst", "dump-presets", "out.brres", "presets"), (_DAE, _IMPORT)),
    Case("dump presets default dest", ("rszst", "dump-presets", "out.brres"), (_DAE, _IMPORT)),
    Case(
        "dump presets existing folder",
        ("rszst", "dump-presets", "out.brres", "full"),
        (_DAE, _IMPORT, ("@sentinel", "full/road.rspreset"), ("@sentinel", "full/keep.txt")),
    ),
    Case(
        "dump presets onto a file",
        ("rszst", "dump-presets", "out.brres", "afile"),
        (_DAE, _IMPORT, ("@sentinel", "afile")),
    ),
    Case("dump presets missing", ("rszst", "dump-presets", "missing.brres", "p")),
)

# --- ABMatt 1.3.2 (P2-T04d) --------------------------------------------------------------
_AB_DAE = ("@dae",)
_AB_OBJ = ("@abobj",)
_AB_CONVERT = ("abmatt", "convert", "course.dae", "to", "course_model.brres", "-o")
_AB_SOURCE = (_AB_DAE, ("rszst", "import-brres", "course.dae", "source.brres"))
_AB_INFO = ("abmatt", "-b", "source.brres", "-c", "info")
_AB_FILE = ("abmatt", "-b", "source.brres", "-f", "set.txt", "-o")
ABMATT_CASES: tuple[Case, ...] = (
    Case("usage", ("abmatt",)),
    Case("unknown option", ("abmatt", "--bogus-flag")),
    Case("unknown short option", ("abmatt", "-z")),
    Case("option missing value", ("abmatt", "-b")),
    Case("convert dae", _AB_CONVERT, (_AB_DAE,)),
    Case("convert dae without overwrite", _AB_CONVERT[:-1], (_AB_DAE,)),
    Case(
        "convert existing without overwrite",
        _AB_CONVERT[:-1],
        (_AB_DAE, ("@sentinel", "course_model.brres")),
    ),
    Case("convert existing overwrite", _AB_CONVERT, (_AB_DAE, ("@sentinel", "course_model.brres"))),
    Case("convert valid existing without overwrite", _AB_CONVERT[:-1], (_AB_DAE, _AB_CONVERT)),
    Case("convert valid existing overwrite", _AB_CONVERT, (_AB_DAE, _AB_CONVERT)),
    Case("convert without wimgt", _AB_CONVERT, (_AB_DAE,), without_wimgt=True),
    Case("convert missing dae", ("abmatt", "convert", "missing.dae", "to", "missing.brres", "-o")),
    Case(
        "convert junk dae",
        ("abmatt", "convert", "junk.dae", "to", "junk.brres", "-o"),
        (("@junk", "junk.dae"),),
        "unmodelled",
    ),
    Case(
        "convert no folder",
        ("abmatt", "convert", "course.dae", "to", "sub/course.brres", "-o"),
        (_AB_DAE,),
    ),
    Case(
        "convert obj map",
        ("abmatt", "convert", "map.obj", "to", "map_model.brres", "-o"),
        (_AB_OBJ,),
    ),
    Case(
        "convert obj plain", ("abmatt", "convert", "map.obj", "to", "map.brres", "-o"), (_AB_OBJ,)
    ),
    Case(
        "convert missing obj", ("abmatt", "convert", "missing.obj", "to", "map_model.brres", "-o")
    ),
    Case("info", _AB_INFO, _AB_SOURCE),
    Case("info missing", ("abmatt", "-b", "missing.brres", "-c", "info")),
    Case("info quiet", (*_AB_INFO, "-l", "0"), _AB_SOURCE),
    Case("command file", _AB_FILE, (*_AB_SOURCE, ("@abcmd", "set.txt"))),
    Case("command file without overwrite", _AB_FILE[:-1], (*_AB_SOURCE, ("@abcmd", "set.txt"))),
    Case(
        "command file missing",
        ("abmatt", "-b", "source.brres", "-f", "missing.txt", "-o"),
        _AB_SOURCE,
    ),
    Case(
        "bad command file",
        ("abmatt", "-b", "source.brres", "-f", "bad.txt", "-o"),
        (*_AB_SOURCE, ("@abcmd", "bad.txt")),
    ),
    Case(
        "inline command parsing",
        ("abmatt", "-b", "source.brres", "-o", "-c", "set material xlu:true for *"),
        _AB_SOURCE,
    ),
    Case(
        "copy material",
        ("abmatt", "-b", "source.brres", "-b", "dest.brres", "-f", "copy.txt", "-o"),
        (*_AB_SOURCE, ("@copyfile", "source.brres", "dest.brres"), ("@abcmd", "copy.txt")),
    ),
)

# --- Blender 5.2.2 (P2-T04e) --------------------------------------------------------------
_BL = ("blender", "-b", "--factory-startup")
BLENDER_CASES: tuple[Case, ...] = (
    Case("background idle", _BL),
    Case("script args", (*_BL, "--python", "ok.py", "--", "a b", "é"), (("@blscript", "ok.py"),)),
    Case(
        "absolute script",
        (*_BL, "--python", "{work}{sep}ok.py", "--", "x"),
        (("@blscript", "ok.py"),),
    ),
    Case(
        "script with unicode path",
        (*_BL, "--python", "script é.py"),
        (("@blscript", "script é.py"),),
    ),
    Case("script writes", (*_BL, "--python", "write.py"), (("@blscript", "write.py"),)),
    Case("script exception", (*_BL, "--python", "boom.py"), (("@blscript", "boom.py"),)),
    Case(
        "script exception exit 7",
        (*_BL[:2], "--python-exit-code", "7", "--factory-startup", "--python", "boom.py"),
        (("@blscript", "boom.py"),),
    ),
    Case("script exits 3", (*_BL, "--python", "quit3.py"), (("@blscript", "quit3.py"),)),
    Case("missing script", (*_BL, "--python", "missing.py")),
    Case("missing script exit 7", (*_BL, "--python-exit-code", "7", "--python", "missing.py")),
    Case(
        "valid blend",
        ("blender", "-b", "good.blend", "--factory-startup", "--python", "ok.py", "--", "x"),
        (("@blend",), ("@blscript", "ok.py")),
    ),
    Case(
        "missing blend",
        ("blender", "-b", "missing.blend", "--factory-startup", "--python", "ok.py"),
        (("@blscript", "ok.py"),),
    ),
    Case(
        "junk blend",
        ("blender", "-b", "junk.blend", "--factory-startup", "--python", "ok.py"),
        (("@junk", "junk.blend"), ("@blscript", "ok.py")),
    ),
    Case("unknown option", ("blender", "--bogus-flag", "-b")),
    Case(
        "bpy only in real Blender",
        (*_BL, "--python", "bpy.py"),
        (("@blscript", "bpy.py"),),
        "bpy_missing",
    ),
    Case(
        "bpy missing exit 7",
        (*_BL, "--python-exit-code", "7", "--python", "bpy.py"),
        (("@blscript", "bpy.py"),),
        "bpy_missing",
    ),
)
