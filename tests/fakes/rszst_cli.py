"""rszst's command line as its clap parser handles it, from the recorded help (P2-T04c).

The subcommands, options and value names come from ``<os>-cli.json`` (the real ``--help``
outputs); the error texts and usage-line shapes from the recorded operation runs and the
clap probe noted in docs/reference/TOOLS.md. Anything else raises ``Unmodelled``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from fake_runtime import Outcome, Refused, Unmodelled, recordings

VERSION = "5.11.5"
PROG = "rszst.exe" if os.name == "nt" else "rszst"
NEWLINE = "\r\n" if os.name == "nt" else "\n"
CLAP_EXIT = -1  # rszst exits -1 on every clap error (Windows shows 4294967295, Linux 255)
SIMILAR = 0.7  # clap suggests a name when its Jaro similarity exceeds this (measured)

_CLI = recordings("rszst", VERSION, "cli")
BANNER = str(_CLI[0]["stdout"]).split("\n")[2]
_OPTION = re.compile(r"^  (?:-(\w), |    )--([\w-]+)(?: <(\w+)>)?")


@dataclass(frozen=True)
class Command:
    name: str
    longs: dict[str, str | None]  # long name -> value name, or None for a flag
    shorts: frozenset[str]


@dataclass
class Parsed:
    command: Command
    positionals: list[str] = field(default_factory=list)
    options: dict[str, str | bool] = field(default_factory=dict)


def _help(*argv: str) -> str:
    for record in _CLI:
        if record["argv"] == list(argv):
            return str(record["stdout"])
    raise RuntimeError(f"no recorded help for {argv}")


def _command(name: str) -> Command:
    text = _help(name, "--help")
    if f"Usage: {PROG} {name} [OPTIONS] <FROM> [TO]\n" not in text:
        raise RuntimeError(f"{name}: positionals differ from <FROM> [TO]; extend the model")
    options = text.split("\nOptions:\n", 1)[1].split("\n\n", 1)[0]
    longs: dict[str, str | None] = {}
    shorts: set[str] = set()
    for line in options.splitlines():
        match = _OPTION.match(line)
        if match is None:
            raise RuntimeError(f"{name}: unparsed option line {line!r}")
        short, long, value = match.groups()
        longs[long] = value
        if short:
            shorts.add(short)
    return Command(name, longs, frozenset(shorts))


MODELLED = ("import-brres", "brres-to-json", "json-to-brres", "dump-presets")
COMMANDS = {name: _command(name) for name in MODELLED}
SUBCOMMANDS = re.findall(r"(?m)^  ([\w-]+)  ", _help("--help").split("\nCommands:\n", 1)[1])


def _match_chars(a: str, b: str) -> tuple[list[str], list[str]]:
    window = max(0, max(len(a), len(b)) // 2 - 1)
    taken = [False] * len(b)
    matched_a: list[str] = []
    for i, char in enumerate(a):
        for j in range(max(0, i - window), min(len(b), i + window + 1)):
            if not taken[j] and b[j] == char:
                taken[j] = True
                matched_a.append(char)
                break
    matched_b = [char for char, hit in zip(b, taken, strict=True) if hit]
    return matched_a, matched_b


def jaro(a: str, b: str) -> float:
    """Jaro similarity as in the ``strsim`` crate clap uses for suggestions."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    matched_a, matched_b = _match_chars(a, b)
    if not matched_a:
        return 0.0
    transpositions = sum(x != y for x, y in zip(matched_a, matched_b, strict=True)) / 2
    m = len(matched_a)
    return (m / len(a) + m / len(b) + (m - transpositions) / m) / 3


def suggest(typed: str, command: Command) -> str | None:
    """The long option clap's "a similar argument exists" tip names, if any."""
    scores = sorted(((jaro(typed[2:], name), name) for name in command.longs), reverse=True)
    if not scores or scores[0][0] <= SIMILAR:
        return None
    if len(scores) > 1 and scores[1][0] == scores[0][0]:
        raise Unmodelled(f"{typed}: tied suggestions")
    return f"--{scores[0][1]}"


def clap_error(message: str, tip: str | None = None, usage: str | None = None) -> Refused:
    """clap writes its errors to stdout here; rszst then prints its banner and ``::``."""
    text = f"error: {message}\n\n"
    if tip is not None:
        text += f"  tip: {tip}\n\n"
    if usage is not None:
        text += f"Usage: {PROG} {usage}\n\n"
    text += "For more information, try '--help'.\n"
    return Refused(outcome(CLAP_EXIT, f"{text}\n{BANNER}\n::\n"))


def outcome(exit_code: int, stdout: str, stderr: str = "") -> Outcome:
    """The Windows build ends lines with CRLF, the Linux build with LF (measured)."""
    return Outcome(exit_code, stdout, stderr, newline=NEWLINE)


def _render(command: Command, long: str) -> str:
    value = command.longs[long]
    return f"--{long}" if value is None else f"--{long} <{value}>"


def _unknown_long(command: Command, parsed: Parsed, typed: str) -> Refused:
    if parsed.options:
        raise Unmodelled(f"{typed} after other options (usage line not measured)")
    hint = suggest(typed, command)
    if hint is None:
        tip = f"to pass '{typed}' as a value, use '-- {typed}'"
        used = ["<FROM>", "<TO>" if len(parsed.positionals) == 2 else "[TO]"]
        usage = " ".join(used) if parsed.positionals else "[OPTIONS] <FROM> [TO]"
    else:
        if len(parsed.positionals) != 2:
            raise Unmodelled(f"{typed}: suggestion usage measured only with both paths")
        tip = f"a similar argument exists: '{hint}'"
        usage = f"{_render(command, hint[2:])} <FROM> <TO>"
    return clap_error(f"unexpected argument '{typed}' found", tip, f"{command.name} {usage}")


def _value(command: Command, long: str, value: str) -> str:
    if value.startswith("-"):
        raise Unmodelled(f"--{long} value {value!r} (clap may read it as a flag)")
    if command.longs[long] in ("MIN_MIP", "MAX_MIP") and not re.fullmatch(r"[0-9]{1,9}", value):
        if not re.fullmatch(r"[A-Za-z]+", value):
            raise Unmodelled(f"--{long} {value!r}: only a letters-only bad number was measured")
        raise clap_error(
            f"invalid value '{value}' for '{_render(command, long)}': invalid digit found in string"
        )
    return value


def _take_long(command: Command, parsed: Parsed, args: list[str], i: int) -> int:
    typed = args[i]
    long, equals, value = typed[2:].partition("=")
    if long not in command.longs:
        raise _unknown_long(command, parsed, typed)
    if command.longs[long] is None:
        if equals or long in parsed.options:
            raise Unmodelled(f"{typed}: flag value or repeat not measured")
        parsed.options[long] = True
        return i + 1
    if long in parsed.options:
        raise clap_error(
            f"the argument '{_render(command, long)}' cannot be used multiple times",
            usage=f"{command.name} [OPTIONS] <FROM> [TO]",
        )
    if not equals:
        if i + 1 == len(args):
            raise clap_error(
                f"a value is required for '{_render(command, long)}' but none was supplied"
            )
        i, value = i + 1, args[i + 1]
    parsed.options[long] = _value(command, long, value)
    return i + 1


def _short_option(command: Command, parsed: Parsed, arg: str) -> Refused:
    if len(arg) != 2 or arg[1] in command.shorts or len(parsed.positionals) != 2:
        raise Unmodelled(f"short option {arg} (measured: unknown, after both paths)")
    tip = f"to pass '{arg}' as a value, use '-- {arg}'"
    return clap_error(
        f"unexpected argument '{arg}' found", tip, f"{command.name} [OPTIONS] <FROM> [TO]"
    )


def parse_command(command: Command, args: list[str]) -> Parsed:
    parsed = Parsed(command)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--" or arg == "-":
            raise Unmodelled(f"{arg!r} argument")
        if arg.startswith("--"):
            i = _take_long(command, parsed, args, i)
            continue
        if arg.startswith("-"):
            raise _short_option(command, parsed, arg)
        if len(parsed.positionals) == 2:
            raise clap_error(
                f"unexpected argument '{arg}' found", usage=f"{command.name} [OPTIONS] <FROM> [TO]"
            )
        parsed.positionals.append(arg)
        i += 1
    if not parsed.positionals:
        raise clap_error(
            "the following required arguments were not provided:\n  <FROM>",
            usage=f"{command.name} <FROM> [TO]",
        )
    return parsed


def parse(argv: list[str]) -> Parsed:
    if not argv or argv[0].startswith("-"):
        raise Unmodelled(f"top-level arguments {argv}")
    name, *args = argv
    if name not in SUBCOMMANDS:
        if any(jaro(name, known) > SIMILAR for known in SUBCOMMANDS):
            raise Unmodelled(f"{name}: clap lists similar subcommands (order not measured)")
        raise clap_error(f"unrecognized subcommand '{name}'", usage="<COMMAND>")
    if name not in COMMANDS:
        raise Unmodelled(f"rszst {name}")
    return parse_command(COMMANDS[name], args)


def replay(argv: list[str]) -> Outcome | None:
    """The recorded reply for a help or version request, if this exact one was recorded."""
    if not {"--help", "-h", "--version", "-V", "help"} & set(argv):
        return None
    for record in _CLI:
        if record["argv"] == argv:
            return outcome(CLAP_EXIT, str(record["stdout"]), str(record["stderr"]))
    raise Unmodelled(f"help request {argv} was not recorded")
