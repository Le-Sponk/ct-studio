"""Fake Wiimm reports that only replay real runs on byte-identical inputs (P2-T05c2).

``wkclt analyze``/``flags`` and ``wszst minimap`` print facts about a file's contents,
which the fakes cannot compute. A source whose SHA-256 equals a recorded input of a row
with the same command and options gets that row's real output (and, for the recorded
minimap patch, the real patched bytes); anything else is ``Unmodelled``.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

import fake_wiimm as fw
import wiimm_cli
from fake_runtime import RECORDINGS, Outcome, Unmodelled, recordings

JUNK = b"not a track file\n" * 4  # the recorder's junk input
# Real ``minimap --auto`` output bytes, retained and checked by the real integration test.
PATCHED = {"minimap auto brres": "map_model_patched.brres"}
_KCL_LABEL = {"ANALYZE": "Analyze", "FLAGS": "KCL Flags of"}


def _same_request(tool: str, row: Mapping[str, Any], parsed: wiimm_cli.Parsed) -> bool:
    if row["exit_code"] != 0 or str(row["argv"][0]).upper() != parsed.command:
        return False  # only successful runs of this command can be replayed
    recorded = wiimm_cli.parse(tool, fw.VERSION, [str(arg) for arg in row["argv"]])
    return (recorded.options, len(recorded.positionals)) == (parsed.options, 1)


def _recorded(tool: str, parsed: wiimm_cli.Parsed, data: bytes) -> Mapping[str, Any] | None:
    digest = sha256(data).hexdigest()
    for row in recordings(tool, fw.VERSION, "ops"):
        if not _same_request(tool, row, parsed):
            continue
        name = Path(str(row["argv"][-1])).name
        if row["inputs"].get(name, {}).get("sha256") == digest:
            return row
    return None


def _replay(tool: str, row: Mapping[str, Any], raw: str) -> Outcome:
    recorded = str(row["argv"][-1])

    def rename(text: object) -> str:
        return str(text).replace(recorded, fw.show(raw))

    writes: list[tuple[Path, bytes]] = []
    for name, effect in row["files"].items():
        if name != recorded or effect["effect"] != "changed" or row["case"] not in PATCHED:
            raise Unmodelled(f"file effects of {row['case']}")
        result = RECORDINGS / tool / fw.VERSION / "inputs" / PATCHED[row["case"]]
        writes.append((Path(raw), result.read_bytes()))
    return Outcome(int(row["exit_code"]), rename(row["stdout"]), rename(row["stderr"]), writes)


def kcl_report(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    fw.allow(parsed, set())
    raw = fw.one_source(parsed)
    data = fw.read_source(tool, raw)
    if data == JUNK:
        stdout = f"{_KCL_LABEL[parsed.command]} ?:{fw.show(raw)}\n"
        return Outcome(36, stdout, fw.error(tool, 36, f"No KCL or OBJ file: {fw.show(raw)}"))
    row = _recorded(tool, parsed, data)
    if row is None:
        raise Unmodelled(f"{parsed.command.lower()} of an unrecorded KCL")
    return _replay(tool, row, raw)


def minimap(tool: str, parsed: wiimm_cli.Parsed) -> Outcome:
    fw.allow(parsed, {"--auto"})
    if "--auto" not in parsed.options:
        raise Unmodelled("minimap without --auto")
    raw = fw.one_source(parsed)
    data = fw.read_source(tool, raw)
    row = _recorded(tool, parsed, data)
    if row is not None:
        return _replay(tool, row, raw)
    archive = fw.read_archive(data)  # a real format that was not recorded is Unmodelled
    if archive is None:
        return Outcome(0, f"\nMinimap data of ?:{fw.show(raw)}\n")
    if archive[0] != "YAZ0.U8" or any(name.startswith("map_model") for name in archive[1]):
        raise Unmodelled("minimap of an uncompressed archive or one with a map model")
    return Outcome(0, f"\nMinimap data of YAZ0:{fw.show(raw)}\n")
