"""Record real Wiimm operations on the generated fixtures for the fakes (P2-T04b).

Run after ``scripts/bootstrap_tools.py`` and ``scripts/fixtures/make_fixtures.py``::

    uv run python scripts/record_tool_outputs.py

Every case runs in a fresh work folder: copy fixtures, run setup commands with the same
tools, snapshot the files, run the case through the core runner, then record output and
which files were created, changed or deleted (with their first four bytes). The work
folder becomes ``<work>`` in the recording. ``tests/unit/test_fake_wiimm.py`` replays the
same cases against the fakes, so the case table here is the fakes' specification.

``compare`` says how much of stdout a fake must reproduce: ``exact``; ``prefix``, where the
real tool goes on to print findings from analysing file contents (KMP/KCL checks) that a
fake cannot compute, so the fake prints only the real opening lines; or ``findings``, which
is ``prefix`` where the exit code also reflects those findings (``wszst check`` exits 2 on
warnings) and is therefore not compared.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import record_tool_help as rth
import tool_paths as tp

FIXTURES = tp.REPO_ROOT / "tests" / "fixtures" / "generated"
WORK = "<work>"
WIIMM = ("wszst", "wkclt", "wkmpt", "wimgt")
Resolve = Callable[[str], Path]
Fixture = Callable[[str], bytes]  # "course.kcl", "textures/road.png" -> file contents


@dataclass(frozen=True)
class Case:
    name: str
    argv: tuple[str, ...]  # tool name first
    setup: tuple[tuple[str, ...], ...] = ()  # ("tool", args...) or ("@sentinel", path), ...
    compare: str = "exact"


_STAGE = ("@stage",)
_SZS = ("wszst", "create", "stage", "--dest", "t.szs")
_KMP_TXT = ("wkmpt", "decode", "stage/course.kmp", "--dest", "k.txt")
CASES: tuple[Case, ...] = (
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


def prepare(case: Case, work: Path, resolve: Resolve, fixture: Fixture) -> None:
    """Create the case's inputs in ``work``; tool steps use ``resolve``, files ``fixture``."""
    for step in case.setup:
        action, *args = step
        if action == "@stage":
            (work / "stage").mkdir()
            for name in ("course.kcl", "course.kmp"):
                (work / "stage" / name).write_bytes(fixture(name))
        elif action == "@sentinel":
            (work / args[0]).write_bytes(b"SENTINEL")
        elif action == "@junk":
            (work / args[0]).write_bytes(b"not a track file\n" * 4)
        elif action == "@texture":
            (work / args[0]).write_bytes(fixture(f"textures/{args[0]}"))
        else:
            rth.capture(resolve(action), expand(args, work), cwd=work, roots={})


def expand(args: Sequence[str], work: Path) -> list[str]:
    """``{work}`` is the case folder's absolute path and ``{sep}`` the OS separator."""
    return [arg.replace("{work}", str(work)).replace("{sep}", os.sep) for arg in args]


def snapshot(work: Path) -> dict[str, str]:
    return {
        path.relative_to(work).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(work.rglob("*"))
        if path.is_file()
    }


def file_effects(work: Path, before: Mapping[str, str]) -> dict[str, dict[str, str]]:
    after = snapshot(work)
    effects: dict[str, dict[str, str]] = {}
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        if name not in after:
            effects[name] = {"effect": "deleted"}
            continue
        effect = "created" if name not in before else "changed"
        effects[name] = {"effect": effect, "magic": (work / name).read_bytes()[:4].hex()}
    return effects


def run_case(case: Case, resolve: Resolve, root: Path, fixture: Fixture) -> dict[str, object]:
    """Run one case in a fresh folder under ``root``; record what it did to the files.

    ``inputs`` lists each fixture file the case used with its size and first 32 bytes, so
    the fakes' replay can rebuild stand-ins without Blender or the real tools.
    """
    work = Path(tempfile.mkdtemp(prefix="case ", dir=root))
    used: dict[str, dict[str, object]] = {}

    def tracked(name: str) -> bytes:
        data = fixture(name)
        used[name] = {"size": len(data), "head": data[:32].hex()}
        return data

    try:
        prepare(case, work, resolve, tracked)
        before = snapshot(work)
        tool, *args = case.argv
        record = rth.capture(resolve(tool), expand(args, work), cwd=work, roots={work: WORK})
        record["files"] = file_effects(work, before)
        return {"case": case.name, "tool": tool, "compare": case.compare, "inputs": used, **record}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def load(tool: str, version: str, platform_name: str = "windows") -> list[dict[str, object]]:
    path = rth.RECORDINGS / tool / version / f"{platform_name}-ops.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write(records: Sequence[dict[str, object]], version: str, platform_name: str) -> None:
    for tool in WIIMM:
        mine = [record for record in records if record["tool"] == tool]
        target = rth.RECORDINGS / tool / version / f"{platform_name}-ops.json"
        target.write_text(
            json.dumps(mine, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"{tool} {version}: {len(mine)} cases -> {target.relative_to(tp.REPO_ROOT)}")


def main() -> int:
    version = rth.pinned_version("wiimms-szs-tools", tp.TOOLS_DIR / "installed.json")
    if not (FIXTURES / "course.kmp").is_file():
        raise rth.RecordError("generate fixtures first: scripts/fixtures/make_fixtures.py")
    bin_dir = tp.TOOLS_DIR / "wiimms-szs-tools" / "bin"

    def resolve(tool: str) -> Path:
        return tp.exe(bin_dir / tool)

    with tempfile.TemporaryDirectory(prefix="ct ops é ") as root:
        records = [
            run_case(case, resolve, Path(root), lambda name: (FIXTURES / name).read_bytes())
            for case in CASES
        ]
    write(records, version, "windows" if sys.platform == "win32" else "linux")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
