"""P4-T07b: ``ctstudio build`` (``cli/build.py``) in-process, with the build itself stubbed.

``plan_build`` / ``build_project`` are replaced by fakes that record what they were given and
replay chosen events, so these tests pin the command's options, output, exit codes and
Ctrl+C handling. The real build of a real project, as a separate process, is in
``tests/integration/test_cli_build_real.py``.
"""

from __future__ import annotations

import _thread
import json
import sys
import threading
import time
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from json_schema_check import errors, schema_from_doc

from ctstudio.__main__ import main
from ctstudio.cli import build as cli_build
from ctstudio.core.build.events import (
    BuildEvent,
    BuildFinished,
    BuildStarted,
    BuildSummary,
    CommandRun,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.errors import ToolNotFound
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(60)
SCHEMA = schema_from_doc(
    Path(__file__).resolve().parents[2] / "docs" / "dev" / "CLI.md", "build-events-schema"
)
WARN = Issue(
    "warning",
    "minimap",
    "WSZST_WARNING",
    "Missing bones 'posLD' and 'posRU' in minimap MDL.",
    "Open map_model.brres in an editor and fix the reported problem.",
    "wszst check",
)


@pytest.fixture(autouse=True)
def no_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("ctstudio.gui.app")

    def run_gui(*_args: object) -> int:
        raise AssertionError("the GUI must not start")

    fake.run_gui = run_gui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctstudio.gui.app", fake)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    users = tmp_path / "users"
    for name in ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA"):
        monkeypatch.setenv(name, str(users / name))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(users / name))
    project = tmp_path / "Pistë 日本"
    Project.create(project, "Pistë", slot="castle_course").close()
    return project


def summary(outcome: str = "succeeded", root: Path | None = None, **kw: Any) -> BuildSummary:
    fields: dict[str, Any] = {
        "ran": ("stage:kcl", "assemble", "validate"),
        "skipped": ("stage:kmp",),
        "failed": (),
        "cancelled": (),
        "not_run": (),
        "issues": (),
        "duration": 0.512,
        "log": None if root is None else root / ".ctstudio" / "logs" / "build-1.log",
    }
    fields.update(kw)
    return BuildSummary(outcome, **fields)  # type: ignore[arg-type]


class Builds:
    """Stands in for plan_build / build_project; ``events`` are replayed, then returned."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.planned: list[dict[str, Any]] = []
        self.ran: list[dict[str, Any]] = []
        self.events: list[BuildEvent] = []
        self.during: Callable[[CancelToken], None] | None = None
        monkeypatch.setattr(cli_build, "plan_build", self._plan)
        monkeypatch.setattr(cli_build, "build_project", self._build)

    def _plan(self, root: Path, manifest: Manifest, profile: str, **kw: Any) -> Any:
        from ctstudio.core.build.graph import BuildGraph
        from ctstudio.core.build.project_build import BuildPlan
        from ctstudio.core.build.runner import BuildRequest

        self.planned.append({"root": root, "profile": profile, **kw})
        return BuildPlan(BuildGraph(root, []), BuildRequest(manifest, profile, {}, {}))  # type: ignore[arg-type]

    def _build(self, plan: Any, on_event: Callable[[BuildEvent], None], **kw: Any) -> Any:
        self.ran.append({"thread": threading.current_thread().name, **kw})
        if self.during is not None:
            self.during(kw["cancel"])
        for event in self.events:
            on_event(event)
        last = self.events[-1]
        assert isinstance(last, BuildFinished)
        return last.summary


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> Builds:
    return Builds(monkeypatch)


def test_a_test_build_of_this_folder_with_the_default_options(
    root: Path, builds: Builds, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(root)
    builds.events = [BuildFinished(summary(root=root))]
    assert main(["build"]) == 0
    [planned] = builds.planned
    assert planned == {
        "root": root.resolve(),
        "profile": "test",
        "only": None,
        "configured": {},
        "library": None,
    }
    [ran] = builds.ran
    assert ran["force"] is False and ran["thread"] == "ctstudio-build"
    assert capsys.readouterr().err == ""


def test_the_options_reach_the_build(root: Path, builds: Builds, tmp_path: Path) -> None:
    from ctstudio.core.project import settings

    wszst = tmp_path / "wszst.exe"
    library = tmp_path / "auto-add"
    saved = settings.UserSettings({"wszst": str(wszst)}).with_auto_add_library(library)
    settings.save(saved)
    builds.events = [BuildFinished(summary(root=root))]
    assert main(["build", str(root), "--release", "--force", "--only", "kcl"]) == 0
    [planned] = builds.planned
    assert planned["profile"] == "release" and planned["only"] == "kcl"
    assert planned["configured"] == {"wszst": wszst} and planned["library"] == library
    assert builds.ran[0]["force"] is True


def test_the_human_output(root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]) -> None:
    builds.events = [
        BuildStarted(("stage:kcl", "stage:kmp", "assemble", "validate")),
        NodeStarted("stage:kcl"),
        LogLine("assemble", "castle_course.szs: 2 files (fast compression), and the _d copy"),
        CommandRun("assemble", ("/t/wszst", "create"), "/t/wszst create"),  # disk log/JSON only
        NodeSkipped("stage:kmp", (WARN,)),
        NodeFinished("stage:kcl", 0.0204, ()),
        NodeFinished("assemble", 0.31, ()),
        NodeFinished("validate", 0.12, (WARN,)),
        BuildFinished(summary(root=root, issues=(WARN,))),
    ]
    assert main(["build", str(root)]) == 0
    assert capsys.readouterr().out == (
        "Building Pistë, replacing Mario Circuit (Flower Cup, track 1): test build, 4 steps\n"
        "  unchanged  Copy Course data\n"
        "  done       Copy Collision (0.02 s)\n"
        "  done       Pack the track (0.31 s)\n"
        "             castle_course.szs: 2 files (fast compression), and the _d copy\n"
        "  done       Check the track (0.12 s)\n"
        "\n"
        "Found while building:\n"
        "  warning  Missing bones 'posLD' and 'posRU' in minimap MDL.\n"
        "           Open map_model.brres in an editor and fix the reported problem.\n"
        "\n"
        "Build succeeded: 3 done, 1 unchanged in 0.5 s.\n"
        "Track: build/castle_course.szs\n"
        "Log: .ctstudio/logs/build-1.log\n"
    )


def test_a_failed_build_says_why_once_and_exits_1(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = Issue("error", "kcl", "STAGE_WRONG_TYPE", "course.kcl is a PNG.", "Choose a KCL.", "s")
    builds.events = [
        BuildStarted(("stage:kcl", "assemble")),
        LogLine("stage:kcl", "checking files/course.kcl"),
        NodeFailed("stage:kcl", stop.message, stop.hint, False, (stop,)),
        BuildFinished(
            summary(
                "failed",
                ran=(),
                skipped=(),
                failed=("stage:kcl",),
                not_run=("assemble",),
                issues=(stop, WARN),
                log=Path("/elsewhere/build.log"),
            )
        ),
    ]
    assert main(["build", str(root)]) == 1
    out = capsys.readouterr().out
    assert out.endswith(
        "  FAILED     Copy Collision\n"
        "             checking files/course.kcl\n"
        "             course.kcl is a PNG.\n"
        "             Choose a KCL.\n"
        "\n"
        "Found while building:\n"
        "  warning  Missing bones 'posLD' and 'posRU' in minimap MDL.\n"
        "           Open map_model.brres in an editor and fix the reported problem.\n"
        "\n"
        "Build failed: 1 failed, 1 not run in 0.5 s.\n"
        f"Log: {Path('/elsewhere/build.log')}\n"
    ), out
    assert out.count("course.kcl is a PNG.") == 1
    assert "Track:" not in out


def test_a_cancelled_build_exits_3_and_names_no_fix(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    builds.events = [
        NodeFailed("assemble", "Wiimm was cancelled.", "Run it again when ready.", True),
        BuildFinished(summary("cancelled", ran=(), skipped=(), cancelled=("assemble",))),
    ]
    assert main(["build", str(root)]) == 3
    out = capsys.readouterr().out
    assert "  cancelled  Pack the track\n             Wiimm was cancelled.\n" in out
    assert "Run it again" not in out
    assert "Build cancelled: 1 cancelled in 0.5 s." in out


def test_one_step_is_said_in_the_singular(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    builds.events = [BuildStarted(("stage:kcl",)), BuildFinished(summary(ran=("stage:kcl",)))]
    assert main(["build", str(root), "--only", "kcl"]) == 0
    assert ": test build, 1 step\n" in capsys.readouterr().out


def test_only_a_track_that_was_packed_is_named(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    builds.events = [BuildFinished(summary(ran=("stage:kcl",), skipped=()))]
    assert main(["build", str(root), "--only", "kcl"]) == 0
    out = capsys.readouterr().out
    assert "Build succeeded: 1 done in 0.5 s.\n" in out and "Track:" not in out
    builds.events = [BuildFinished(summary(ran=(), skipped=("assemble",)))]
    assert main(["build", str(root)]) == 0
    assert "Track: build/castle_course.szs" in capsys.readouterr().out


def test_json_events_prints_one_valid_line_per_event(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    builds.events = [
        BuildStarted(("stage:kcl",)),
        NodeStarted("stage:kcl"),
        LogLine("stage:kcl", "Pistë 日本"),
        CommandRun("stage:kcl", ("/t/wszst", "Pistë 日本"), "/t/wszst 'Pistë 日本'"),
        NodeFinished("stage:kcl", 0.02, (WARN,)),
        BuildFinished(summary(root=root, issues=(WARN,))),
    ]
    assert main(["build", str(root), "--json-events"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["event"] for line in lines] == [
        "build_started",
        "step_started",
        "log",
        "command",
        "step_finished",
        "build_finished",
    ]
    assert "Pistë 日本" in lines[2], "UTF-8 as is, not \\u escapes"
    assert all(errors(json.loads(line), SCHEMA) == [] for line in lines)


def test_ctrl_c_cancels_the_build_and_waits_for_it(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[bool] = []

    def interrupted(cancel: CancelToken) -> None:
        _thread.interrupt_main()  # as Ctrl+C: KeyboardInterrupt in the main thread
        deadline = time.monotonic() + 10
        while not cancel.cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        seen.append(cancel.cancelled)

    builds.during = interrupted
    builds.events = [BuildFinished(summary("cancelled", ran=(), cancelled=("assemble",)))]
    assert main(["build", str(root)]) == 3
    assert seen == [True], "the build saw the cancel, and was waited for"
    assert "Cancelling: running steps finish first." in capsys.readouterr().err


def test_an_error_inside_the_build_reaches_the_user(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_cancel: CancelToken) -> None:
        raise ToolNotFound("Wiimms SZS Tool", hint="Install it.")

    builds.during = broken
    assert main(["build", str(root)]) == 1
    assert "Wiimms SZS Tool was not found." in capsys.readouterr().err


def test_a_project_open_elsewhere_is_not_built(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    with Project.open(root):
        assert main(["build", str(root)]) == 1
    err = capsys.readouterr().err
    assert "This project is in use by CT Studio or another build, so it was not built." in err
    assert "Wait for that build to finish or close the project there, then build again." in err
    assert builds.planned == []


def test_a_folder_without_a_project_exits_1(
    tmp_path: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["build", str(tmp_path)]) == 1
    assert "ctstudio.toml" in capsys.readouterr().err


def test_a_missing_tool_stops_before_anything_runs(
    root: Path, builds: Builds, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(*_a: object, **_k: object) -> Any:
        raise ToolNotFound("Wiimms SZS Tool", hint="Install Wiimms SZS Tools.")

    monkeypatch.setattr(cli_build, "plan_build", missing)
    assert main(["build", str(root)]) == 1
    err = capsys.readouterr().err
    assert "Wiimms SZS Tool was not found." in err and builds.ran == []
    assert not (root / ".ctstudio" / "lock").exists(), "the lock is let go"


def test_a_wrong_part_is_a_usage_error(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["build", str(root), "--only", "objects"])
    assert caught.value.code == 2
    assert "invalid choice: 'objects'" in capsys.readouterr().err


def test_a_damaged_settings_file_is_reported_and_ignored(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    from ctstudio.core.project import settings

    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    builds.events = [BuildFinished(summary(root=root))]
    assert main(["build", str(root)]) == 0
    assert builds.planned[0]["configured"] == {}
    err = capsys.readouterr().err
    assert err.startswith("Warning: ") and "ignored for this build" in err
