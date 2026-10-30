"""P2-T06b/c: ``rszst_install.build_linux`` — the Linux source build as six runner steps.

The real ``process.run`` is replaced by a stand-in that enforces the same rule (the program
must be an absolute path), records each step and creates the executable at the end; program
lookup is a stub, so these run on any OS. A build only counts once ``setup.json`` is written.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from version_fakes import fake_executable

from ctstudio.core.errors import Cancelled, ToolFailed
from ctstudio.core.tools.process import CancelToken, RunResult
from ctstudio.core.tools.rszst_install import SetupFailed, build_linux
from ctstudio.core.tools.rszst_setup import Preflight, SetupRecord, Toolchain, read_record

pytestmark = pytest.mark.timeout(60)
BANNER = "RiiStudio Parser 1.0\nRiiStudio CLI Alpha 5.11.5 (Built May 22 2025, Clang 19.1.5)"


def _banner(text: str = BANNER) -> Callable[[Path], str]:
    return lambda _exe: text


# --- Linux build ---------------------------------------------------------------------------------


READY = Preflight((), (), 50 * 1024**3, Toolchain("clang", "clang++", None, None))


BIN = Path(os.path.abspath("/usr/bin"))  # absolute on both OSes ("C:\\usr\\bin" on Windows)


def which_bin(cmd: str, mode: int = 0, path: str | None = None) -> str | None:
    return str(BIN / cmd)


class Runner:
    """Stands in for ``process.run``: records each step and creates the executable at the end."""

    def __init__(self, fail_at: int | None = None, cancel_at: int | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_at, self.cancel_at = fail_at, cancel_at

    def __call__(self, cmd: Sequence[str | Path], **kwargs: Any) -> RunResult:
        # The real process.run refuses a bare program name; so does this stand-in.
        if not Path(str(cmd[0])).is_absolute():
            raise ValueError("cmd[0] must be an absolute executable path from tool discovery")
        index = len(self.calls)
        self.calls.append({"argv": tuple(str(c) for c in cmd), **kwargs})
        if index == self.cancel_at:
            raise Cancelled("cmake")
        if index == self.fail_at:
            raise ToolFailed([str(c) for c in cmd], 2, "error: no memory header", None)
        if Path(str(cmd[0])).name == "cmake" and cmd[1] == "--build":
            exe = Path(str(cmd[2])) / "source" / "cli" / "rszst"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"\x7fELF")
        return RunResult(0, 0.1, "", "", None)


def test_the_build_runs_every_step_logs_and_records(tmp_path: Path) -> None:
    root = tmp_path / "riistudio-5.11.5"
    runner, lines, started = Runner(), list[str](), list[str]()
    exe = build_linux(
        root,
        jobs=2,
        which=which_bin,
        preflight_result=READY,
        runner=runner,
        banner=_banner(),
        on_step=lambda n, total, step: started.append(f"{n}/{total} {step.name}"),
        on_line=lambda stream, line: lines.append(line),
    )
    assert exe == root / "build" / "source" / "cli" / "rszst"
    assert read_record(root) == SetupRecord("build", "5.11.5", "build/source/cli/rszst")
    assert started[0] == "1/6 Download RiiStudio source" and started[-1].startswith("6/6 Compile")
    build = str(root / "build")
    assert runner.calls[-1]["argv"] == (
        str(BIN / "cmake"),
        "--build",
        build,
        "--target",
        "cli",
        "--parallel",
        "2",
    )
    for call in runner.calls:
        assert call["log_path"] == root / "build.log"
        assert call["cwd"] == root and call["check"] is True
        assert call["cancel"] is None and call["on_line"] is not None
    assert runner.calls[-1]["env"] == {"CXXFLAGS": "-include memory"}
    assert runner.calls[-1]["timeout"] == 4 * 3600


def test_the_build_uses_the_toolchain_preflight_found(tmp_path: Path) -> None:
    rust = Path("/usr/lib/rust-1.85/bin")
    found = Preflight((), (), 50 * 1024**3, Toolchain("clang-19", "clang++-19", rust, (1, 85)))
    runner = Runner()
    build_linux(
        tmp_path / "r",
        jobs=1,
        which=which_bin,
        preflight_result=found,
        runner=runner,
        banner=_banner(),
    )
    configure = cast("tuple[str, ...]", runner.calls[4]["argv"])
    assert "-DCMAKE_C_COMPILER=clang-19" in configure
    assert f"-DRust_CARGO={rust / 'cargo'}" in configure


def test_build_programs_are_found_on_each_steps_own_path(tmp_path: Path) -> None:
    rust = Path(os.path.abspath("/usr/lib/rust-1.85/bin"))
    found = Preflight((), (), 50 * 1024**3, Toolchain("clang-19", "clang++-19", rust, (1, 85)))
    searched: list[tuple[str, str | None]] = []

    def which(cmd: str, mode: int = 0, path: str | None = None) -> str | None:
        searched.append((cmd, path))
        return str(BIN / cmd)

    runner = Runner()
    build_linux(tmp_path / "r", jobs=1, preflight_result=found, runner=runner, banner=_banner(),
                which=which)  # fmt: skip
    assert [cmd for cmd, _ in searched] == ["git", "git", "git", "git", "cmake", "cmake"]
    assert searched[0][1] == os.environ.get("PATH", "")
    assert all(path is not None and path.startswith(str(rust)) for _, path in searched[4:])
    programs = [cast("tuple[str, ...]", call["argv"])[0] for call in runner.calls]
    assert programs == [str(BIN / "git")] * 4 + [str(BIN / "cmake")] * 2


def test_a_build_program_that_cannot_be_found_stops_before_running_it(tmp_path: Path) -> None:
    runner = Runner()

    def which(cmd: str, mode: int = 0, path: str | None = None) -> str | None:
        return None if cmd == "cmake" else str(BIN / cmd)

    with pytest.raises(SetupFailed, match="needs “cmake”") as caught:
        build_linux(tmp_path / "r", jobs=1, preflight_result=READY, runner=runner,
                    banner=_banner(), which=which)  # fmt: skip
    assert len(runner.calls) == 4  # the four git steps ran; cmake never started
    assert caught.value.hint is not None and "sudo apt install -y" in caught.value.hint
    assert read_record(tmp_path / "r") is None


def test_the_build_refuses_to_start_when_preflight_fails(tmp_path: Path) -> None:
    root = tmp_path / "riistudio-5.11.5"
    runner = Runner()
    not_ready = Preflight(("cmake",), ("libssl-dev",), 50 * 1024**3)
    with pytest.raises(SetupFailed) as caught:
        build_linux(
            root,
            jobs=2,
            which=which_bin,
            preflight_result=not_ready,
            runner=runner,
            banner=_banner(),
        )
    assert runner.calls == [] and not root.exists()
    assert "cmake" in caught.value.user_message and "sudo apt install" in (caught.value.hint or "")


def test_a_failed_step_keeps_the_log_and_names_the_step(tmp_path: Path) -> None:
    root = tmp_path / "riistudio-5.11.5"
    with pytest.raises(SetupFailed) as caught:
        build_linux(
            root,
            jobs=2,
            which=which_bin,
            preflight_result=READY,
            runner=Runner(fail_at=4),
            banner=_banner(),
        )
    assert "Configure" in caught.value.user_message
    assert str(root / "build.log") in (caught.value.hint or "")
    assert read_record(root) is None and root.is_dir()  # kept for the log; not a setup


def test_a_cancelled_build_is_not_a_setup(tmp_path: Path) -> None:
    root = tmp_path / "riistudio-5.11.5"
    token = CancelToken()
    with pytest.raises(Cancelled):
        build_linux(
            root,
            jobs=1,
            which=which_bin,
            preflight_result=READY,
            runner=Runner(cancel_at=5),
            banner=_banner(),
            cancel=token,
        )
    assert read_record(root) is None


def test_the_cancel_token_reaches_every_step(tmp_path: Path) -> None:
    token, runner = CancelToken(), Runner()
    build_linux(
        tmp_path / "r",
        jobs=1,
        which=which_bin,
        preflight_result=READY,
        runner=runner,
        banner=_banner(),
        cancel=token,
    )
    assert all(call["cancel"] is token for call in runner.calls)


def test_a_build_without_the_executable_fails(tmp_path: Path) -> None:
    class NoOutput(Runner):
        def __call__(self, cmd: Sequence[str | Path], **kwargs: Any) -> RunResult:
            self.calls.append({"argv": tuple(str(c) for c in cmd)})
            return RunResult(0, 0.1, "", "", None)

    root = tmp_path / "r"
    with pytest.raises(SetupFailed, match="no rszst"):
        build_linux(
            root,
            jobs=1,
            which=which_bin,
            preflight_result=READY,
            runner=NoOutput(),
            banner=_banner(),
        )
    assert read_record(root) is None


def test_a_built_rszst_with_the_wrong_banner_fails(tmp_path: Path) -> None:
    root = tmp_path / "r"
    with pytest.raises(SetupFailed, match=r"5\.11\.5"):
        build_linux(
            root,
            jobs=1,
            which=which_bin,
            preflight_result=READY,
            runner=Runner(),
            banner=_banner("odd"),
        )
    assert read_record(root) is None


def test_a_previous_partial_build_is_cleared_first(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "source").mkdir(parents=True)
    (root / "source" / "stale").write_text("x", encoding="utf-8")
    build_linux(
        root, jobs=1, which=which_bin, preflight_result=READY, runner=Runner(), banner=_banner()
    )
    assert not (root / "source" / "stale").exists()


def test_a_finished_build_is_not_repeated(tmp_path: Path) -> None:
    root = tmp_path / "r"
    build_linux(
        root, jobs=1, which=which_bin, preflight_result=READY, runner=Runner(), banner=_banner()
    )
    again = Runner()
    build_linux(
        root, jobs=1, which=which_bin, preflight_result=READY, runner=again, banner=_banner()
    )
    assert again.calls == []


def test_the_real_runner_accepts_the_steps_and_reports_a_failing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression (Mint, 2026-10-30): bare "git" reached ``process.run``, which raised ValueError.

    Real ``shutil.which`` and real ``process.run``: a fake ``git`` (a Python interpreter, so
    ``git clone ...`` exits 2) on PATH must surface as a setup failure at step 1.
    """
    git = fake_executable(tmp_path / "bin", "git")
    monkeypatch.setenv("PATH", str(git.parent))
    root = tmp_path / "riistudio-5.11.5"
    with pytest.raises(SetupFailed, match="failed at step “Download RiiStudio source”"):
        build_linux(root, jobs=1, preflight_result=READY, banner=_banner())
    assert (root / "build.log").is_file()
    assert read_record(root) is None
