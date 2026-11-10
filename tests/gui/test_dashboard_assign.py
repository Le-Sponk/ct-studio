"""P5-T04b: dropping or choosing a file on the dashboard assigns it on the launch worker."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from assign_helpers import AssignWork, assign_services, drop, kcl_bytes, local, png_bytes, write
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from ctstudio.core.components.assign import Assigned
from ctstudio.core.components.registry import ComponentSpec
from ctstudio.core.errors import ProjectError
from ctstudio.core.project import manifest_io
from ctstudio.core.project.project import Project
from ctstudio.gui.assign_text import assignment_detail, describe_assignment
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusResult
from ctstudio.gui.views.dashboard import Dashboard

pytestmark = [pytest.mark.gui, pytest.mark.timeout(30)]


@contextmanager
def board(
    qtbot: QtBot, folder: Path, work: AssignWork | None = None
) -> Iterator[tuple[Dashboard, AppServices, Project, AssignWork]]:
    work = work if work is not None else AssignWork()
    services = assign_services(work)
    project = Project.create(folder / "Pistë 日本", "Pistë 日本")
    services.adopt(project)
    try:
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(project)
        page.resize(900, 800)
        page.show()
        qtbot.waitUntil(lambda: not page.busy)
        yield page, services, project, work
    finally:
        for held in (work.gate, work.release):
            if held is not None:
                held.set()
        qtbot.waitUntil(lambda: not services.launch.busy)
        assert services.shutdown(10)


def settle(qtbot: QtBot, page: Dashboard, services: AppServices) -> None:
    qtbot.waitUntil(lambda: not services.launch.busy)
    qtbot.waitUntil(lambda: not page.busy and not services.status.busy)


def test_a_dropped_file_is_copied_saved_published_and_rechecked(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with board(qtbot, tmp_path) as (page, services, project, work):
        before = project.manifest_path.read_bytes()
        updates: list[object] = []
        services.status.updated.connect(updates.append)
        source = write(tmp_path / "Sources été" / "mine.kcl", kcl_bytes())
        card = page.cards["kcl"]
        assert drop(card, local(source))
        settle(qtbot, page, services)
        [(part, given, reference, thread)] = work.calls
        assert (part, given, reference) == ("kcl", source, False)
        assert thread is not threading.main_thread()
        kcl = project.manifest.components.kcl
        assert (kcl.mode, kcl.file) == ("manual", "files/course.kcl")
        assert manifest_io.load(project.manifest_path) == project.manifest
        copied = project.root / "files" / "course.kcl"
        assert copied.read_bytes() == kcl_bytes()
        assert [p.read_bytes() for p in project.root.glob("*.bak")] == [before]
        assert (card.mode_label.text(), card.path) == ("Mode: manual", copied)
        note = card.assign_note
        expected = "Now using files/course.kcl (a copy of mine.kcl)."
        assert (note.text(), note.accessibleDescription(), note.isHidden()) == (
            expected,
            expected,
            False,
        )
        checked = [isinstance(u, StatusResult) for u in updates]
        assert True in checked, "statuses were checked again"
        assert (card.choose_action.isEnabled(), page.refresh_button.isEnabled()) == (True, True)


def test_replacing_a_copy_says_where_the_old_one_was_backed_up(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with board(qtbot, tmp_path) as (page, services, project, _work):
        write(project.root / "files" / "course.kcl", kcl_bytes())
        source = write(tmp_path / "newer.kcl", kcl_bytes(0x800))
        assert drop(page.cards["kcl"], local(source))
        settle(qtbot, page, services)
        [backup] = (project.root / ".ctstudio" / "backups").iterdir()
        assert (backup / "files" / "course.kcl").read_bytes() == kcl_bytes()
        note = page.cards["kcl"].assign_note
        assert note.text() == (
            "Now using files/course.kcl (a copy of newer.kcl). "
            f"The previous copy is backed up in .ctstudio/backups/{backup.name}."
        )
        assert note.toolTip() == f"{note.text()}\n{backup}"
        selectable = Qt.TextInteractionFlag.TextSelectableByMouse
        assert note.textInteractionFlags() & selectable == selectable


def test_reference_in_place_records_the_path_and_copies_nothing(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with board(qtbot, tmp_path) as (page, services, project, work):
        source = write(tmp_path / "Ailleurs" / "kept.kcl", kcl_bytes())
        card = page.cards["kcl"]

        def chooser(_parent: QWidget, _spec: ComponentSpec, _start: Path) -> Path:
            return source

        card.choose = chooser
        card.reference_action.trigger()
        settle(qtbot, page, services)
        assert work.calls[0][2] is True
        assert project.manifest.components.kcl.file == str(source.resolve())
        assert not (project.root / "files").exists() or not any((project.root / "files").iterdir())
        assert card.assign_note.text() == "Now using kept.kcl where it is (outside the project)."
        assert card.assign_note.toolTip() == f"{card.assign_note.text()}\n{source.resolve()}"
        assert card.assign_note.accessibleDescription() == card.assign_note.toolTip()


def test_reference_in_place_inside_the_project_names_its_project_path(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with board(qtbot, tmp_path) as (page, services, project, _work):
        source = write(project.root / "sources" / "mine.kcl", kcl_bytes())
        card = page.cards["kcl"]

        def chooser(_parent: QWidget, _spec: ComponentSpec, _start: Path) -> Path:
            return source

        card.choose = chooser
        card.reference_action.trigger()
        settle(qtbot, page, services)
        assert project.manifest.components.kcl.file == "sources/mine.kcl"
        assert card.assign_note.text() == "Now using sources/mine.kcl where it is."
        assert card.assign_note.toolTip() == card.assign_note.text()


def test_the_wrong_type_is_explained_on_the_card_and_nothing_changes(
    qtbot: QtBot, tmp_path: Path
) -> None:
    with board(qtbot, tmp_path) as (page, services, project, _work):
        manifest, raw = project.manifest, project.manifest_path.read_bytes()
        source = write(tmp_path / "photo.png", png_bytes())
        card = page.cards["kcl"]
        assert drop(card, local(source))
        settle(qtbot, page, services)
        assert project.manifest is manifest
        assert project.manifest_path.read_bytes() == raw
        assert card.mode_label.text() == "Mode: auto"
        assert card.assign_note.text().startswith(
            "photo.png is the wrong type: expected collision file (KCL), found PNG image."
        )
        assert "Next:" in card.assign_note.text()
        assert card.assign_note.toolTip() == card.assign_note.text()
        assert not page.cards["kmp"].assign_note.text(), "only the card it was dropped on"


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (RuntimeError("boom"), "Could not assign the file: boom. Try again; if it keeps failing"),
        (RuntimeError(), "Could not assign the file: RuntimeError. Try again"),
        (
            PermissionError(13, "Permission denied", "C:\\x\\files"),
            "Could not assign the file: Permission denied. Try again",
        ),
        (OSError(13, ""), "Could not assign the file: a system error. Try again"),
        (OSError("disk full"), "Could not assign the file: disk full. Try again"),
        (KeyboardInterrupt(), "Assigning the file was interrupted. Check this card, then try"),
    ],
    ids=["crash", "empty-crash", "os-error", "empty-os-error", "plain-os-error", "interrupt"],
)
def test_unexpected_failures_are_shown_without_publishing(
    qtbot: QtBot, tmp_path: Path, error: BaseException, text: str
) -> None:
    work = AssignWork()
    work.error = error
    with board(qtbot, tmp_path, work) as (page, services, project, _work):
        manifest = project.manifest
        assert drop(page.cards["kcl"], local(tmp_path / "x.kcl"))
        settle(qtbot, page, services)
        assert project.manifest is manifest
        assert page.cards["kcl"].assign_note.text().startswith(text)


def test_while_assigning_everything_waits_and_the_card_says_so(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = AssignWork()
    work.gate = threading.Event()
    with board(qtbot, tmp_path, work) as (page, services, _project, _work):
        source = write(tmp_path / "mine.kcl", kcl_bytes())
        card = page.cards["kcl"]
        assert drop(card, local(source))
        assert services.launch.busy
        assert card.assign_note.text() == "Copying mine.kcl into the project…"
        assert page.launch_progress.isVisible()
        assert (page.refresh_button.isEnabled(), page.edit_button.isEnabled()) == (False, False)
        assert not page.builds._eligible()
        offered = [(c.choose_action.isEnabled(), c.acceptDrops()) for c in page.cards.values()]
        assert set(offered) == {(False, False)}
        assert len(work.calls) == 1, "a second drop starts nothing"
        with pytest.raises(ProjectError, match="still finishing"):
            services.close_project()
        work.gate.set()
        settle(qtbot, page, services)
        assert card.assign_note.text().startswith("Now using files/course.kcl")


def test_a_project_changed_meanwhile_is_not_overwritten(qtbot: QtBot, tmp_path: Path) -> None:
    work = AssignWork()
    work.release = threading.Event()
    with board(qtbot, tmp_path, work) as (page, services, project, _work):
        source = write(tmp_path / "mine.kcl", kcl_bytes())
        assert drop(page.cards["kcl"], local(source))
        assert work.done.wait(10), "saved on disk, result not yet delivered"
        changed = replace(project.manifest, project=replace(project.manifest.project, name="X"))
        project.manifest = changed
        work.release.set()
        settle(qtbot, page, services)
        assert project.manifest is changed
        assert page.cards["kcl"].mode_label.text() == "Mode: auto"
        assert page.cards["kcl"].assign_note.text() == (
            "The project changed while the file was being assigned, so this card was not "
            "updated. Close and reopen the project to see the result."
        )


def test_a_failure_while_the_project_changed_says_nothing_was_saved(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = AssignWork()
    work.gate = threading.Event()
    work.error = ProjectError("No.", hint="Do this.")
    with board(qtbot, tmp_path, work) as (page, services, project, _work):
        assert drop(page.cards["kcl"], local(write(tmp_path / "mine.kcl", kcl_bytes())))
        changed = replace(project.manifest, project=replace(project.manifest.project, name="X"))
        project.manifest = changed
        work.gate.set()
        settle(qtbot, page, services)
        assert project.manifest is changed
        assert page.cards["kcl"].assign_note.text() == "No.\nNext: Do this."


def test_a_refusal_before_starting_is_shown_on_the_card(qtbot: QtBot, tmp_path: Path) -> None:
    with board(qtbot, tmp_path) as (page, services, project, work):
        assert project.manifest is not None
        services.status.request(project)  # a status check is now pending
        assert services.status.busy
        page._assign("kcl", tmp_path / "x.kcl", False)
        assert work.calls == []
        assert page.cards["kcl"].assign_note.text() == (
            "Component statuses are still being checked.\n"
            "Next: Wait for the check to finish, then try again."
        )
        qtbot.waitUntil(lambda: not services.status.busy)


def test_a_read_only_dashboard_takes_no_drops(qtbot: QtBot, tmp_path: Path) -> None:
    work = AssignWork()
    services = assign_services(work)
    with Project.create(tmp_path / "Pistë", "Pistë") as holder:
        other = Project.open(holder.root)
        services.adopt(other)
        page = Dashboard(services)
        qtbot.addWidget(page)
        page.set_project(other)
        try:
            qtbot.waitUntil(lambda: not page.busy)
            source = write(tmp_path / "mine.kcl", kcl_bytes())
            assert not drop(page.cards["kcl"], local(source))
            assert not page.cards["kcl"].choose_action.isEnabled()
            page._assign("kcl", source, False)
            assert work.calls == []
        finally:
            assert services.shutdown(10)


def test_a_drive_root_used_in_place_is_named_in_full(tmp_path: Path) -> None:
    root = Path(Path.cwd().anchor)  # e.g. C:\\ on Windows, / elsewhere
    with Project.create(tmp_path / "P", "P") as project:
        assigned = Assigned(project.manifest, str(root), None, None)
        result = LaunchResult(
            project, project.root, project.manifest, "posteffect", assigned, None, root, True
        )
        assert describe_assignment(result) == (
            f"Now using {root} where it is (outside the project)."
        )
        assert assignment_detail(result) == str(root)
