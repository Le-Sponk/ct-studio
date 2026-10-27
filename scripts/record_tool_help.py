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
import re
import sys
from collections.abc import Mapping, Sequence
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
    # Bare `help` lists every real command, so a fake can tell "unknown command" (the real
    # tool's error) from "real but not modelled" (the fake's loud failure).
    argvs = (("version",), ("help",), *(("help", command) for command in _WIIMM_HELP[name]))
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
    roots = {tools_root: PLACEHOLDER}
    return [capture(exe, argv, cwd=exe.parent, roots=roots) for argv in argvs]


def capture(
    exe: Path, argv: Sequence[str], *, cwd: Path, roots: Mapping[Path, str]
) -> dict[str, object]:
    """Run once through the core runner; keep every line, replace ``roots`` by placeholders."""
    lines: dict[Stream, list[str]] = {"stdout": [], "stderr": []}

    def keep(stream: Stream, line: str) -> None:
        lines[stream].append(line)

    result = run([exe, *argv], cwd=cwd, timeout=TIMEOUT_SECONDS, on_line=keep, check=False)
    return {
        "argv": [clean(arg, roots) for arg in argv],
        "exit_code": result.exit_code,
        "stdout": "".join(clean(line, roots) + "\n" for line in lines["stdout"]),
        "stderr": "".join(clean(line, roots) + "\n" for line in lines["stderr"]),
    }


def clean(text: str, roots: Mapping[Path, str]) -> str:
    """Replace every spelling of each root folder (longest first) with its placeholder."""
    pairs = [(spelling, label) for root, label in roots.items() for spelling in _spellings(root)]
    for spelling, label in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(spelling, label)
    return text


def _spellings(folder: Path) -> set[str]:
    resolved = folder.resolve()
    variants = {str(folder), folder.as_posix(), str(resolved), resolved.as_posix()}
    return variants | {_cygwin(resolved)} if sys.platform == "win32" else variants


def _cygwin(path: Path) -> str:
    """Wiimm's Windows build is a Cygwin program and prints ``/cygdrive/c/...`` paths."""
    drive = path.drive.rstrip(":").lower()
    return f"/cygdrive/{drive}{path.as_posix()[2:]}"


_WIIMM_OPTION_LINE = re.compile(r"^(?:  (-[A-Za-z0-9]) |     )--([A-Za-z0-9][\w-]*)(.*)$")


def wiimm_option_index(tool: str, xhelp: str) -> dict[str, object]:
    """Commands, aliases and options (with argument kind) from Wiimm's ``--xhelp``.

    Wiimm's getopt table is the union of every command's options; each command then
    refuses options it does not list. Argument kinds: ``none`` (two spaces before the
    description), ``required`` (``--dest path``) or ``optional`` (``--pt-dir=[=mode]``).
    """
    header = re.compile(rf"^{re.escape(tool)} ([A-Z0-9-]+(?:\|[A-Z0-9-]+)*) : ")
    commands: dict[str, dict[str, object]] = {}
    global_options: dict[str, dict[str, str | None]] = {}
    current: dict[str, dict[str, str | None]] | None = None
    for line in xhelp.splitlines():
        if line.startswith("Global options:"):
            current = global_options
        elif match := header.match(line):
            name, *aliases = match.group(1).split("|")
            current = {}
            commands[name] = {"aliases": aliases, "options": current}
        elif current is not None and (option := _WIIMM_OPTION_LINE.match(line)):
            short, long_name, rest = option.groups()
            current[f"--{long_name}"] = {"short": short, "arg": _argument_kind(rest)}
    if not commands or not global_options:
        raise RecordError(f"{tool} --xhelp has no command or global option sections")
    return {"commands": commands, "global": global_options}


def _argument_kind(rest: str) -> str:
    if rest.startswith("=[="):
        return "optional"
    return "required" if re.match(r"^ \S", rest) else "none"


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
        if tool == "wiimms-szs-tools":
            _record_option_index(name, exe, target.with_name(f"{platform_name}-options.json"))
    return 0


def _record_option_index(name: str, exe: Path, target: Path) -> None:
    [xhelp] = record(exe, [("--xhelp",)], tools_root=exe.parent)
    if xhelp["exit_code"] != 0:
        raise RecordError(f"{name} --xhelp exited {xhelp['exit_code']}")
    index = wiimm_option_index(name, str(xhelp["stdout"]))
    target.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{name}: {len(index['commands'])} commands -> {target.relative_to(tp.REPO_ROOT)}")  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())
