"""Wiimm's command line as the real 2.42a tools parse it, from their recorded ``--xhelp``.

GNU getopt semantics, measured on the real tools (``*-ops.json`` cases): options may come
before or after positionals; ``-dVALUE``/``-d VALUE``/``--dest=VALUE``/``--dest VALUE``;
the command is the first positional, case-insensitive, aliases allowed. An option no
command knows is a getopt error (exit 110); one another command knows is refused by this
command (exit 108). Abbreviations, repeats, ``--`` and global-only options are not
modelled: the real tools accept or reinterpret them in ways nobody has recorded.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

from fake_runtime import Outcome, Refused, Unmodelled, recordings

_MORE_HELP = "(pipe it to a pager like 'less') for more help.\n\n"


@dataclass
class Parsed:
    command: str
    positionals: list[str]
    options: dict[str, str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionIndex:
    commands: dict[str, dict[str, dict[str, str | None]]]  # COMMAND -> --long -> {short, arg}
    aliases: dict[str, str]  # lower-case name or alias -> COMMAND
    global_options: frozenset[str]
    kinds: dict[str, frozenset[str]]  # --long -> argument kinds across all sections
    shorts: dict[str, frozenset[str]]  # -x -> --long names across all sections


@functools.cache
def option_index(tool: str, version: str) -> OptionIndex:
    raw = recordings(tool, version, "options")
    assert isinstance(raw, dict)
    commands = {name: entry["options"] for name, entry in raw["commands"].items()}
    aliases: dict[str, str] = {}
    for name, entry in raw["commands"].items():
        for spelling in (name, *entry["aliases"]):
            aliases[spelling.lower()] = name
    kinds: dict[str, set[str]] = {}
    shorts: dict[str, set[str]] = {}
    for section in (raw["global"], *commands.values()):
        for long_name, spec in section.items():
            kinds.setdefault(long_name, set()).add(spec["arg"])
            if spec["short"]:
                shorts.setdefault(spec["short"], set()).add(long_name)
    return OptionIndex(
        commands=commands,
        aliases=aliases,
        global_options=frozenset(raw["global"]),
        kinds={name: frozenset(found) for name, found in kinds.items()},
        shorts={name: frozenset(found) for name, found in shorts.items()},
    )


def parse(tool: str, version: str, argv: list[str]) -> Parsed:
    index = option_index(tool, version)
    options, positionals = _getopt(tool, index, argv)
    if not positionals:
        raise Unmodelled("no command (global options alone)")
    command = index.aliases.get(positionals[0].lower())
    if command is None:
        message = (
            f"!! {tool}: ERROR #110 [SYNTAX ERROR]\n!!        Unknown command: {positionals[0]}\n"
        )
        raise Refused(
            Outcome(110, "", message + f"-> Type '{tool} -h' or '{tool} help' {_MORE_HELP}")
        )
    _refuse_foreign(tool, index, command, options)
    return Parsed(command, positionals[1:], options)


def _getopt(
    tool: str, index: OptionIndex, argv: list[str]
) -> tuple[dict[str, str | bool], list[str]]:
    options: dict[str, str | bool] = {}
    positionals: list[str] = []
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--":
            raise Unmodelled("'--' ends option parsing")
        if arg.startswith("--"):
            _long(tool, index, arg, rest, options)
        elif arg.startswith("-") and arg != "-":
            _shorts(tool, index, arg[1:], rest, options)
        else:
            positionals.append(arg)
    return options, positionals


def _long(
    tool: str, index: OptionIndex, arg: str, rest: list[str], options: dict[str, str | bool]
) -> None:
    name, equals, value = arg.partition("=")
    if name not in index.kinds:
        if any(known.startswith(name) for known in index.kinds):
            raise Unmodelled(f"{name} abbreviates a real option")
        if equals:
            raise Unmodelled(f"unknown option {arg} with a value")
        raise _unknown(tool, name[2:])
    kind = _kind(index, name)
    if kind == "none":
        if equals:
            raise Unmodelled(f"{name} takes no value")
        _add(options, name, True)
    elif kind == "required":
        _add(options, name, value if equals else _next_value(name, rest))
    else:
        _add(options, name, value if equals else True)


def _shorts(
    tool: str, index: OptionIndex, letters: str, rest: list[str], options: dict[str, str | bool]
) -> None:
    for position, letter in enumerate(letters):
        found = index.shorts.get(f"-{letter}")
        if not found:
            raise _unknown(tool, letter)
        if len(found) > 1:
            raise Unmodelled(f"-{letter} means {sorted(found)} in different commands")
        [name] = found
        kind = _kind(index, name)
        if kind == "none":
            _add(options, name, True)
        elif kind == "required":
            tail = letters[position + 1 :]
            _add(options, name, tail if tail else _next_value(name, rest))
            return
        else:
            raise Unmodelled(f"-{letter} has an optional value")


def _kind(index: OptionIndex, name: str) -> str:
    kinds = index.kinds[name]
    if len(kinds) > 1:
        raise Unmodelled(f"{name} takes different arguments in different commands")
    return next(iter(kinds))


def _next_value(name: str, rest: list[str]) -> str:
    if not rest:
        raise Unmodelled(f"{name} is missing its value")
    return rest.pop(0)


COUNTED = frozenset({"--verbose"})  # repeats measured only for -vv (wszst autoadd)


def _add(options: dict[str, str | bool], name: str, value: str | bool) -> None:
    if name in COUNTED and value is True:
        options[name] = str(int(str(options.get(name, "0"))) + 1)  # "1", "2", ...
        return
    if name in options:
        raise Unmodelled(f"{name} given twice (Wiimm counts repeats)")
    options[name] = value


def _unknown(tool: str, name: str) -> Refused:
    stderr = f"{tool}: unknown option -- {name}\n-> Type '{tool} -h' or '{tool} help' {_MORE_HELP}"
    return Refused(Outcome(110, "", stderr))


# Global options measured as accepted after a command (P2-T05d: create --auto-add).
_ALSO_ACCEPTED = {"CREATE": ("--autoadd-path",)}


def _refuse_foreign(
    tool: str, index: OptionIndex, command: str, options: dict[str, str | bool]
) -> None:
    allowed = {*index.commands[command], *_ALSO_ACCEPTED.get(command, ())}
    foreign = [name for name in options if name not in allowed]
    if not foreign:
        return
    if len(foreign) > 1 or foreign[0] in index.global_options:
        raise Unmodelled(f"options {foreign} with {command}")
    [name] = foreign
    shorts = sorted(short for short, longs in index.shorts.items() if name in longs)
    short = f" ({shorts[0]})" if len(shorts) == 1 else ""
    if len(shorts) > 1:
        raise Unmodelled(f"{name} has several short forms")
    stderr = (
        f"!! {tool}: ERROR #108 [SEMANTIC ERROR]\n"
        f"!!        Command '{command}' doesn't allow the option {name}{short}.\n"
        f"-> Type '{tool} help {command}' {_MORE_HELP}"
    )
    raise Refused(Outcome(108, "", stderr))
