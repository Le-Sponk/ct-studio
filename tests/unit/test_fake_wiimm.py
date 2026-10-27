"""P2-T04b: the Wiimm fakes behave like the real tools' recorded runs, through the core runner.

Every recorded case in ``tests/fakes/recordings/<tool>/<version>/*-ops.json`` (made by
``scripts/record_tool_outputs.py`` with the real tools) is replayed against the fakes with
stand-in inputs of the recorded size and leading bytes. A fake must match the real exit
code, stderr and file effects exactly, and stdout exactly or as a prefix (see ``compare``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import fake_wiimm
import record_tool_help as rth
import record_tool_outputs as rto
import tool_catalogue as tc
import wiimm_cli
from fake_runtime import UNMODELLED_EXIT

from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.versions import VersionCache, probe_versions

pytestmark = pytest.mark.timeout(60)

VERSION = tc.ALL_TOOLS["wiimms-szs-tools"].version
CASES = {case.name: case for case in rto.CASES}


def recorded_cases() -> list[object]:
    return [
        pytest.param(record, id=str(record["case"]))
        for tool in rto.WIIMM
        for record in rto.load(tool, VERSION)
    ]


def help_records() -> list[object]:
    params: list[object] = []
    for tool in rto.WIIMM:
        path = rth.RECORDINGS / tool / VERSION / "windows-help.json"
        for record in json.loads(path.read_text(encoding="utf-8")):
            params.append(pytest.param(tool, record, id=f"{tool} {' '.join(record['argv'])}"))
    return params


def stand_ins(record: dict[str, object]):
    inputs: dict[str, dict[str, object]] = record["inputs"]  # type: ignore[assignment]

    def fixture(name: str) -> bytes:
        head = bytes.fromhex(str(inputs[name]["head"]))
        return head + b"\0" * (int(str(inputs[name]["size"])) - len(head))

    return fixture


def test_every_recorded_case_is_still_in_the_case_table() -> None:
    recorded = {str(record["case"]) for tool in rto.WIIMM for record in rto.load(tool, VERSION)}
    assert recorded == set(CASES), "re-run scripts/record_tool_outputs.py after editing CASES"


@pytest.mark.parametrize("record", recorded_cases())
def test_fake_matches_the_recorded_real_run(
    record: dict[str, object], fake_tools_path, tmp_path: Path
) -> None:
    root = tmp_path / "ct ops é"
    root.mkdir()
    fake = rto.run_case(
        CASES[str(record["case"])], fake_tools_path.resolve, root, stand_ins(record)
    )

    # A fake never invents findings: where the real exit code reports them, it exits 0.
    expected_exit = 0 if record["compare"] == "findings" else record["exit_code"]
    assert fake["exit_code"] == expected_exit
    assert fake["stderr"] == record["stderr"]
    assert fake["files"] == record["files"]
    if record["compare"] == "exact":
        assert fake["stdout"] == record["stdout"]
    else:
        lines = str(fake["stdout"]).splitlines(keepends=True)
        assert lines, "a fake prints at least the real opening line"
        assert lines == str(record["stdout"]).splitlines(keepends=True)[: len(lines)]


@pytest.mark.parametrize(("tool", "record"), help_records())
def test_fake_help_and_version_equal_the_recordings(
    tool: str, record: dict[str, object], fake_tools_path, tmp_path: Path
) -> None:
    fake = rth.capture(fake_tools_path.resolve(tool), record["argv"], cwd=tmp_path, roots={})  # type: ignore[arg-type]
    assert (fake["exit_code"], fake["stdout"], fake["stderr"]) == (
        record["exit_code"],
        record["stdout"],
        record["stderr"],
    )


@pytest.mark.parametrize(
    "argv",
    [
        ("wszst", "extract", "t.szs"),  # a real command the fakes do not model
        ("wszst", "analyze", "t.szs"),  # real, help recorded, not modelled
        ("wszst", "create", "stage", "--dest", "t.szs", "--auto-add"),  # real option, no model
        ("wkclt", "decode", "c.kcl", "--dest", "c.obj", "--kcl-script", "f.txt"),
        ("wszst", "create", "stage", "--over"),  # getopt may expand abbreviations
        ("wszst", "--version"),
        ("wszst", "list", "-l", "-l", "t.szs"),  # repeating changes the real output
    ],
    ids=lambda argv: " ".join(argv),
)
def test_unmodelled_behaviour_fails_loudly(
    argv: tuple[str, ...], fake_tools_path, tmp_path: Path
) -> None:
    tool, *args = argv
    work = tmp_path / "work"
    (work / "stage").mkdir(parents=True)
    fake = rth.capture(fake_tools_path.resolve(tool), args, cwd=work, roots={})
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert "not modelled" in str(fake["stderr"])
    assert fake["stdout"] == ""
    assert sorted(path.name for path in work.iterdir()) == ["stage"], "nothing written"
    assert [call["argv"] for call in fake_tools_path.calls()] == [args], "still logged"


def test_fakes_refuse_to_read_real_archives(fake_tools_path, tmp_path: Path) -> None:
    # `check` would otherwise report "unsupported format" and exit 0, hiding the mix-up.
    (tmp_path / "real.szs").write_bytes(b"Yaz0" + bytes(60))
    for args in (["check", "real.szs"], ["list", "real.szs"]):
        fake = rth.capture(fake_tools_path.resolve("wszst"), args, cwd=tmp_path, roots={})
        assert fake["exit_code"] == UNMODELLED_EXIT, args


def test_wimgt_refuses_png_kinds_nobody_recorded(fake_tools_path, tmp_path: Path) -> None:
    # Only 8-bit RGBA was measured (stored as RGB5A3); grayscale picks another format.
    header = b"\x89PNG\r\n\x1a\n" + bytes.fromhex("0000000d49484452") + bytes(8)
    (tmp_path / "grey.png").write_bytes(header + bytes([8, 0]) + bytes(40))  # colour type 0
    argv = ["encode", "grey.png", "--dest", "g.tex0"]
    fake = rth.capture(fake_tools_path.resolve("wimgt"), argv, cwd=tmp_path, roots={})
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert not (tmp_path / "g.tex0").exists()


def test_fake_output_bytes_use_lf_like_the_cygwin_tools(fake_tools_path, tmp_path: Path) -> None:
    # The runner hides CR, so read the raw pipe (tests may spawn directly; src/ may not).
    import subprocess

    exe = str(fake_tools_path.resolve("wszst"))
    raw = subprocess.run([exe, "version"], cwd=tmp_path, capture_output=True, check=True)  # noqa: S603 - our fake
    assert raw.stdout.endswith(b"2024-03-26\n")
    assert b"\r" not in raw.stdout


def test_discovery_and_version_probes_find_the_fakes_and_the_log_records_calls(
    fake_tools_path, tmp_path: Path
) -> None:
    located = [(TOOL_BY_ID[tool], discover(TOOL_BY_ID[tool])) for tool in rto.WIIMM]
    for tool, (_, location) in zip(rto.WIIMM, located, strict=True):
        assert location is not None
        assert location.path.samefile(fake_tools_path.resolve(tool))
    results = probe_versions(
        [(spec, location) for spec, location in located if location is not None],
        cache=VersionCache(tmp_path / "versions.json"),
    )
    assert [result.location.version for result in results] == [VERSION] * 4
    calls = sorted((call["tool"], tuple(call["argv"])) for call in fake_tools_path.calls())
    assert calls == [(tool, ("version",)) for tool in sorted(rto.WIIMM)]


def test_wiimm_options_parse_like_getopt() -> None:
    assert fake_wiimm.VERSION == VERSION, "fakes imitate the catalogue pin"
    parsed = wiimm_cli.parse("wszst", VERSION, ["Create", "stage", "-dt.szs", "--compr=9", "-o"])
    assert parsed.command == "CREATE"
    assert parsed.positionals == ["stage"]
    assert parsed.options == {"--dest": "t.szs", "--compr": "9", "--overwrite": True}

    parsed = wiimm_cli.parse("wkmpt", VERSION, ["decode", "-D", "out/k.txt", "in.kmp", "-B"])
    assert parsed.options == {"--DEST": "out/k.txt", "--brief": True}
    assert parsed.positionals == ["in.kmp"]
