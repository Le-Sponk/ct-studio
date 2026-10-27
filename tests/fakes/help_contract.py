"""Which flags each pinned CLI accepts, read from its recorded real help (P2-T04a).

Recordings live in ``recordings/<tool>/<version>/*.json`` (see
``scripts/record_tool_help.py``). Four help formats are parsed:

* Wiimm (wszst, wkclt, wkmpt, wimgt): ``help <command>`` option tables, one per command.
* clap (rszst): ``<command> --help`` ``Options:`` lists, plus top-level ``--help``.
* ABMatt: one pipe table of global flags.
* Blender: ``-x or --long`` entries at column 0 of ``--help``.

``Contract.unknown_flags(args)`` returns the flags in ``args`` that the recorded help does
not list for that command, so an adapter or a fake cannot use a misspelt or foreign flag.
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

RECORDINGS = Path(__file__).resolve().parent / "recordings"

_FLAG = r"-{1,2}[A-Za-z0-9][\w-]*"
# Wiimm: "  -d --dest path" (short + long) or "     --no-wildcards" (long only).
# Continuation lines are indented 24 columns, so they never match.
_WIIMM_OPTION = re.compile(r"^(?:  (-[A-Za-z0-9]) |     )(--[A-Za-z0-9][\w-]*)")
# clap: "  -s, --scale <SCALE>" or "      --mipmaps".
_CLAP_OPTION = re.compile(r"^  (?:(-[A-Za-z0-9]), |    )(--[A-Za-z0-9][\w-]*)")
_BLENDER_OPTION = re.compile(rf"^({_FLAG})(?: or ({_FLAG}))?")

WIIMM_TOOLS = frozenset({"wszst", "wkclt", "wkmpt", "wimgt"})


class ContractError(Exception):
    """The recordings cannot answer the question (no recording, or unrecorded command)."""


def parse_wiimm(help_text: str) -> set[str]:
    return _matches(_WIIMM_OPTION, help_text)


def parse_clap(help_text: str) -> set[str]:
    return _matches(_CLAP_OPTION, help_text)


def parse_blender(help_text: str) -> set[str]:
    return _matches(_BLENDER_OPTION, help_text)


def parse_abmatt(help_text: str) -> set[str]:
    flags: set[str] = set()
    for line in help_text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.split("|")[1:3]]
            flags.update(cell for cell in cells if re.fullmatch(_FLAG, cell))
    return flags


def _matches(pattern: re.Pattern[str], help_text: str) -> set[str]:
    flags: set[str] = set()
    for line in help_text.splitlines():
        match = pattern.match(line)
        if match:
            flags.update(group for group in match.groups() if group)
    return flags


@dataclass(frozen=True)
class Contract:
    tool: str
    version: str
    # Flags accepted per subcommand; key None holds global flags (the only key for tools
    # without subcommands).
    commands: Mapping[str | None, frozenset[str]]

    @property
    def has_subcommands(self) -> bool:
        return any(name is not None for name in self.commands)

    def unknown_flags(self, args: Sequence[str]) -> list[str]:
        """Flags in ``args`` that the pinned help does not list; ``--`` ends flag parsing."""
        if "--" in args:
            args = args[: list(args).index("--")]
        allowed = set(self.commands.get(None, frozenset()))
        if self.has_subcommands:
            allowed |= self.commands[self._command(args)]
        flags = [arg.split("=", 1)[0] for arg in args if re.match(_FLAG, arg)]
        return [flag for flag in flags if flag not in allowed]

    def _command(self, args: Sequence[str]) -> str:
        positional = next((arg for arg in args if not arg.startswith("-")), None)
        name = positional.lower() if positional and self.tool in WIIMM_TOOLS else positional
        if name is None or name not in self.commands:
            raise ContractError(f"no recorded help for '{self.tool} {positional}'")
        return name


@functools.cache
def load_contract(tool: str, version: str) -> Contract:
    folder = RECORDINGS / tool / version
    # Help (``*-help.json``) and rszst's CLI captures (``*-cli.json``); operation runs
    # (``*-ops.json``) and Wiimm's option index (``*-options.json``) are for the fakes.
    files = sorted([*folder.glob("*-help.json"), *folder.glob("*-cli.json")])
    if not files:
        raise ContractError(f"no recordings for {tool} {version} in {folder}")
    records: list[dict[str, object]] = []
    for path in files:
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return Contract(tool, version, _commands(tool, records))


def _commands(tool: str, records: list[dict[str, object]]) -> dict[str | None, frozenset[str]]:
    commands: dict[str | None, set[str]] = {}
    for record in records:
        argv = [str(arg) for arg in record["argv"]]  # type: ignore[union-attr]
        text = str(record["stdout"]) + str(record["stderr"])
        key, parser = _classify(tool, argv)
        if parser is not None:
            commands.setdefault(key, set()).update(parser(text))
        elif key is not None:
            commands.setdefault(key, set())  # a recorded command without options
    return {key: frozenset(flags) for key, flags in commands.items()}


def _classify(tool: str, argv: list[str]) -> tuple[str | None, Callable[[str], set[str]] | None]:
    if tool in WIIMM_TOOLS:
        if argv[:1] == ["help"] and len(argv) == 2:
            return argv[1].lower(), parse_wiimm
        return (argv[0].lower(), None) if argv == ["version"] else (None, None)
    if tool == "rszst":
        if argv == ["--help"]:
            return None, parse_clap
        return (argv[0], parse_clap) if argv[1:] == ["--help"] else (None, None)
    parser = {"abmatt": parse_abmatt, "blender": parse_blender}[tool]
    return None, parser if argv == ["--help"] else None


def verified_templates(tools_markdown: str) -> list[str]:
    """argv templates from every TOOLS.md table with an "Exact argv template" column.

    Optional parts are written in ``[...]``; brackets are dropped so their flags are
    checked too.
    """
    templates: list[str] = []
    column: int | None = None
    for line in tools_markdown.splitlines():
        if not line.startswith("|"):
            column = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if column is None:
            column = cells.index("Exact argv template") if "Exact argv template" in cells else None
            continue
        match = re.search(r"`([^`]+)`", cells[column]) if column < len(cells) else None
        if match:
            templates.append(re.sub(r"[\[\]]", "", match.group(1)))
    return templates
