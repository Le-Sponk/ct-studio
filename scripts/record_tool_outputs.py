"""Record real tool operations on the generated fixtures for the fakes (P2-T04b, P2-T04c).

Run after ``scripts/bootstrap_tools.py`` and ``scripts/fixtures/make_fixtures.py``::

    uv run python scripts/record_tool_outputs.py [--only wiimms-szs-tools|riistudio]

Every case (``scripts/ops_cases.py``) runs in a fresh work folder: copy fixtures, run setup
commands with the same tools, snapshot the files, run the case through the core runner, then
record output and which files were created, changed or deleted (with their first four
bytes). The work folder becomes ``<work>`` in the recording. The ``tests/unit/test_fake_*``
modules replay the same cases against the fakes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import record_tool_help as rth
import tool_paths as tp
from ops_cases import RSZST_CASES, WIIMM, WIIMM_CASES, Case

FIXTURES = tp.REPO_ROOT / "tests" / "fixtures" / "generated"
WORK = "<work>"
Resolve = Callable[[str], Path]
Fixture = Callable[[str], bytes]  # "course.kcl", "textures/road.png" -> file contents
DAE_TEXTURES = ("road.png", "grass.png", "fence.png", "water.png")  # copied beside course.dae
# What to record, by bootstrap tool name: its executables and its case table.
TOOLSETS: dict[str, tuple[tuple[str, ...], tuple[Case, ...]]] = {
    "wiimms-szs-tools": (WIIMM, WIIMM_CASES),
    "riistudio": (("rszst",), RSZST_CASES),
}


def prepare(case: Case, work: Path, resolve: Resolve, fixture: Fixture) -> None:
    """Create the case's inputs in ``work``; tool steps use ``resolve``, files ``fixture``."""
    for step in case.setup:
        action, *args = step
        if action == "@stage":
            (work / "stage").mkdir()
            for name in ("course.kcl", "course.kmp"):
                (work / "stage" / name).write_bytes(fixture(name))
        elif action == "@dae":
            for name in ("course.dae", *DAE_TEXTURES):
                (work / name).write_bytes(fixture(name))
        elif action == "@sentinel":
            (work / args[0]).parent.mkdir(parents=True, exist_ok=True)
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


def write(
    records: Sequence[dict[str, object]], tools: Sequence[str], version: str, platform_name: str
) -> None:
    for tool in tools:
        mine = [record for record in records if record["tool"] == tool]
        target = rth.RECORDINGS / tool / version / f"{platform_name}-ops.json"
        target.write_text(
            json.dumps(mine, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"{tool} {version}: {len(mine)} cases -> {target.relative_to(tp.REPO_ROOT)}")


def resolver(toolset: str) -> Resolve:
    if toolset == "riistudio":
        return lambda _tool: tp.RSZST
    bin_dir = tp.TOOLS_DIR / "wiimms-szs-tools" / "bin"
    return lambda tool: tp.exe(bin_dir / tool)


def record(toolset: str) -> None:
    tools, cases = TOOLSETS[toolset]
    version = rth.pinned_version(toolset, tp.TOOLS_DIR / "installed.json")
    needed = "course.dae" if toolset == "riistudio" else "course.kmp"
    if not (FIXTURES / needed).is_file():
        raise rth.RecordError("generate fixtures first: scripts/fixtures/make_fixtures.py")
    fixture = lambda name: (FIXTURES / name).read_bytes()  # noqa: E731
    with tempfile.TemporaryDirectory(prefix="ct ops é ") as root:
        records = [run_case(case, resolver(toolset), Path(root), fixture) for case in cases]
    write(records, tools, version, "windows" if sys.platform == "win32" else "linux")
    if toolset == "riistudio":
        # The rszst fake accepts only the exact fixture DAE and its four textures.
        inputs = rth.RECORDINGS / "rszst" / version / "inputs"
        inputs.mkdir(exist_ok=True)
        for name in ("course.dae", *DAE_TEXTURES):
            (inputs / name).write_bytes((FIXTURES / name).read_bytes())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record real external-tool operation outputs")
    parser.add_argument("--only", action="append", choices=sorted(TOOLSETS))
    for toolset in parser.parse_args(argv).only or sorted(TOOLSETS):
        record(toolset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
