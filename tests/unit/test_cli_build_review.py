"""P4-GATE regressions for closed output and the human build summary."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from test_cli_build import WARN, Builds, no_gui, summary  # noqa: F401 - autouse fixture

from ctstudio.__main__ import main
from ctstudio.cli import build as cli_build
from ctstudio.core.build.events import BuildEvent, BuildFinished, BuildStarted, NodeFinished
from ctstudio.core.project.project import Project
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(name="root")
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    users = tmp_path / "users"
    for name in ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA"):
        monkeypatch.setenv(name, str(users / name))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(users / name))
    project = tmp_path / "Pistë 日本"
    Project.create(project, "Pistë", slot="castle_course").close()
    return project


@pytest.fixture(name="builds")
def fake_builds(monkeypatch: pytest.MonkeyPatch) -> Builds:
    return Builds(monkeypatch)


def test_a_closed_output_stops_the_build_quietly_and_exits_1(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``ctstudio build --json-events | head -1``: the reader goes, the build stops."""
    shown: list[BuildEvent] = []
    seen: list[CancelToken] = []

    def printer(_root: Path) -> Callable[[BuildEvent], None]:
        def show(event: BuildEvent) -> None:
            if shown:
                raise BrokenPipeError(32, "Broken pipe")
            shown.append(event)

        return show

    monkeypatch.setattr(cli_build, "_json_printer", printer)
    builds.during = seen.append
    builds.events = [
        BuildStarted(("stage:kcl",)),
        NodeFinished("stage:kcl", 0.1, ()),
        BuildFinished(summary(root=root, ran=("stage:kcl",), skipped=())),
    ]
    assert main(["build", str(root), "--json-events"]) == 1
    assert len(shown) == 1
    assert seen[0].cancelled, "the build was told to stop"
    assert capsys.readouterr().err == "The output was closed, so the build was stopped.\n"


def test_info_lines_are_counted_not_listed(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    info = Issue("info", "track", "WSZST_INFO", "Signature: WiimmSZS v2.42", None, "wszst check")
    builds.events = [
        BuildStarted(("validate",)),
        NodeFinished("validate", 0.1, (info, WARN, info)),
        BuildFinished(summary(root=root, ran=("validate",), skipped=(), issues=(info, WARN, info))),
    ]
    assert main(["build", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Signature" not in out
    assert (
        "Found while building:\n"
        "  warning  Missing bones 'posLD' and 'posRU' in minimap MDL.\n"
        "           Open map_model.brres in an editor and fix the reported problem.\n"
        "  and 2 notes for information, in the log.\n"
    ) in out


def test_one_info_note_is_said_in_the_singular(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deep Clean #1 step b: the summary split keeps "1 note" singular."""
    info = Issue("info", "track", "WSZST_INFO", "Signature: WiimmSZS v2.42", None, "wszst check")
    builds.events = [
        BuildStarted(("validate",)),
        NodeFinished("validate", 0.1, (info, WARN)),
        BuildFinished(summary(root=root, ran=("validate",), skipped=(), issues=(info, WARN))),
    ]
    assert main(["build", str(root)]) == 0
    assert "  and 1 note for information, in the log.\n" in capsys.readouterr().out


def test_only_info_notes_print_no_found_block(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deep Clean #1 step b review: no "Found while building" header without a finding."""
    info = Issue("info", "track", "WSZST_INFO", "Signature: WiimmSZS v2.42", None, "wszst check")
    builds.events = [
        BuildStarted(("validate",)),
        NodeFinished("validate", 0.1, (info,)),
        BuildFinished(summary(root=root, ran=("validate",), skipped=(), issues=(info,))),
    ]
    assert main(["build", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Found while building" not in out and "for information" not in out
    assert "\n\nBuild succeeded: 1 done in 0.5 s.\n" in out


def test_the_counts_keep_their_order(
    root: Path, builds: Builds, capsys: pytest.CaptureFixture[str]
) -> None:
    ended = summary(
        "failed",
        root=root,
        ran=("stage:kcl",),
        skipped=("stage:kmp",),
        failed=("assemble",),
        cancelled=("validate",),
        not_run=("stage:minimap",),
    )
    builds.events = [BuildStarted(("stage:kcl",)), BuildFinished(ended)]
    main(["build", str(root)])
    expected = "Build failed: 1 done, 1 unchanged, 1 failed, 1 cancelled, 1 not run in 0.5 s.\n"
    assert expected in capsys.readouterr().out
