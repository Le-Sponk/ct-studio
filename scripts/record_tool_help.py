"""Record pinned CLI tools' real help output for the flag contract (P2-T04a).

Run after ``scripts/bootstrap_tools.py``::

    uv run python scripts/record_tool_help.py

Each tool is run through ``ctstudio.core.tools.process.run`` (the app's only spawner) and
its full output is written to ``tests/fakes/recordings/<tool>/<version>/<os>-help.json``.
Newlines become LF and the tool's install folder becomes ``<tool-dir>``, so recordings are
stable and contain no local paths. A tool whose installed version differs from the
catalogue pin is refused: a recording must describe the version the contract claims.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import tool_catalogue as tc
import tool_paths as tp

from ctstudio.core.tools.process import Stream, run

RECORDINGS = tp.REPO_ROOT / "tests" / "fakes" / "recordings"
TIMEOUT_SECONDS = 60.0
PLACEHOLDER = "<tool-dir>"

_WIIMM_HELP = {
    "wszst": ("create", "check", "analyze", "list", "slots", "minimap", "autoadd"),
    "wkclt": ("analyze", "flags", "encode", "decode"),
    "wkmpt": ("encode", "decode"),
    "wimgt": ("encode",),
}


def _wiimm(name: str) -> tuple[str, str, str, tuple[tuple[str, ...], ...]]:
    argvs = (("version",), *(("help", command) for command in _WIIMM_HELP[name]))
    return name, "wiimms-szs-tools", f"bin/{name}", argvs


# (recording name, catalogue tool, executable relative to its folder, argv lists).
# rszst's recording (P0-T13, both OSes) predates this script and is kept as measured.
PLAN: tuple[tuple[str, str, str, tuple[tuple[str, ...], ...]], ...] = (
    *(_wiimm(name) for name in _WIIMM_HELP),
    ("abmatt", "abmatt", "bin/abmatt", (("--help",),)),
    ("blender", "blender", "blender", (("--version",), ("--help",))),
)


class RecordError(Exception):
    """The recording would not describe the pinned tool."""


def pinned_version(tool: str, installed_json: Path) -> str:
    """Return the catalogue pin, provided ``.tools/installed.json`` says it is installed."""
    pin = tc.ALL_TOOLS[tool].version
    try:
        installed = json.loads(installed_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        installed = {}
    entry = installed.get(tool)
    if not isinstance(entry, dict):
        raise RecordError(f"{tool} is not installed; run scripts/bootstrap_tools.py")
    if entry.get("version") != pin:
        raise RecordError(f"{tool} {entry.get('version')} is installed but {pin} is pinned")
    return pin


def record(
    exe: Path, argvs: Sequence[Sequence[str]], *, tools_root: Path
) -> list[dict[str, object]]:
    """Run ``exe`` once per argv and return sanitised, complete output records."""
    records: list[dict[str, object]] = []
    for argv in argvs:
        lines: dict[Stream, list[str]] = {"stdout": [], "stderr": []}

        def keep(stream: Stream, line: str, lines: dict[Stream, list[str]] = lines) -> None:
            lines[stream].append(line)

        result = run(
            [exe, *argv], cwd=exe.parent, timeout=TIMEOUT_SECONDS, on_line=keep, check=False
        )
        records.append(
            {
                "argv": [_clean(arg, tools_root) for arg in argv],
                "exit_code": result.exit_code,
                "stdout": _join(lines["stdout"], tools_root),
                "stderr": _join(lines["stderr"], tools_root),
            }
        )
    return records


def _join(lines: list[str], tools_root: Path) -> str:
    return "".join(_clean(line, tools_root) + "\n" for line in lines)


def _clean(text: str, tools_root: Path) -> str:
    for spelling in sorted(_spellings(tools_root), key=len, reverse=True):
        text = text.replace(spelling, PLACEHOLDER)
    return text


def _spellings(folder: Path) -> set[str]:
    resolved = folder.resolve()
    variants = {str(folder), str(resolved), resolved.as_posix()}
    return variants | {_cygwin(resolved)} if sys.platform == "win32" else variants


def _cygwin(path: Path) -> str:
    """Wiimm's Windows build is a Cygwin program and prints ``/cygdrive/c/...`` paths."""
    drive = path.drive.rstrip(":").lower()
    return f"/cygdrive/{drive}{path.as_posix()[2:]}"


def main() -> int:
    platform_name = "windows" if sys.platform == "win32" else "linux"
    installed = tp.TOOLS_DIR / "installed.json"
    for name, tool, relative, argvs in PLAN:
        version = pinned_version(tool, installed)
        tool_dir = tp.TOOLS_DIR / tool
        exe = tp.exe(tool_dir / relative)
        records = record(exe, argvs, tools_root=tool_dir)
        target = RECORDINGS / name / version / f"{platform_name}-help.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(records, indent=1, ensure_ascii=False) + "\n"
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"{name} {version}: {len(records)} runs -> {target.relative_to(tp.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
