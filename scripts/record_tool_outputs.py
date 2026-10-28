"""Record real tool operations on generated fixtures for P2-T04b/c/d fakes.

Run after ``scripts/bootstrap_tools.py`` and ``scripts/fixtures/make_fixtures.py``::

    uv run python scripts/record_tool_outputs.py [--only wiimms-szs-tools|riistudio|abmatt]

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
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import record_tool_help as rth
import tool_paths as tp
from ops_cases import ABMATT_CASES, RSZST_CASES, WIIMM, WIIMM_CASES, Case

FIXTURES = tp.REPO_ROOT / "tests" / "fixtures" / "generated"
WORK = "<work>"
Resolve = Callable[[str], Path]
Fixture = Callable[[str], bytes]  # "course.kcl", "textures/road.png" -> file contents
DAE_TEXTURES = ("road.png", "grass.png", "fence.png", "water.png")  # copied beside course.dae
ABMATT_CMDS = {
    "set.txt": "set material xlu:true for road\n",
    "bad.txt": "frobnicate everything\n",
    "copy.txt": "copy material for road in source.brres\npaste material for road in dest.brres\n",
}


def normalize_abmatt(record: dict[str, object]) -> dict[str, object]:
    """Scrub ABMatt's process-specific seconds and PyInstaller PID, not diagnostics."""
    stdout = re.sub(
        r"(?<=\.\.\. finished in )\d+(?:\.\d+)?(?= secs)", "<duration>", str(record["stdout"])
    )
    stderr = re.sub(
        r"\[\d+\](?= Failed to execute script __main__)", "[<pid>]", str(record["stderr"])
    )
    return {**record, "stdout": stdout, "stderr": stderr}


# What to record, by bootstrap tool name: its executables and its case table.
TOOLSETS: dict[str, tuple[tuple[str, ...], tuple[Case, ...]]] = {
    "wiimms-szs-tools": (WIIMM, WIIMM_CASES),
    "riistudio": (("rszst",), RSZST_CASES),
    "abmatt": (("abmatt",), ABMATT_CASES),
}


def _place_abmatt(action: str, args: list[str], work: Path, fixture: Fixture) -> bool:
    if action == "@abobj":
        (work / "map.obj").write_bytes(fixture("map.obj"))
    elif action == "@abcmd":
        (work / args[0]).write_text(ABMATT_CMDS[args[0]], encoding="utf-8", newline="\n")
    elif action == "@copyfile":
        (work / args[1]).write_bytes((work / args[0]).read_bytes())
    else:
        return False
    return True


def _setup_archive(action: str, args: list[str], work: Path) -> None:
    destination: str | None = None
    if action == "rszst" and args[:1] == ["import-brres"] and len(args) > 2:
        destination = args[2]
    elif action == "abmatt" and args[:1] == ["convert"] and len(args) > 3:
        destination = args[3]
    if destination is not None:
        path = work / destination
        if not path.is_file() or not path.read_bytes().startswith(b"bres"):
            raise rth.RecordError(f"setup {action} did not write a BRRES at {destination}")


def verify_abmatt_source(installed_json: Path, exe: Path) -> None:
    """ABMatt's BRRES setup must use the actually pinned rszst, not just a path."""
    pin = rth.pinned_version("riistudio", installed_json)
    result = rth.capture(exe, ["--version"], cwd=exe.parent, roots={})
    if result["exit_code"] != tp.EXIT_MINUS_ONE or f"RiiStudio CLI Alpha {pin}" not in str(
        result["stdout"]
    ):
        raise rth.RecordError(f"rszst version mismatch: expected Alpha {pin}")


def _setup_tool(
    action: str, args: list[str], work: Path, resolve: Resolve, env: Mapping[str, str] | None
) -> None:
    result = rth.capture(resolve(action), expand(args, work), cwd=work, roots={}, env=env)
    if result["exit_code"] != 0:
        raise rth.RecordError(f"setup {action} exited {result['exit_code']}: {args}")
    _setup_archive(action, args, work)


def prepare(
    case: Case, work: Path, resolve: Resolve, fixture: Fixture, env: Mapping[str, str] | None = None
) -> None:
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
        elif _place_abmatt(action, args, work, fixture):
            continue
        else:
            _setup_tool(action, args, work, resolve, env)


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


def run_case(
    case: Case,
    resolve: Resolve,
    root: Path,
    fixture: Fixture,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
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
        prepare(case, work, resolve, tracked, env)
        before = snapshot(work)
        tool, *args = case.argv
        command_env = {**(env or os.environ), "PATH": ""} if case.without_wimgt else env
        record = rth.capture(
            resolve(tool), expand(args, work), cwd=work, roots={work: WORK}, env=command_env
        )
        if tool == "abmatt":
            record = normalize_abmatt(record)
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
    if toolset == "abmatt":
        return lambda tool: tp.ABMATT if tool == "abmatt" else tp.RSZST
    bin_dir = tp.TOOLS_DIR / "wiimms-szs-tools" / "bin"
    return lambda tool: tp.exe(bin_dir / tool)


def record(toolset: str) -> None:
    tools, cases = TOOLSETS[toolset]
    version = rth.pinned_version(toolset, tp.TOOLS_DIR / "installed.json")
    if toolset == "abmatt":
        verify_abmatt_source(tp.TOOLS_DIR / "installed.json", tp.RSZST)
    needed = "course.dae" if toolset in {"riistudio", "abmatt"} else "course.kmp"
    if not (FIXTURES / needed).is_file():
        raise rth.RecordError("generate fixtures first: scripts/fixtures/make_fixtures.py")
    abmatt_inputs = rth.RECORDINGS / "abmatt" / version / "inputs"

    def fixture(name: str) -> bytes:
        return (abmatt_inputs if name == "map.obj" else FIXTURES).joinpath(name).read_bytes()

    env = tp.tools_env() if toolset == "abmatt" else None
    with tempfile.TemporaryDirectory(prefix="ct ops é ") as root:
        records = [run_case(case, resolver(toolset), Path(root), fixture, env) for case in cases]
    write(records, tools, version, "windows" if sys.platform == "win32" else "linux")
    if toolset in {"riistudio", "abmatt"}:
        # Byte-exact import fixtures are retained for stand-in replay on either OS.
        inputs = (
            rth.RECORDINGS / ("rszst" if toolset == "riistudio" else "abmatt") / version / "inputs"
        )
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
