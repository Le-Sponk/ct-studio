"""P5-T08b: Settings → Build shows and saves the open project's build settings.

The page reads the project file on a joined worker and saves only on Save (one backup per
save); Undo changes goes back to what is saved. Save is off while a build or a launch runs,
and every control is off while the page reads or saves (it then owns ``services.editing``,
so the project cannot be closed under it). A read-only project is shown but not editable,
and with no project open the page says where these settings live.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from build_fakes import FakeBuilds
from editor_owner_helpers import outcome
from editor_request_helpers import settled
from launch_controller_helpers import owned_launch
from pytestqt.qtbot import QtBot
from test_new_project_window import quiet_services

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.build_settings import BuildChoices, BuildSettingsService
from ctstudio.gui.project_details import DetailsSnapshot
from ctstudio.gui.services import AppServices
from ctstudio.gui.views.build_page import WORKER_NAME, BuildPage

pytestmark = [pytest.mark.gui]


class HeldSettings(BuildSettingsService):
    """The real service, with gates and planted failures; records each call's thread."""

    def __init__(self) -> None:
        self.load_gate: threading.Event | None = None
        self.save_gate: threading.Event | None = None
        self.load_error: Exception | None = None
        self.save_error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    def load(self, project: Project) -> DetailsSnapshot:
        self.calls.append(("load", threading.current_thread().name))
        if self.load_gate is not None:
            assert self.load_gate.wait(10)
        if self.load_error is not None:
            raise self.load_error
        return super().load(project)

    def save(
        self, project: Project, snapshot: DetailsSnapshot, choices: BuildChoices
    ) -> DetailsSnapshot:
        self.calls.append(("save", threading.current_thread().name))
        if self.save_gate is not None:
            assert self.save_gate.wait(10)
        if self.save_error is not None:
            raise self.save_error
        return super().save(project, snapshot, choices)


@contextmanager
def page_for(
    qtbot: QtBot,
    folder: Path | None,
    held: HeldSettings | None = None,
    builds: FakeBuilds | None = None,
) -> Generator[tuple[BuildPage, AppServices, HeldSettings]]:
    services = quiet_services(builds)
    if folder is not None:
        services.adopt(Project.create(folder / "Build page é", "Build page é"))
    held = held if held is not None else HeldSettings()
    page = BuildPage(services, service=held)
    qtbot.addWidget(page)
    page.show()
    try:
        yield page, services, held
    finally:
        for gate in (held.load_gate, held.save_gate):
            if gate is not None:
                gate.set()
        assert settled(qtbot, lambda: not page.busy), "the page's worker never finished"
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


def shown(page: BuildPage) -> BuildChoices:
    return BuildChoices(
        page.test_compression.currentData(),
        page.release_compression.currentData(),
        page.d_copy.isChecked(),
        page.auto_add.isChecked(),
    )


def pick(page: BuildPage, combo_name: str, value: str) -> None:
    combo = getattr(page, combo_name)
    index = combo.findData(value)
    assert index >= 0, f"{value} is not offered"
    combo.setCurrentIndex(index)


def editing_controls(page: BuildPage) -> list[bool]:
    return [
        w.isEnabled()
        for w in (page.test_compression, page.release_compression, page.d_copy, page.auto_add)
    ]


def test_with_no_project_the_page_says_where_the_settings_live(
    qtbot: QtBot,
) -> None:
    with page_for(qtbot, None) as (page, _services, held):
        assert not page.busy and held.calls == [], "read a project that is not there"
        assert page.fields.isHidden(), "the choices are shown with no project"
        assert page.action_row.isHidden(), "Save and Undo are shown with no project"
        assert "Open a project" in page.note.text()
        assert not page.save_button.isEnabled() and not page.undo_button.isEnabled()


def test_the_saved_choices_are_read_on_a_worker_and_shown(qtbot: QtBot, tmp_path: Path) -> None:
    held = HeldSettings()
    held.load_gate = threading.Event()
    with page_for(qtbot, tmp_path, held) as (page, services, _held):
        assert settled(qtbot, lambda: held.calls == [("load", WORKER_NAME)])
        assert page.busy and services.editing, "a read runs without owning the project"
        assert not any(editing_controls(page)) and page.progress.isVisible()
        held.load_gate.set()
        assert settled(qtbot, lambda: not page.busy), "the read never finished"
        assert not services.editing, "the page kept the project after reading"
        assert shown(page) == BuildChoices("fast", "best", make_d_variant=True, auto_add=True)
        assert all(editing_controls(page)) and not page.progress.isVisible()
        assert "Build page é" in page.note.text() and manifest_io.FILE_NAME in page.note.text()
        assert not page.save_button.isEnabled(), "Save is on with nothing changed"
        assert not page.undo_button.isEnabled(), "Undo is on with nothing changed"


def test_save_writes_on_a_worker_publishes_and_persists_across_reopen(
    qtbot: QtBot, tmp_path: Path
) -> None:
    held = HeldSettings()
    with page_for(qtbot, tmp_path, held) as (page, services, _held):
        assert settled(qtbot, lambda: not page.busy)
        project = services.project
        assert project is not None
        wanted = BuildChoices("none", "fast", make_d_variant=False, auto_add=False)
        pick(page, "test_compression", "none")
        pick(page, "release_compression", "fast")
        page.d_copy.setChecked(False)
        page.auto_add.setChecked(False)
        assert page.save_button.isEnabled() and page.undo_button.isEnabled()
        saved: list[bool] = []
        page.saved.connect(lambda: saved.append(True))
        held.save_gate = threading.Event()
        page.save_button.click()
        assert settled(qtbot, lambda: ("save", WORKER_NAME) in held.calls)
        assert page.busy and services.editing and not any(editing_controls(page))
        assert BuildChoices.of(project.manifest.build) != wanted, "published before the save"
        held.save_gate.set()
        assert settled(qtbot, lambda: not page.busy), "the save never finished"
        assert not services.editing and saved == [True]
        assert BuildChoices.of(project.manifest.build) == wanted, "the live project is old"
        assert BuildChoices.of(manifest_io.load(project.manifest_path).build) == wanted
        assert "Saved" in page.problem.text()
        assert not page.save_button.isEnabled() and shown(page) == wanted
        root = project.root
        services.close_project()
        services.adopt(Project.open(root))
        page.reload()
        assert settled(qtbot, lambda: not page.busy)
        assert shown(page) == wanted, "the saved choices did not come back after reopening"


def test_undo_changes_goes_back_to_what_is_saved(qtbot: QtBot, tmp_path: Path) -> None:
    with page_for(qtbot, tmp_path) as (page, _services, held):
        assert settled(qtbot, lambda: not page.busy)
        before = shown(page)
        pick(page, "release_compression", "none")
        page.auto_add.setChecked(False)
        page.undo_button.click()
        assert shown(page) == before and not page.changed
        assert not page.save_button.isEnabled() and not page.undo_button.isEnabled()
        assert page.save() is False, "a save with nothing changed was started"
        assert [call for call, _ in held.calls] == ["load"], "Undo read or wrote the file"


def test_a_read_only_project_is_shown_but_not_editable(qtbot: QtBot, tmp_path: Path) -> None:
    holder = Project.create(tmp_path / "Held", "Held")
    try:
        holder.save(replace(holder.manifest, build=replace(holder.manifest.build, auto_add=False)))
        services = quiet_services()
        services.adopt(Project.open(holder.root))
        page = BuildPage(services, service=HeldSettings())
        qtbot.addWidget(page)
        assert settled(qtbot, lambda: not page.busy)
        assert shown(page).auto_add is False, "the read-only project's choices are not shown"
        assert not any(editing_controls(page)), "a read-only project's choices can be changed"
        assert not page.save_button.isEnabled() and "read-only" in page.blocked.text()
        page.auto_add.setChecked(True)  # past Qt's own disabling
        assert page.save() is False, "a save of a read-only project was started"
        assert outcome(lambda: services.shutdown(10)) is True
    finally:
        holder.close()


def test_save_is_off_while_a_build_runs(qtbot: QtBot, tmp_path: Path) -> None:
    builds = FakeBuilds()
    builds.gate = threading.Event()
    with page_for(qtbot, tmp_path, builds=builds) as (page, services, held):
        assert settled(qtbot, lambda: not page.busy)
        pick(page, "test_compression", "best")
        assert page.save_button.isEnabled()
        assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
        assert services.start_build() is True
        assert settled(qtbot, lambda: services.build.running)
        assert not page.save_button.isEnabled(), "Save stays on during a build"
        assert "build" in page.blocked.text().casefold() and page.blocked.isVisibleTo(page)
        page.save()  # past Qt's own disabling
        assert [call for call, _ in held.calls] == ["load"], "saved during a build"
        builds.gate.set()
        assert settled(qtbot, lambda: not services.build.running)
        assert settled(qtbot, page.save_button.isEnabled), "Save stayed off after the build"
        assert page.changed, "the change was lost during the build"


def test_a_failed_save_is_explained_and_the_change_kept(qtbot: QtBot, tmp_path: Path) -> None:
    with page_for(qtbot, tmp_path) as (page, services, held):
        assert settled(qtbot, lambda: not page.busy)
        project = services.project
        assert project is not None
        before = project.manifest
        held.save_error = ProjectError("Synthetic refusal.", hint="Synthetic hint.")
        page.d_copy.setChecked(False)
        page.save_button.click()
        assert settled(qtbot, lambda: not page.busy)
        assert "Could not save the build settings" in page.problem.text()
        assert "Synthetic refusal." in page.problem.text()
        assert project.manifest == before, "a failed save changed the live project"
        assert page.changed and not page.d_copy.isChecked(), "the change was thrown away"


def test_a_failed_read_is_explained(qtbot: QtBot, tmp_path: Path) -> None:
    held = HeldSettings()
    held.load_error = ProjectError("Synthetic unreadable file.", hint="Synthetic hint.")
    with page_for(qtbot, tmp_path, held) as (page, services, _held):
        assert settled(qtbot, lambda: not page.busy)
        assert "Could not read the build settings" in page.problem.text()
        assert "Synthetic unreadable file." in page.problem.text()
        assert not any(editing_controls(page)) and not page.save_button.isEnabled()
        assert not services.editing


def test_a_project_changed_since_reading_is_not_overwritten(qtbot: QtBot, tmp_path: Path) -> None:
    with page_for(qtbot, tmp_path) as (page, services, _held):
        assert settled(qtbot, lambda: not page.busy)
        project = services.project
        assert project is not None
        outside = project.manifest_path.read_bytes() + b"\n# changed outside\n"
        project.manifest_path.write_bytes(outside)
        pick(page, "test_compression", "none")
        page.save_button.click()
        assert settled(qtbot, lambda: not page.busy)
        assert "changed" in page.problem.text() and project.manifest_path.read_bytes() == outside


def test_reload_shows_the_project_open_now(qtbot: QtBot, tmp_path: Path) -> None:
    with page_for(qtbot, tmp_path) as (page, services, _held):
        assert settled(qtbot, lambda: not page.busy)
        other = Project.create(tmp_path / "Other", "Other")
        other.save(replace(other.manifest, build=replace(other.manifest.build, auto_add=False)))
        services.close_project()
        services.adopt(other)
        page.reload()
        assert settled(qtbot, lambda: not page.busy)
        assert "Other" in page.note.text() and shown(page).auto_add is False
        services.close_project()
        page.reload()
        assert page.fields.isHidden() and "Open a project" in page.note.text()


def test_save_is_off_while_a_launch_runs(qtbot: QtBot, tmp_path: Path) -> None:
    with owned_launch(tmp_path) as (services, _project, work):
        page = BuildPage(services, service=HeldSettings())
        qtbot.addWidget(page)
        assert settled(qtbot, lambda: not page.busy)
        page.auto_add.setChecked(False)
        assert page.save_button.isEnabled()
        assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
        assert services.start_launch(None) is True and services.launch.busy
        assert not page.save_button.isEnabled(), "Save stays on during a launch"
        assert "Other work" in page.blocked.text()
        assert page.save() is False, "a save started during a launch"
        work.gate.set()
        assert settled(qtbot, lambda: not services.launch.busy)
        assert settled(qtbot, page.save_button.isEnabled), "Save stayed off after the launch"
        assert page.blocked.text() == "" and page.blocked.isHidden(), "the reason stayed"


def test_another_window_editing_the_project_is_respected(qtbot: QtBot, tmp_path: Path) -> None:
    services = quiet_services()
    services.adopt(Project.create(tmp_path / "Owned", "Owned"))
    services.editing = True  # as Project details does while it is open
    held = HeldSettings()
    page = BuildPage(services, service=held)
    qtbot.addWidget(page)
    try:
        assert held.calls == [] and not page.busy, "read a project another window edits"
        assert "Another window" in page.problem.text()
        assert services.editing, "the page took the other window's ownership away"
        services.editing = False
        page.reload()
        assert settled(qtbot, lambda: not page.busy) and held.calls[0][0] == "load"
    finally:
        services.editing = False
        assert outcome(lambda: services.shutdown(10)) is True


def test_an_earlier_error_survives_a_build(qtbot: QtBot, tmp_path: Path) -> None:
    builds = FakeBuilds()
    builds.gate = threading.Event()
    with page_for(qtbot, tmp_path, builds=builds) as (page, services, held):
        assert settled(qtbot, lambda: not page.busy)
        held.save_error = ProjectError("Synthetic refusal.", hint="Synthetic hint.")
        page.d_copy.setChecked(False)
        page.save_button.click()
        assert settled(qtbot, lambda: not page.busy)
        error = page.problem.text()
        assert "Synthetic refusal." in error
        assert settled(qtbot, lambda: not services.status.busy), "the status check hung"
        assert services.start_build() is True
        assert settled(qtbot, lambda: services.build.running)
        assert page.problem.text() == error, "a starting build hid the error"
        builds.gate.set()
        assert settled(qtbot, lambda: not services.build.running)
        assert page.problem.text() == error, "the error was cleared after the build"


def test_a_file_changed_outside_since_opening_is_shown_not_edited(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with page_for(qtbot, tmp_path) as (page, services, held):
        assert settled(qtbot, lambda: not page.busy)
        project = services.project
        assert project is not None
        text = project.manifest_path.read_text(encoding="utf-8")
        assert 'test_compression = "fast"' in text, "the file does not read as expected"
        changed = text.replace('test_compression = "fast"', 'test_compression = "none"')
        project.manifest_path.write_text(changed, encoding="utf-8")
        page.reload()
        assert settled(qtbot, lambda: not page.busy)
        assert shown(page).test_compression == "none", "the file's value is not shown"
        assert "changed outside CT Studio" in page.blocked.text()
        assert not any(editing_controls(page)) and not page.save_button.isEnabled()
        page.d_copy.setChecked(False)  # past Qt's own disabling
        assert page.save() is False and [c for c, _ in held.calls] == ["load", "load"]
        assert project.manifest.build.test_compression == "fast", "the live project changed"


def test_after_a_save_the_page_stays_editable_and_saves_again(qtbot: QtBot, tmp_path: Path) -> None:
    with page_for(qtbot, tmp_path) as (page, services, held):
        assert settled(qtbot, lambda: not page.busy)
        project = services.project
        assert project is not None
        page.d_copy.setChecked(False)
        page.save_button.click()
        assert settled(qtbot, lambda: not page.busy) and "Saved" in page.problem.text()
        assert page.blocked.text() == "" and page.blocked.isHidden(), page.blocked.text()
        assert all(editing_controls(page)), "the page locked itself after its own save"
        page.auto_add.setChecked(False)
        assert page.can_save and page.save_button.isEnabled(), "a second change cannot be saved"
        page.save_button.click()
        assert settled(qtbot, lambda: not page.busy) and "Saved" in page.problem.text()
        assert [call for call, _ in held.calls] == ["load", "save", "save"]
        assert project.manifest.build.auto_add is False and page.blocked.isHidden()
