"""P2-T06b: ``ctstudio setup rszst`` — the user-initiated route, with a dry run.

The installers are replaced by recording stubs; what is checked is the choice of route per
OS, the words printed before anything happens, Ctrl+C handling and the exit codes.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from ctstudio.__main__ import main
from ctstudio.cli import setup as cli_setup
from ctstudio.core.errors import Cancelled
from ctstudio.core.tools.rszst_install import SetupFailed
from ctstudio.core.tools.rszst_setup import PIN, Preflight, Toolchain

pytestmark = pytest.mark.timeout(60)
READY = Preflight((), (), 50 * 1024**3, Toolchain("clang", "clang++", None, None))
NOT_READY = Preflight(("cmake",), ("libssl-dev",), 50 * 1024**3)


@pytest.fixture(autouse=True)
def no_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("ctstudio.gui.app")

    def run_gui(*_args: object) -> int:
        raise AssertionError("the GUI was started")

    fake.run_gui = run_gui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctstudio.gui.app", fake)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, object]:
    calls: dict[str, object] = {"data": tmp_path / "data", "existing": None}
    monkeypatch.setattr(cli_setup, "_data_dir", lambda: calls["data"])
    monkeypatch.setattr(cli_setup, "_existing", lambda: calls["existing"])
    monkeypatch.setattr(cli_setup, "preflight", lambda target: calls.setdefault("preflight", READY))
    monkeypatch.setattr(cli_setup.os, "cpu_count", lambda: 8)

    def download(root: Path, **kwargs: object) -> Path:
        calls["download"] = (root, kwargs)
        return root / "rszst.exe"

    def build(root: Path, **kwargs: object) -> Path:
        calls["build"] = (root, kwargs)
        return root / "build/source/cli/rszst"

    monkeypatch.setattr(cli_setup, "download_windows", download)
    monkeypatch.setattr(cli_setup, "build_linux", build)
    return calls


def _on(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(cli_setup, "current_os", lambda: platform)


def test_windows_downloads_into_the_managed_folder(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "windows")
    assert main(["setup", "rszst"]) == 0
    root, kwargs = world["download"]  # type: ignore[misc]
    assert root == Path(world["data"]) / "tools" / "riistudio-5.11.5"  # type: ignore[arg-type]
    assert set(kwargs) == {"cancel", "on_progress"}
    out = capsys.readouterr().out
    assert PIN.windows_zip_url in out and "44 MB" in out
    assert "never bundled" in out
    assert f"Installed: {root / 'rszst.exe'}" in out


def test_linux_builds_with_one_job_per_two_cores(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    assert main(["setup", "rszst"]) == 0
    root, kwargs = world["build"]  # type: ignore[misc]
    assert kwargs["jobs"] == 4 and kwargs["preflight_result"] is READY  # type: ignore[index]
    out = capsys.readouterr().out
    assert "about 1 hour" in out and "Ctrl+C" in out and str(root / "build.log") in out
    assert PIN.source_commit in out


def test_jobs_can_be_chosen(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    assert main(["setup", "rszst", "--jobs", "1"]) == 0
    assert world["build"][1]["jobs"] == 1  # type: ignore[index]
    capsys.readouterr()


def test_a_dry_run_only_explains(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for platform in ("windows", "linux"):
        _on(monkeypatch, platform)
        assert main(["setup", "rszst", "--dry-run"]) == 0
    assert "download" not in world and "build" not in world
    out = capsys.readouterr().out
    assert "Nothing was changed (dry run)." in out
    assert "git clone --branch Alpha-5.11.5" in out  # the exact recipe is shown
    assert "-DRust_CARGO=" not in out  # READY found Rust on PATH


def test_a_dry_run_on_an_unready_machine_shows_the_expected_toolchain(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    world["preflight"] = NOT_READY
    main(["setup", "rszst", "--dry-run"])
    out = capsys.readouterr().out
    assert "-DCMAKE_C_COMPILER=clang-19" in out and "-DRust_CARGO=" in out and "rust-1.85" in out


def test_a_dry_run_shows_what_is_missing(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    world["preflight"] = NOT_READY
    assert main(["setup", "rszst", "--dry-run"]) == 1
    out = capsys.readouterr().out
    assert "Missing programs: cmake" in out and "sudo apt install -y" in out


def test_an_existing_rszst_is_left_alone(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    world["existing"] = Path("/usr/local/bin/rszst")
    assert main(["setup", "rszst"]) == 0
    assert "build" not in world
    assert "already installed: /usr/local/bin/rszst" in capsys.readouterr().out


def test_a_failure_prints_the_reason_and_exits_1(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "windows")

    def broken(root: Path, **_kwargs: object) -> Path:
        raise SetupFailed("The RiiStudio download did not match.", hint="Nothing was installed.")

    monkeypatch.setattr(cli_setup, "download_windows", broken)
    assert main(["setup", "rszst"]) == 1
    err = capsys.readouterr().err
    assert "did not match" in err and "Next: Nothing was installed." in err


def test_ctrl_c_cancels_cleanly(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    seen: list[object] = []

    def interrupted(root: Path, **kwargs: object) -> Path:
        seen.append(kwargs["cancel"])
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_setup, "build_linux", interrupted)
    assert main(["setup", "rszst"]) == 130
    assert seen and seen[0].cancelled  # type: ignore[attr-defined]
    assert "cancelled" in capsys.readouterr().err


def test_a_cancel_from_the_installer_exits_130(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "windows")

    def stopped(root: Path, **_kwargs: object) -> Path:
        raise Cancelled("Downloading RiiStudio")

    monkeypatch.setattr(cli_setup, "download_windows", stopped)
    assert main(["setup", "rszst"]) == 130
    capsys.readouterr()


def test_other_systems_are_told_plainly(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "other")
    assert main(["setup", "rszst"]) == 1
    assert "on only Windows and Linux" in capsys.readouterr().err


def test_progress_and_build_lines_are_printed(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _on(monkeypatch, "linux")
    assert main(["setup", "rszst"]) == 0
    kwargs = world["build"][1]  # type: ignore[index]
    from ctstudio.core.tools.rszst_setup import Step

    kwargs["on_step"](2, 6, Step("Configure", ("cmake",), Path("."), 1))  # type: ignore[index]
    kwargs["on_line"]("stdout", "[ 42%] Building CXX object")  # type: ignore[index]
    out = capsys.readouterr().out
    assert "Step 2 of 6: Configure" in out and "[ 42%] Building CXX object" in out


def test_download_progress_is_in_megabytes(capsys: pytest.CaptureFixture[str]) -> None:
    cli_setup._progress(21_804_582, 43_609_164)
    assert capsys.readouterr().out == "\r  21.8 of 43.6 MB"
    cli_setup._progress(43_609_164, 43_609_164)
    assert capsys.readouterr().out == "\r  43.6 of 43.6 MB\n"


def test_only_a_users_own_rszst_counts_as_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    from ctstudio.core.tools.discovery import ToolLocation

    for source, expected in [("path", Path("/bin/rszst")), ("managed", None)]:
        location = ToolLocation(Path("/bin/rszst"), None, source, "direct")  # type: ignore[arg-type]
        monkeypatch.setattr(cli_setup, "discover", lambda _spec, _l=location: _l)
        assert cli_setup._existing() == expected
    monkeypatch.setattr(cli_setup, "discover", lambda _spec: None)
    assert cli_setup._existing() is None


def test_setup_help_names_the_tool(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["setup", "--help"])
    out = capsys.readouterr().out
    assert "rszst" in out and "--dry-run" in out and "--jobs" in out
