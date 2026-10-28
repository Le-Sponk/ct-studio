"""Fake wszst, wkclt, wkmpt and wimgt: the subset CT Studio uses, as the real 2.42a behaves.

Each behaviour below is one or more recorded real runs (``recordings/<tool>/2.42a/*-ops.json``,
replayed by ``tests/unit/test_fake_wiimm.py``). Things the fakes cannot compute are left
out rather than guessed: check findings, KMP/KCL analysis lines after the first output
line, real archive contents. Archives a fake writes are marked so a fake never mistakes a
real SZS for one of its own (a real one is ``Unmodelled``).

Quirks kept because the real tools have them: ``wszst create`` reports an existing or
uncreatable destination on stderr but still exits 0; ``wkmpt encode`` overwrites an
existing file without ``--overwrite``; ``wimgt`` stores RGBA PNGs as RGB5A3.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import wiimm_cli
from fake_runtime import Outcome, Refused, Unmodelled, finish, recordings

VERSION = "2.42a"  # the pin these fakes imitate; tests compare it with tool_catalogue
FAKE_MARK = b"\nCT-STUDIO-FAKE-ARCHIVE\n"
YAZ0 = b"Yaz0"
U8 = bytes.fromhex("55aa382d")
# Real formats a fake must not pretend to read.
REAL_MAGIC = (YAZ0, b"Yaz1", U8, b"WU8a", b"bres", b"RKMD", b"TEX0", b"PACK", b"\x89PNG")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ERROR_NAMES = {
    36: "INVALID DATA",
    39: "INVALID FILE FORMAT",
    64: "FILE ALREADY EXISTS",
    78: "CAN'T OPEN FILE",
    82: "CAN'T CREATE FILE",
}
NO_SUCH_FILE = "-> No such file or directory [2]"


def show(raw: str) -> str:
    """Paths as the Cygwin build prints them: ``\\`` becomes ``/`` (recorded absolute case)."""
    return raw.replace("\\", "/") if os.name == "nt" else raw


def error(tool: str, code: int, *lines: str) -> str:
    text = f"!! {tool}: ERROR #{code} [{ERROR_NAMES[code]}]\n"
    return text + "".join(f"!!        {line}\n" for line in lines)


@dataclass(frozen=True)
class Target:
    raw: str
    path: Path
    make_parents: bool


def allow(parsed: wiimm_cli.Parsed, modelled: set[str]) -> None:
    extra = sorted(set(parsed.options) - modelled)
    if extra:
        raise Unmodelled(f"{parsed.command} {extra}")


def one_source(parsed: wiimm_cli.Parsed) -> str:
    if len(parsed.positionals) != 1:
        raise Unmodelled(f"{parsed.command} with {len(parsed.positionals)} sources")
    return parsed.positionals[0]


def target(parsed: wiimm_cli.Parsed, default: str | None = None) -> Target:
    dest, dest_parents = parsed.options.get("--dest"), parsed.options.get("--DEST")
    if dest is not None and dest_parents is not None:
        raise Unmodelled("--dest together with --DEST")
    raw = dest if dest is not None else dest_parents if dest_parents is not None else default
    if not isinstance(raw, str):
        raise Unmodelled("no destination (Wiimm's default naming is not recorded here)")
    if raw == "-" or "%" in raw or raw.endswith(("/", "\\")) or Path(raw).is_dir():
        raise Unmodelled(f"destination {raw!r} (stdout, escapes or a folder)")
    return Target(raw, Path(raw), dest_parents is not None)


def blocked(tool: str, where: Target, *, overwrite: bool) -> tuple[int, str] | None:
    if where.path.exists() and not overwrite:
        return 64, error(tool, 64, f"File already exists: {show(where.raw)}")
    if not where.make_parents and not where.path.parent.is_dir():
        return 82, error(tool, 82, f"Can't create file: {show(where.raw)}", NO_SUCH_FILE)
    return None


def read_source(tool: str, raw: str, stdout: str = "") -> bytes:
    path = Path(raw)
    if not path.exists():
        raise Refused(
            Outcome(78, stdout, error(tool, 78, f"Can't find file: {show(raw)}", NO_SUCH_FILE))
        )
    if path.is_dir():
        raise Unmodelled(f"{raw} is a folder")
    return path.read_bytes()


def write_one(
    tool: str, line: str, where: Target, data: bytes, *, overwrite: bool, exit_on_block: bool
) -> Outcome:
    problem = blocked(tool, where, overwrite=overwrite)
    if problem is not None:
        code, stderr = problem
        return Outcome(code if exit_on_block else 0, line, stderr)
    return Outcome(0, line, writes=[(where.path, data)], make_parents=where.make_parents)


# --- archives ------------------------------------------------------------------------------


def fake_archive(magic: bytes, folder: Path) -> bytes:
    files = {}
    for entry in sorted(folder.iterdir(), key=lambda path: path.name):
        if not entry.is_file():
            raise Unmodelled(f"sub-folder {entry.name} in an archive source")
        data = entry.read_bytes()
        files[entry.name] = {"size": len(data), "magic": data[:4].hex()}
    if len(files) < 2:
        raise Unmodelled("archives of fewer than two files")
    return magic + FAKE_MARK + json.dumps(files, sort_keys=True).encode("utf-8")


def read_archive(data: bytes) -> tuple[str, dict[str, dict[str, object]]] | None:
    """(label, files) for a fake archive; None for data in no known format."""
    head, mark, body = data.partition(FAKE_MARK)
    if mark and head in (YAZ0, U8):
        return ("YAZ0.U8" if head == YAZ0 else "U8"), json.loads(body)
    if data[:4] in REAL_MAGIC:
        raise Unmodelled("a real archive (fakes only read their own)")
    return None


def yaz0_archive(tool: str, raw: str) -> dict[str, dict[str, object]]:
    archive = read_archive(read_source(tool, raw))
    if archive is None or archive[0] != "YAZ0.U8":
        raise Unmodelled(f"{raw} is not a compressed fake archive")
    return archive[1]


# --- wszst ---------------------------------------------------------------------------------


def _is_empty(name: str, folder: Path) -> bool:
    return name == "empty" and folder.is_dir() and not any(folder.iterdir())


def _empty_archive(parsed: wiimm_cli.Parsed, where: Target) -> bytes:
    """Only the exact recorded empty-stage creation is modelled."""
    if where.raw != "empty.szs" or set(parsed.options) != {"--dest"}:
        raise Unmodelled("unrecorded empty archive creation")
    return YAZ0 + FAKE_MARK + b"{}"  # exact recorded invocation, not real SZS bytes


def _create_options(parsed: wiimm_cli.Parsed) -> bool:
    """Validate recorded creation flags; return whether the archive is uncompressed."""
    allow(parsed, {"--dest", "--DEST", "--overwrite", "--no-compress", "--fast", "--compr"})
    compr = parsed.options.get("--compr")
    if compr is not None and not re.fullmatch(r"[0-9]", str(compr)):
        raise Unmodelled(f"--compr={compr}")
    plain = "--no-compress" in parsed.options
    if plain and ({"--fast", "--compr"} & set(parsed.options)):
        raise Unmodelled("--no-compress with a compression level")
    return plain


def wszst_create(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    plain = _create_options(parsed)
    source = one_source(parsed)
    name = source.rstrip("/\\")
    default = f"./{name}.szs" if name and Path(name).name == name else None
    where = target(parsed, default)
    shown = show(name) + "/"
    folder = Path(source)
    if not folder.exists():
        line = f"CREATE {shown} -> DIR:{show(where.raw)}\n"
        raise Refused(
            Outcome(78, line, error(tool, 78, f"Can't open directory: {shown}", NO_SUCH_FILE))
        )
    if not folder.is_dir():
        raise Unmodelled("create from a single file")
    label, magic = ("U8", U8) if plain else ("YAZ0.U8", YAZ0)
    line = f"CREATE {shown} -> {label}:{show(where.raw)}\n"
    data = _empty_archive(parsed, where) if _is_empty(name, folder) else fake_archive(magic, folder)
    overwrite = "--overwrite" in parsed.options
    return write_one(tool, line, where, data, overwrite=overwrite, exit_on_block=False)


def wszst_list(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--long"})
    raw = one_source(parsed)
    files = yaz0_archive(tool, raw)
    if any(len(name) > len("file or directory") for name in files):
        raise Unmodelled("names wider than the recorded --long table")
    out = f"\n> 0 directories + {len(files)} files of YAZ0.U8:{show(raw)} \n\n"
    if "--long" not in parsed.options:
        return Outcome(0, out + "".join(f"{name}\n" for name in files) + "\n")
    out += "size/dec  magic file or directory\n" + "─" * 34 + "\n"
    for name, info in files.items():
        out += f"{info['size']:>8}  {_magic_text(str(info['magic']))}  {name}\n"
    return Outcome(0, out + "\n")


def _magic_text(magic_hex: str) -> str:
    return "".join(chr(byte) if 0x20 < byte < 0x7F else "." for byte in bytes.fromhex(magic_hex))


def _known_stage(folder: Path) -> bool:
    """Only the byte-identical recorded fixture can justify a fake directory prefix."""
    row = next(
        row for row in recordings("wszst", VERSION, "ops") if row["case"] == "check directory"
    )
    inputs = row["inputs"]
    if {entry.name for entry in folder.iterdir()} != {"course.kcl", "course.kmp"}:
        return False
    return all(
        not (path := folder / name).is_symlink()
        and path.is_file()
        and sha256(path.read_bytes()).hexdigest() == info["sha256"]
        for name, info in inputs.items()
    )


def wszst_check(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--brief"})
    raw = one_source(parsed)
    if Path(raw).is_dir():
        if "--brief" in parsed.options:
            raise Unmodelled("brief check of a directory")
        if raw == "empty" and not any(Path(raw).iterdir()):
            return Outcome(0, "\nCHECK U8:empty\n")
        if not _known_stage(Path(raw)):
            raise Unmodelled("check of an unrecorded directory")
        return Outcome(0, f"\nCHECK U8:{show(raw)}\n")
    archive = read_archive(read_source(tool, raw, stdout="\nCHECK ?:\n"))
    if archive is None:
        message = f"CHECK doesn't support file format '?': {show(raw)}"
        return Outcome(0, f"\nCHECK ?:{show(raw)}\n", error(tool, 39, message))
    if archive[0] != "YAZ0.U8":
        raise Unmodelled("check of an uncompressed archive")
    # The real tool goes on to list findings and exits 2 on warnings; a fake has none.
    return Outcome(0, f"\nCHECK YAZ0.U8:{show(raw)}\n")


def wszst_minimap(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--auto"})
    if "--auto" not in parsed.options:
        raise Unmodelled("minimap without --auto")
    raw = one_source(parsed)
    if not Path(raw).exists():
        raise Unmodelled("minimap of a missing file")
    if any(name.startswith("map_model") for name in yaz0_archive(tool, raw)):
        raise Unmodelled("minimap with a map model (the real tool patches it)")
    return Outcome(0, f"\nMinimap data of YAZ0:{show(raw)}\n")


# --- wkclt / wkmpt / wimgt -----------------------------------------------------------------


def wkclt_decode(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--dest", "--DEST", "--overwrite"})
    raw = one_source(parsed)
    data = read_source(tool, raw)
    if data[:1] == b"#" or data[:4] in REAL_MAGIC or FAKE_MARK in data:
        raise Unmodelled(f"{raw} is not a binary KCL")
    where = target(parsed)
    if where.path.suffix != ".obj":
        raise Unmodelled("KCL decode to a format other than OBJ")
    line = f"DECODE KCL:{show(raw)} -> KCLTXT:{show(where.raw)}\n"
    outcome = write_one(
        tool,
        line,
        where,
        b"#KCL fake OBJ\n",
        overwrite="--overwrite" in parsed.options,
        exit_on_block=True,
    )
    if outcome.writes:  # the real tool writes a material library next to the OBJ
        outcome.writes.append((where.path.with_suffix(".mtl"), b"\r\nnewmtl fake\n"))
    return outcome


def wkmpt_decode(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--dest", "--DEST", "--overwrite", "--brief"})
    raw = one_source(parsed)
    default = raw[: -len(".kmp")] + ".txt" if raw.endswith(".kmp") else None
    data = read_source(tool, raw)
    where = target(parsed, default)
    if data.startswith(b"#KMP") or (data[:4] in REAL_MAGIC and data[:4] != b"RKMD"):
        raise Unmodelled(f"decode of {raw} (not a binary KMP)")
    if data[:4] != b"RKMD":
        stdout = f"DECODE ?:{show(raw)} -> KMPTXT:{show(where.raw)}\n"
        raise Refused(Outcome(36, stdout, error(tool, 36, f"No KMP file: {show(raw)}")))
    line = f"DECODE KMP:{show(raw)} -> KMPTXT:{show(where.raw)}\n"
    text = b"#KMP fake text\n" + data[4:16].hex().encode("ascii") + b"\n"
    return write_one(
        tool, line, where, text, overwrite="--overwrite" in parsed.options, exit_on_block=True
    )


def wkmpt_encode(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--dest", "--DEST", "--overwrite"})
    raw = one_source(parsed)
    data = read_source(tool, raw)
    where = target(parsed)
    if data[:4] in REAL_MAGIC:
        raise Unmodelled(f"encode of binary {raw}")
    if not data.startswith(b"#KMP"):
        stdout = f"ENCODE ?:{show(raw)} -> KMP:{show(where.raw)}\n"
        raise Refused(Outcome(36, stdout, error(tool, 36, f"No KMP file: {show(raw)}")))
    line = f"ENCODE KMPTXT:{show(raw)} -> KMP:{show(where.raw)}\n"
    # Recorded: encode replaces an existing KMP even without --overwrite.
    return write_one(tool, line, where, b"RKMD" + FAKE_MARK, overwrite=True, exit_on_block=True)


def wimgt_encode(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    allow(parsed, {"--dest", "--DEST", "--overwrite"})
    raw = one_source(parsed)
    data = read_source(tool, raw)
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise Unmodelled(f"{raw} is not a PNG")
    if (data[24], data[25]) != (8, 6):
        raise Unmodelled("only 8-bit RGBA PNGs were recorded (stored as RGB5A3)")
    where = target(parsed)
    if where.path.suffix != ".tex0":
        raise Unmodelled("image output other than TEX0")
    line = f"ENCODE PNG:{show(raw)} -> TEX.RGB5A3:{show(where.raw)}\n"
    overwrite = "--overwrite" in parsed.options
    return write_one(
        tool, line, where, b"TEX0" + FAKE_MARK, overwrite=overwrite, exit_on_block=True
    )


# --- recorded replies, dispatch ------------------------------------------------------------


def replay(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    if parsed.options:
        raise Unmodelled(f"{parsed.command} with options")
    wanted = [parsed.command.lower(), *(arg.lower() for arg in parsed.positionals)]
    for record in recordings(tool, VERSION, "help"):  # type: ignore[union-attr]
        if [str(arg).lower() for arg in record["argv"]] == wanted:  # type: ignore[index]
            return Outcome(int(record["exit_code"]), str(record["stdout"]), str(record["stderr"]))  # type: ignore[index]
    raise Unmodelled(f"{' '.join(wanted)} was not recorded")


Command = Callable[[str, wiimm_cli.Parsed], Outcome]
COMMANDS: dict[tuple[str, str], Command] = {
    ("wszst", "CREATE"): wszst_create,
    ("wszst", "LIST"): wszst_list,
    ("wszst", "CHECK"): wszst_check,
    ("wszst", "MINIMAP"): wszst_minimap,
    ("wkclt", "DECODE"): wkclt_decode,
    ("wkmpt", "DECODE"): wkmpt_decode,
    ("wkmpt", "ENCODE"): wkmpt_encode,
    ("wimgt", "ENCODE"): wimgt_encode,
}


def main(tool: str, argv: list[str]) -> int:
    def run() -> Outcome:
        parsed = wiimm_cli.parse(tool, VERSION, argv)
        if parsed.command in ("VERSION", "HELP"):
            return replay(tool, parsed)
        command = COMMANDS.get((tool, parsed.command))
        if command is None:
            raise Unmodelled(f"{tool} {parsed.command}")
        return command(tool, parsed)

    return finish(tool, argv, run)
