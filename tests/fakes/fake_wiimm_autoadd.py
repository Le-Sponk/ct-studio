"""Fake ``wszst autoadd`` and ``create --auto-add``: the recorded synthetic runs only (P2-T05d).

Wiimm judges a library file against its own list of the original game files, which no
fake can know. So the fake models only the recorded synthetic world: an empty library,
a library holding the synthetic BRRES under the itembox name (reported *invalid*), a
``Course/beginner_course.szs`` built from the objects stage plus that BRRES, and creating
the objects stage with either library. Everything else is ``Unmodelled``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import fake_wiimm as fw
import wiimm_cli
from fake_runtime import RECORDINGS, Outcome, Refused, Unmodelled, recordings

ITEM = "itembox.brres"
COURSE = "beginner_course.szs"
_HEADERS = ("CURRENT AUTO-ADD PATH: ", "SEARCH PATH[0]: ", "LIST OF FILES IN ")
_HEADERS_2 = ("LIST OF MISSED FILES IN ", "LIST OF INVALID FILES IN ")


def _row(case: str) -> Mapping[str, Any]:
    return next(row for row in recordings("wszst", fw.VERSION, "ops") if row["case"] == case)


def _digest(case: str, name: str) -> str:
    return str(_row(case)["inputs"][name]["sha256"])


def _is(path: Path, case: str, name: str) -> bool:
    return path.is_file() and sha256(path.read_bytes()).hexdigest() == _digest(case, name)


def _library_kind(raw: str) -> str:
    """``empty`` or ``synthetic`` (only the retained BRRES as itembox); else Unmodelled."""
    folder = Path(raw)
    if Path("auto-add").is_dir():
        raise Unmodelled("a ./auto-add folder adds a search path (not recorded)")
    names = sorted(entry.name for entry in folder.iterdir())
    if not names:
        return "empty"
    if names == [ITEM] and _is(folder / ITEM, "create auto-add", "map_model.brres"):
        return "synthetic"
    raise Unmodelled("an auto-add library with unrecorded content")


def _missing_dir(raw: str, *, status_line: bool) -> Refused:
    stderr = fw.error("wszst", 84, f"Directory does not exist: {fw.show(raw)}")
    if status_line:
        stderr += "wszst: Command 'AUTOADD' returns with status #84 [CAN'T CREATE DIRECTORY]\n"
    return Refused(Outcome(84, "", stderr))


def _renamed(case: str, recorded: str, raw: str) -> str:
    """The recorded report with only its path-bearing header lines renamed."""
    lines = str(_row(case)["stdout"]).splitlines(keepends=True)
    out = []
    for line in lines:
        for prefix in (*_HEADERS, *_HEADERS_2):
            if line.lstrip().startswith(prefix) and line.rstrip("\n").endswith(recorded):
                line = line[: len(line) - len(recorded) - 1] + fw.show(raw) + "\n"
        out.append(line)
    return "".join(out)


def _status(raw: str, verbose: str | None) -> Outcome:
    if not Path(raw).is_dir():
        if verbose != "2":
            raise Unmodelled("status of a missing library")
        raise _missing_dir(raw, status_line=True)
    kind = _library_kind(raw)
    if verbose is None:
        return Outcome(0, _renamed("autoadd status dest", "lib", raw))
    if verbose != "2":
        raise Unmodelled(f"--verbose x{verbose}")
    case, recorded = (
        ("autoadd verify empty", "empty")
        if kind == "empty"
        else (
            "autoadd verify synthetic",
            "lib",
        )
    )
    return Outcome(0, _renamed(case, recorded, raw))


def _course_archive(source: Path) -> None:
    """Only the recorded synthetic Course/ folder: one fake archive of the objects stage."""
    entries = sorted(entry.name for entry in source.iterdir())
    if entries != [COURSE]:
        raise Unmodelled(f"auto-add source with {entries}")
    archive = fw.yaz0_archive("wszst", str(source / COURSE))
    inputs = _row("autoadd build")["inputs"]
    expected = {
        name: {"size": inputs[kept]["size"], "magic": str(inputs[kept]["head"])[:8]}
        for name, kept in (
            ("course.kcl", "course.kcl"),
            ("course.kmp", "objects.kmp"),
            (ITEM, "map_model.brres"),
        )
    }
    if archive != expected:
        raise Unmodelled("an auto-add source archive with unrecorded content")


def _build(raw: str, where: fw.Target) -> Outcome:
    source, library = Path(raw), where.path
    if not where.make_parents and not library.is_dir():
        raise _missing_dir(where.raw, status_line=False)
    head = f"\nCURRENT AUTO-ADD PATH: {fw.show(where.raw)}\n"
    if not source.exists():
        error = fw.error("wszst", 78, f"Can't find file: {fw.show(raw)}", fw.NO_SUCH_FILE)
        raise Refused(Outcome(78, head + "ANALYZE ?:\n", error))
    if not source.is_dir():
        raise Unmodelled("auto-add from a single file")
    if not any(source.iterdir()):
        return Outcome(0, head)
    _course_archive(source)
    out = head + f"ANALYZE YAZ0.U8:{fw.show(raw.rstrip('/'))}/{COURSE}\n"
    item = library / ITEM
    if item.exists():
        if not _is(item, "autoadd build", "map_model.brres"):
            raise Unmodelled("an existing, different library file")
        return Outcome(0, out)
    data = (RECORDINGS / "wszst" / fw.VERSION / "inputs" / "map_model.brres").read_bytes()
    add = f"  ADD {len(data):>7}, BRRES:{fw.show(where.raw)}/{ITEM}\n"
    return Outcome(0, out + add, writes=[(item, data)], make_parents=True)


def _default_status(verbose: object) -> Outcome:
    if verbose is not None or Path("auto-add").is_dir():
        raise Unmodelled("default status with -v or a ./auto-add folder")
    return Outcome(0, str(_row("autoadd status")["stdout"]))


def _build_target(parsed: wiimm_cli.Parsed) -> fw.Target:
    dest, dest_parents = parsed.options.get("--dest"), parsed.options.get("--DEST")
    raw = dest if isinstance(dest, str) else dest_parents
    if not isinstance(raw, str) or (dest is not None and dest_parents is not None):
        raise Unmodelled("auto-add build needs exactly one of --dest/--DEST")
    return fw.Target(raw, Path(raw), dest is None)


def autoadd(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    fw.allow(parsed, {"--dest", "--DEST", "--verbose"})
    verbose = parsed.options.get("--verbose")
    if parsed.positionals:
        if verbose is not None:
            raise Unmodelled("auto-add build with --verbose")
        return _build(fw.one_source(parsed), _build_target(parsed))
    if "--DEST" in parsed.options:
        raise Unmodelled("status with --DEST")
    dest = parsed.options.get("--dest")
    if dest is None:
        return _default_status(verbose)
    return _status(str(dest), None if verbose is None else str(verbose))


# --- create --auto-add ----------------------------------------------------------------


def _check_create(parsed: wiimm_cli.Parsed) -> str:
    """Refuse every auto-add creation except the recorded objects stage + library."""
    if not {"--auto-add", "--autoadd-path"} <= set(parsed.options):
        raise Unmodelled("--auto-add without --autoadd-path (default library) or vice versa")
    stage = Path(fw.one_source(parsed))
    if not stage.is_dir() or (stage / ITEM).exists():
        raise Unmodelled("auto-add with an unrecorded stage")
    if not _is(stage / "course.kmp", "create auto-add", "objects.kmp"):
        raise Unmodelled("auto-add with a KMP whose objects were not recorded")
    library = str(parsed.options["--autoadd-path"])
    if not Path(library).is_dir():
        raise Unmodelled("--autoadd-path to a missing folder")
    return _library_kind(library)


def _create(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    """The synthetic library supplies the itembox BRRES; an empty one adds nothing."""
    kind = _check_create(parsed)
    library = str(parsed.options["--autoadd-path"])
    plain = {k: v for k, v in parsed.options.items() if k not in ("--auto-add", "--autoadd-path")}
    outcome = fw.wszst_create(tool, wiimm_cli.Parsed(parsed.command, parsed.positionals, plain))
    if kind == "empty" or not outcome.writes:
        return outcome
    [(path, data)] = outcome.writes
    archive = fw.read_archive(data)
    if archive is None or archive[0] != "YAZ0.U8":
        raise Unmodelled("auto-add into an uncompressed archive")
    item = (Path(library) / ITEM).read_bytes()
    files = {**archive[1], ITEM: {"size": len(item), "magic": item[:4].hex()}}
    rebuilt = fw.YAZ0 + fw.FAKE_MARK + json.dumps(files, sort_keys=True).encode("utf-8")
    line = f"  >> auto-add [{len(item)}] {fw.show(library)}/{ITEM}\n"
    return replace(outcome, stdout=line + outcome.stdout, writes=[(path, rebuilt)])


def dispatch(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    if parsed.command == "AUTOADD":
        return autoadd(tool, parsed)
    if parsed.command == "CREATE":
        return _create(tool, parsed)
    raise Unmodelled(f"auto-add options with {parsed.command}")
