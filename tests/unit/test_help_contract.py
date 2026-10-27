"""P2-T04a: every verified argv template uses flags the pinned tool's recorded help lists."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "fakes"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tool_catalogue as tc
from help_contract import (
    RECORDINGS,
    Contract,
    ContractError,
    load_contract,
    parse_abmatt,
    parse_blender,
    parse_clap,
    parse_wiimm,
    verified_templates,
)

pytestmark = pytest.mark.timeout(10)

TOOLS_MD = REPO_ROOT / "docs" / "reference" / "TOOLS.md"
PINS = {
    "wszst": tc.ALL_TOOLS["wiimms-szs-tools"].version,
    "wkclt": tc.ALL_TOOLS["wiimms-szs-tools"].version,
    "wkmpt": tc.ALL_TOOLS["wiimms-szs-tools"].version,
    "wimgt": tc.ALL_TOOLS["wiimms-szs-tools"].version,
    "rszst": tc.ALL_TOOLS["riistudio"].version,
    "abmatt": tc.ALL_TOOLS["abmatt"].version,
    "blender": tc.ALL_TOOLS["blender"].version,
}
# Invocations verified by real runs but described in TOOLS.md prose, not in a table:
# the Blender add-on's KCL encode (P0-T03) and the measured compression flags (P0-T04).
PROSE_TEMPLATES = [
    "wkclt encode TMP --dest OUT -o --kcl=MEDIUM --kcl-script=SCRIPT --const lower=30,degree=45,",
    "wszst create DIR --dest OUT.szs --overwrite --no-compress",
    "wszst create DIR --dest OUT.szs --overwrite --fast",
    "wszst create DIR -D OUT.szs --overwrite --auto-add",
    "wszst check FILE.szs -B",
    "blender -b --factory-startup --python SCRIPT -- --project DIR",
]


def contract(tool: str) -> Contract:
    return load_contract(tool, PINS[tool])


def test_wiimm_option_tables_list_short_and_long_flags_only() -> None:
    help_text = (
        "wszst CREATE|C : Create SZS archives.\n\nOptions:\n\n"
        "     --no-wildcards     Disable wildcard parsing.\n"
        "  -d --dest path        Define a destination path; see also\n"
        "                        --number and --overwrite.\n"
        "     --colors=[=modus]  Define the modus.\n"
        "  -C --compr level      Define a compression level.\n"
    )
    flags = parse_wiimm(help_text)
    assert flags == {"--no-wildcards", "-d", "--dest", "--colors", "-C", "--compr"}


def test_clap_abmatt_and_blender_help_formats() -> None:
    clap = (
        "Usage: rszst.exe import-brres [OPTIONS] <FROM> [TO]\n\nArguments:\n"
        "  <FROM>  File to import from\n\nOptions:\n"
        "  -s, --scale <SCALE>              Scale [default: 1.0]\n"
        "      --mipmaps                    Whether to generate mipmaps\n"
        "  -h, --help                       Print help\n"
    )
    assert parse_clap(clap) == {"-s", "--scale", "--mipmaps", "-h", "--help"}
    abmatt = (
        "| -a | --auto-fix | Set the autofix level. |\n"
        "| -l | --loudness | Sets the verbosity level. (0-5)\n"
        "|   | --moonview | Treat the Brres as Moonview course. |\n"
        "USAGE: abmatt [command_line][--interactive -f <file>]\n"
    )
    assert parse_abmatt(abmatt) == {"-a", "--auto-fix", "-l", "--loudness", "--moonview"}
    blender = (
        "Blender 5.2.2 LTS\nUsage: blender [args ...] [file] [args ...]\n\n"
        "-b or --background \n\tRun in background, see -setaudio.\n\n"
        "--python-expr <expression>\n\tRun the given expression.\n\n"
        "-setaudio\n\tSet the audio device.\n"
    )
    assert parse_blender(blender) == {"-b", "--background", "--python-expr", "-setaudio"}


def test_recordings_are_stored_under_the_pinned_versions() -> None:
    for tool, version in PINS.items():
        folder = RECORDINGS / tool / version
        assert folder.is_dir(), f"{tool}: no recording for pinned {version}"
        loaded = contract(tool)
        assert loaded.version == version
    versions = {path.name for path in (RECORDINGS / "wszst").iterdir()}
    assert versions == {PINS["wszst"]}, "stale recording folders must be removed on a bump"


def test_recordings_hold_no_local_paths_or_carriage_returns() -> None:
    home = str(Path.home())
    for path in RECORDINGS.glob("*/*/*-help.json"):
        text = path.read_text(encoding="utf-8")
        records = json.loads(text)
        assert records and all({"argv", "exit_code", "stdout", "stderr"} <= set(r) for r in records)
        for record in records:
            output = record["stdout"] + record["stderr"]
            assert "\r" not in output, path
            assert home not in output and home.replace("\\", "/") not in output, path


def test_templates_are_read_from_every_argv_table_including_optional_flags() -> None:
    markdown = (
        "| Tool | Operation | Exact argv template | Exit codes |\n"
        "|---|---|---|---|\n"
        "| wszst | check | `wszst check FILE.szs [--brief]` | 2 |\n"
        "\nprose with `wszst fake --nope` is ignored\n\n"
        "| Tool | Exact argv template |\n|---|---|\n"
        "| rszst | `rszst import-brres IN OUT [--mipmaps --min-mip N]` |\n"
    )
    assert verified_templates(markdown) == [
        "wszst check FILE.szs --brief",
        "rszst import-brres IN OUT --mipmaps --min-mip N",
    ]


def test_every_verified_template_uses_only_recorded_flags() -> None:
    templates = [*verified_templates(TOOLS_MD.read_text(encoding="utf-8")), *PROSE_TEMPLATES]
    checked = 0
    for template in templates:
        tool, *args = template.split()
        if tool not in PINS:
            continue
        assert contract(tool).unknown_flags(args) == [], template
        checked += 1
    assert checked >= 30, f"only {checked} templates checked; did the TOOLS.md tables move?"


@pytest.mark.parametrize(
    ("template", "unknown"),
    [
        ("wszst create DIR --dest OUT.szs --compression=BEST", ["--compression"]),
        ("wkmpt encode SRC.txt --dset OUT.kmp --overwrite", ["--dset"]),
        ("rszst import-brres IN.dae OUT.brres --mip-maps", ["--mip-maps"]),
        ("abmatt -b FILE.brres --cmd info", ["--cmd"]),
        ("blender --backgroud --factory-startup", ["--backgroud"]),
    ],
)
def test_a_misspelled_flag_is_reported(template: str, unknown: list[str]) -> None:
    tool, *args = template.split()
    assert contract(tool).unknown_flags(args) == unknown


def test_a_flag_from_another_subcommand_is_reported() -> None:
    # --mipmaps exists for import-brres only; --json is analyze's, not list's.
    assert contract("rszst").unknown_flags(["brres-to-json", "IN", "OUT", "--mipmaps"]) == [
        "--mipmaps"
    ]
    assert contract("wszst").unknown_flags(["list", "--json", "FILE.szs"]) == ["--json"]
    assert contract("wszst").unknown_flags(["analyze", "--json", "FILE.szs"]) == []


def test_an_unrecorded_subcommand_is_an_error_not_a_pass() -> None:
    with pytest.raises(ContractError, match="no recorded help for 'wszst extract'"):
        contract("wszst").unknown_flags(["extract", "FILE.szs", "--dest", "DIR"])


def test_arguments_after_a_double_dash_are_not_flags() -> None:
    args = ["-b", "--python", "SCRIPT", "--", "--anything", "-x"]
    assert contract("blender").unknown_flags(args) == []
