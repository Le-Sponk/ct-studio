"""P2-T06: ``ctstudio doctor`` on the command line (``ctstudio.cli.doctor``).

The text layout is pinned by an exact snapshot built from a fixed report, so a change to
column widths or wording is a deliberate test edit. ``--json`` is plain data for scripts.
Exit 0 unless a required tool is missing, too old or not working (exit 1).
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from ctstudio.__main__ import main
from ctstudio.cli import doctor as cli_doctor
from ctstudio.cli.doctor import render
from ctstudio.core.tools.doctor import Report, ToolCheck

pytestmark = pytest.mark.timeout(60)

REPORT = Report(
    "windows",
    (
        ToolCheck(
            "wszst",
            "Wiimms SZS Tool",
            "found",
            True,
            "SZS assembly, validation and analysis",
            version="2.42a",
            path=Path("C:/Tools/Wiimm é/wszst.exe"),
            launcher="direct",
            source="path",
        ),
        ToolCheck(
            "rszst",
            "RiiStudio CLI",
            "missing",
            False,
            "BRRES import and material presets",
            fix="Install RiiStudio CLI from https://github.com/snailspeed3/RiiStudio/releases.",
        ),
        ToolCheck(
            "brawlcrate",
            "BrawlCrate",
            "found",
            False,
            "Manual BRRES editing",
            path=Path("C:/Editors/BrawlCrate/BrawlCrate.exe"),
            launcher="direct",
            source="standard",
        ),
        ToolCheck(
            "wine",
            "Wine",
            "not_needed",
            False,
            "Running Windows-only editors on Linux",
            note="Only used on Linux.",
        ),
    ),
)

SNAPSHOT = """\
CT Studio doctor (windows)

Tool             Status      Version  Used for
---------------  ----------  -------  -------------------------------------
Wiimms SZS Tool  found       2.42a    SZS assembly, validation and analysis
    path: C:/Tools/Wiimm é/wszst.exe (direct, from PATH)
RiiStudio CLI    missing     -        BRRES import and material presets
    fix: Install RiiStudio CLI from https://github.com/snailspeed3/RiiStudio/releases.
BrawlCrate       found       -        Manual BRRES editing
    path: C:/Editors/BrawlCrate/BrawlCrate.exe (direct, standard location)
Wine             not needed  -        Running Windows-only editors on Linux
    note: Only used on Linux.

All required tools are ready (required: Wiimms SZS Tool).
"""


def test_text_report_matches_the_snapshot() -> None:
    assert render(REPORT) == SNAPSHOT


def test_a_missing_required_tool_is_called_out_at_the_end() -> None:
    broken = Report(
        "linux",
        (
            ToolCheck(
                "wszst",
                "Wiimms SZS Tool",
                "missing",
                True,
                "SZS assembly",
                fix="Install Wiimms SZS Tool from https://szs.wiimm.de/download/.",
            ),
        ),
    )
    text = render(broken)
    assert text.startswith("CT Studio doctor (linux)\n")
    assert text.endswith(
        "\nCT Studio cannot build tracks until these are fixed: Wiimms SZS Tool.\n"
    )


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("too_old", "too old"),
        ("not_working", "not working"),
        ("needs_wine", "needs Wine"),
        ("sandboxed", "sandboxed"),
    ],
)
def test_every_status_has_a_plain_label(status: str, label: str) -> None:
    check = ToolCheck("x", "X", status, False, "y")  # type: ignore[arg-type]
    row = render(Report("linux", (check,))).splitlines()[4]
    assert row.split("  ")[0] == "X"
    assert f"  {label}  " in row


def test_sources_are_described_in_words() -> None:
    for source, words in [
        ("path", "from PATH"),
        ("standard", "standard location"),
        ("setting", "your setting"),
        ("dev", "developer copy in .tools"),
        ("flatpak", "Flatpak"),
        ("managed", "installed by CT Studio"),
    ]:
        check = ToolCheck(
            "x", "X", "found", False, "y", path=Path("/p/x"), launcher="direct", source=source
        )
        assert f"(direct, {words})" in render(Report("linux", (check,)))


@pytest.mark.parametrize(
    ("route", "words"),
    [("download", "downloaded by CT Studio"), ("build", "built from source by CT Studio")],
)
def test_a_managed_rszst_says_how_it_was_installed(route: str, words: str) -> None:
    check = ToolCheck(
        "rszst", "RiiStudio CLI", "found", False, "y", path=Path("/d/rszst"),
        launcher="direct", source="managed", route=route,
    )  # fmt: skip
    assert f"(direct, {words})" in render(Report("linux", (check,)))


# --- the subcommand -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail at once, instead of opening a window, if ``doctor`` ever falls through to the GUI."""
    fake = types.ModuleType("ctstudio.gui.app")

    def run_gui(*_args: object) -> int:
        raise AssertionError("the GUI was started")

    fake.run_gui = run_gui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctstudio.gui.app", fake)


@pytest.fixture
def diagnosed(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> Report:
        calls.append(kwargs)
        return REPORT

    monkeypatch.setattr(cli_doctor, "diagnose", fake)
    return calls


def test_doctor_prints_the_table_and_exits_0(
    diagnosed: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["doctor"]) == 0
    assert capsys.readouterr().out == SNAPSHOT
    assert diagnosed == [{"force": False}]


def test_recheck_forces_new_version_probes(
    diagnosed: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["doctor", "--recheck"]) == 0
    assert diagnosed == [{"force": True}]
    capsys.readouterr()


def test_json_output_is_the_report_data(
    diagnosed: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["doctor", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == json.loads(json.dumps(REPORT.to_json()))
    assert data["tools"][0]["path"] == str(Path("C:/Tools/Wiimm é/wszst.exe"))


@pytest.mark.parametrize("status", ["missing", "too_old", "not_working"])
def test_a_required_tool_problem_exits_1(
    status: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = Report("windows", (ToolCheck("wszst", "Wiimms SZS Tool", status, True, "x"),))  # type: ignore[arg-type]
    monkeypatch.setattr(cli_doctor, "diagnose", lambda **_k: bad)
    assert main(["doctor"]) == 1
    assert "cannot build tracks" in capsys.readouterr().out
    assert main(["doctor", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_the_verdict_names_only_the_broken_required_tools() -> None:
    report = Report(
        "linux",
        (
            ToolCheck("wszst", "Wiimms SZS Tool", "found", True, "x"),
            ToolCheck("wkclt", "Wiimms KCL Tool", "too_old", True, "y"),
        ),
    )
    assert render(report).endswith(
        "\nCT Studio cannot build tracks until these are fixed: Wiimms KCL Tool.\n"
    )


def test_optional_tool_problems_still_exit_0(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = Report(
        "linux",
        (
            ToolCheck("wszst", "Wiimms SZS Tool", "found", True, "x"),
            ToolCheck("blender", "Blender", "missing", False, "y"),
            ToolCheck("brawlcrate", "BrawlCrate", "needs_wine", False, "z"),
        ),
    )
    monkeypatch.setattr(cli_doctor, "diagnose", lambda **_k: report)
    assert main(["doctor"]) == 0
    capsys.readouterr()


def test_doctor_help_lists_its_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["doctor", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--json" in out and "--recheck" in out


def test_doctor_does_not_import_qt(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "from ctstudio.cli import doctor\n"
        "doctor.diagnose = lambda **k: doctor.Report('linux', ())\n"
        "from ctstudio.__main__ import main\n"
        "rc = main(['doctor', '--json'])\n"
        "assert rc == 0, rc\n"
        "assert not any(m.startswith('PySide6') for m in sys.modules), 'Qt imported'\n"
        "assert 'ctstudio.gui' not in sys.modules\n"
    )
    result = subprocess.run(  # noqa: S603 - our own interpreter
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=50, check=False
    )
    assert result.returncode == 0, result.stderr
