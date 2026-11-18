"""P5-T07d3: application service guards and launch-only editor wording on the joined owner."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from editor_owner_helpers import BUILTIN, CUSTOM, Results, outcome, snapshot_for
from editor_request_helpers import owned_editors, settled
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import ProjectError, ToolNotFound
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.editor_launch import PreparedEditors
from ctstudio.gui.launch_controller import THREAD_NAME, LaunchResult, Receipt
from ctstudio.gui.launch_text import describe_editor, describe_launch

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def refused(call: object) -> ProjectError:
    """The typed refusal a request raised (asserted, never a bare raise or pytest.fail)."""
    assert callable(call)
    error = outcome(call)
    assert isinstance(error, ProjectError), f"expected a ProjectError refusal, got {error!r}"
    assert error.hint, "every refusal says what to do next"
    return error


def prepared(qtbot: QtBot, results: Results, count: int) -> PreparedEditors:
    assert settled(qtbot, lambda: len(results.items) >= count and not results.owner.busy)
    receipt = results.items[-1].receipt
    assert isinstance(receipt, PreparedEditors), f"no preparation receipt: {results.items[-1]!r}"
    return receipt


def test_service_requests_run_joined_on_the_owner_for_the_current_project(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        assert settled(qtbot, lambda: not services.status.busy)
        results = Results(services.launch)
        assert outcome(lambda: services.start_prepare_editors(document)) is True
        assert services.launch.busy, "owned from the moment it starts"
        assert work.entered.wait(5)
        work.gate.set()
        receipt = prepared(qtbot, results, 1)
        assert receipt is work.snapshots[-1]
        assert results.threads[-1] is threading.main_thread(), "delivered on the UI thread"
        assert outcome(lambda: services.start_open_editor(receipt, CUSTOM)) is True
        assert settled(qtbot, lambda: len(results.items) == 2 and not services.launch.busy)
        opened = results.items[-1]
        assert opened.receipt is work.launched and opened.choice == CUSTOM
        assert opened.project is project and opened.root == project.root
        kinds = [(call[0], call[1], call[2], call[3]) for call in work.calls]
        assert kinds == [("prepare", project, document, None), ("open", project, document, CUSTOM)]
        assert {call[4].name for call in work.calls} == {THREAD_NAME}


def test_memory_only_refusals_start_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_editors(tmp_path) as (services, _project, document, work, _other):
        snapshot = snapshot_for(document)
        checking = refused(lambda: services.start_prepare_editors(document))
        assert "checked" in checking.user_message  # the first status check still runs
        checking = refused(lambda: services.start_open_editor(snapshot, BUILTIN))
        assert "checked" in checking.user_message
        assert settled(qtbot, lambda: not services.status.busy)
        services.editing = True
        assert "details" in refused(lambda: services.start_prepare_editors(document)).user_message
        assert (
            "details" in refused(lambda: services.start_open_editor(snapshot, BUILTIN)).user_message
        )
        services.editing = False
        assert not work.calls and not services.launch.busy
        services.close_project()
        assert (
            "No project" in refused(lambda: services.start_prepare_editors(document)).user_message
        )
        assert (
            "No project"
            in refused(lambda: services.start_open_editor(snapshot, BUILTIN)).user_message
        )
        assert not work.calls and not services.launch.busy


def test_a_busy_owner_refuses_every_request_and_keeps_the_project(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, other):
        assert settled(qtbot, lambda: not services.status.busy)
        assert outcome(lambda: services.start_launch("kcl")) is True
        assert other.entered.wait(5)
        busy = refused(lambda: services.start_prepare_editors(document))
        assert "still finishing" in busy.user_message and "editor" in busy.user_message
        snapshot = snapshot_for(document)
        assert (
            "still finishing"
            in refused(lambda: services.start_open_editor(snapshot, BUILTIN)).user_message
        )
        assert not work.calls
        other.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy)
        assert services.project is project and not project.read_only


def test_a_running_build_refuses_both_requests(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        assert settled(qtbot, lambda: not services.status.busy)
        builds = FakeBuilds()  # holds the real build owner with no tool work
        builds.gate = threading.Event()
        services.build = BuildController(plan=builds.plan, build=builds.run)
        try:
            assert outcome(services.start_build) is True
            assert services.build.running
            snapshot = snapshot_for(document)
            for call in (
                lambda: services.start_prepare_editors(document),
                lambda: services.start_open_editor(snapshot, BUILTIN),
            ):
                assert "being built" in refused(call).user_message
            assert not work.calls and not services.launch.busy
        finally:
            builds.gate.set()
            assert services.build.shutdown(10)
        assert services.project is project and not project.read_only


def test_read_only_projects_may_prepare_but_never_open(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        assert settled(qtbot, lambda: not services.status.busy)
        viewer = Project.open(project.root)  # the lock is held, so this copy is read-only
        services.project = viewer
        try:
            assert viewer.read_only
            results = Results(services.launch)
            work.gate.set()
            assert outcome(lambda: services.start_prepare_editors(document)) is True
            receipt = prepared(qtbot, results, 1)
            error = refused(lambda: services.start_open_editor(receipt, BUILTIN))
            assert "read-only" in error.user_message
            assert [call[0] for call in work.calls] == ["prepare"]
            assert work.calls[0][1] is viewer
        finally:
            services.project = project
            viewer.close()


def test_stale_choices_are_refused_through_the_services(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        assert settled(qtbot, lambda: not services.status.busy)
        results = Results(services.launch)
        work.gate.set()
        assert outcome(lambda: services.start_prepare_editors(document)) is True
        receipt = prepared(qtbot, results, 1)
        foreign = refused(lambda: services.start_open_editor(snapshot_for(document), BUILTIN))
        assert "out of date" in foreign.user_message
        project.manifest = replace(project.manifest)  # e.g. saved project details
        changed = refused(lambda: services.start_open_editor(receipt, BUILTIN))
        assert "out of date" in changed.user_message
        assert [call[0] for call in work.calls] == ["prepare"]
        assert not services.launch.busy


def test_close_timeout_during_an_editor_request_keeps_the_writer_lock(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with owned_editors(tmp_path) as (services, project, document, work, _other):
        assert settled(qtbot, lambda: not services.status.busy)
        assert outcome(lambda: services.start_prepare_editors(document)) is True
        assert work.entered.wait(5)
        assert outcome(lambda: services.shutdown(0)) is False
        assert services.project is project and not project.read_only
        assert services.launch.busy, "ownership kept, not abandoned"
        assert "still finishing" in refused(services.close_project).user_message
        with Project.open(project.root) as viewer:
            assert viewer.read_only, "the writer lock was released early"
        work.gate.set()
        assert outcome(lambda: services.shutdown(10)) is True
        assert services.project is None and project.read_only
        with Project.open(project.root) as again:
            assert not again.read_only


def editor_result(
    project: Project,
    action: str,
    *,
    receipt: Receipt | None = None,
    error: BaseException | None = None,
    choice: EditorChoice = CUSTOM,
) -> LaunchResult:
    return LaunchResult(
        project,
        project.root,
        project.manifest,
        None,
        receipt,
        error,
        editor_action=action,
        document=project.root / "course 日本.brres",
        choice=choice,
    )


def test_open_wording_names_the_chosen_editor_and_claims_only_a_start(tmp_path: Path) -> None:
    with Project.create(tmp_path / "P", "P") as project:
        launched = editors.Launched("brawlcrate", 321, Path("course 日本.brres"), ("Warned.",))
        custom = describe_editor(editor_result(project, "open", receipt=launched), "My Crate")
        assert (
            custom.splitlines()[0] == "My Crate was started (process 321) with course 日本.brres."
        )
        assert "cannot tell whether My Crate finished opening" in custom
        assert "Warned." in custom.splitlines()  # adapter warnings are kept
        builtin = describe_launch(editor_result(project, "open", receipt=launched, choice=BUILTIN))
        assert builtin.startswith("BrawlCrate was started (process 321)")
        for text in (custom, builtin):
            assert "Blender" not in text, text


def test_preparation_wording_is_a_readiness_note_not_a_launch(tmp_path: Path) -> None:
    with Project.create(tmp_path / "P", "P") as project:
        snapshot = snapshot_for(project.root / "course 日本.brres")
        text = describe_launch(editor_result(project, "prepare", receipt=snapshot))
        assert text == "Editor choices for course 日本.brres are ready (2 of 2 found)."


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ToolNotFound("BrawlCrate", "Set its path on the Tools page."), "Tools page"),
        (OSError("disk vanished"), ": disk vanished. Try again; if it keeps failing, restart"),
        (RuntimeError(), ": RuntimeError. Try again"),
        (KeyboardInterrupt(), "was interrupted. Try again."),
    ],
    ids=["typed", "ordinary", "empty", "interrupt"],
)
@pytest.mark.parametrize("action", ["prepare", "open"])
def test_editor_failures_are_explained_without_blender(
    tmp_path: Path, action: str, error: BaseException, expected: str
) -> None:
    with Project.create(tmp_path / "P", "P") as project:
        text = describe_editor(editor_result(project, action, error=error), "My Crate")
        assert expected in text, text
        if isinstance(error, ToolNotFound):  # typed errors keep their exact wording
            assert text == str(error), text
        assert "Blender" not in text and ": ." not in text
        if not isinstance(error, ToolNotFound):
            subject = "prepare editor choices" if action == "prepare" else "open My Crate"
            assert subject in text, text
