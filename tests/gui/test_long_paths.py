"""P5-T10c (owner decision D2): long paths are never cut off. A path line shows one line
shortened in the middle with the whole path on hover, read out, and in Copy path; the
"was started" notice names the file relative to the project."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from build_window_helpers import build_window
from editor_request_helpers import settled
from outside_visual_helpers import visual_style
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot
from wizard_fakes import Choices, Creator, choices, creator, edit, make_wizard, to_summary

from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools import folders as corefolders
from ctstudio.gui.launch_controller import LaunchResult
from ctstudio.gui.launch_text import describe_editor, describe_launch
from ctstudio.gui.views.path_label import PathLabel

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]
__all__ = ["choices", "creator"]  # fixtures used by name

UNBROKEN = "C:\\" + "a" * 150 + "\\" + "b" * 150 + "\\course.kcl"  # 300+ characters


def inside(outer: QWidget, widget: QWidget) -> bool:
    top_left = widget.mapTo(outer, QPoint(0, 0))
    return outer.rect().contains(QRect(top_left, widget.size()))


def test_a_long_path_is_shortened_in_the_middle_with_the_whole_path_kept(qtbot: QtBot) -> None:
    holder = QWidget()
    qtbot.addWidget(holder)
    label = PathLabel(holder)
    QVBoxLayout(holder).addWidget(label)
    label.set_path(UNBROKEN)
    holder.resize(400, 80)
    holder.show()
    qtbot.waitExposed(holder)
    assert inside(holder, label), "the path ran past the window"
    shown = label.text()
    assert "…" in shown and shown != UNBROKEN
    assert shown.startswith("C:\\aaa") and shown.endswith("course.kcl"), shown
    assert label.full_text == UNBROKEN
    assert label.toolTip() == UNBROKEN
    assert label.accessibleName() == UNBROKEN  # read out whole, once
    assert label.accessibleDescription() == ""
    label.copy_action.trigger()
    assert QApplication.clipboard().text() == UNBROKEN
    holder.resize(4000, 80)
    assert settled(qtbot, lambda: label.text() == UNBROKEN), "room again, but still shortened"


def test_a_bigger_font_shortens_the_path_again(qtbot: QtBot) -> None:
    label = PathLabel()
    qtbot.addWidget(label)
    label.set_path("C:\\" + "c" * 30 + "\\course.kcl")
    label.setFixedSize(label.fontMetrics().horizontalAdvance(label.full_text) + 12, 60)
    label.show()
    qtbot.waitExposed(label)
    assert label.text() == label.full_text  # it fits
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 2)
    label.setFont(font)  # same size: only the font tells it to fit again
    assert settled(qtbot, lambda: "…" in label.text()), "the bigger font was not fitted"


def test_a_placeholder_is_not_offered_as_a_path(qtbot: QtBot) -> None:
    label = PathLabel()
    qtbot.addWidget(label)
    label.set_path("No Blender file chosen", is_path=False)
    assert label.full_text == "No Blender file chosen" and not label.copy_action.isEnabled()


def test_a_short_path_is_shown_whole(qtbot: QtBot) -> None:
    label = PathLabel()
    qtbot.addWidget(label)
    label.set_path("C:\\Tracks\\Piste")
    label.resize(600, 30)
    label.show()
    qtbot.waitExposed(label)
    assert label.text() == "C:\\Tracks\\Piste"
    label.set_path("")
    assert label.text() == "" and not label.copy_action.isEnabled()


@pytest.mark.parametrize("enlarged", [False, True], ids=["normal", "enlarged"])
def test_the_dashboard_path_lines_stay_in_the_window_at_800_px(
    qtbot: QtBot, tmp_path: Path, enlarged: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    folder = tmp_path / ("p" * 120)
    folder.mkdir()
    with (
        visual_style(app, False, enlarged),
        build_window(qtbot, folder) as (view, project, _fake),
    ):
        view.resize(800, 600)
        QApplication.processEvents()
        page = view.dashboard
        for line, whole in (
            (page.folder_label, str(project.root)),
            (page.source_label, "No Blender file chosen"),
        ):
            assert isinstance(line, PathLabel)
            assert line.full_text == whole and line.toolTip() == whole
            assert inside(view, line), f"{line.objectName()} runs off the window"
        assert "…" in page.folder_label.text()
        assert page.folder_label.copy_action.isEnabled()
        assert not page.source_label.copy_action.isEnabled()  # a placeholder, not a path


def _launched(root: Path, document: Path) -> LaunchResult:
    project = cast(Project, object())
    manifest = cast(Manifest, object())
    receipt = editors.Launched("custom", 321, document, ())
    return LaunchResult(project, root, manifest, None, receipt, editor_action="open")


def test_the_started_notice_names_the_file_relative_to_the_project(tmp_path: Path) -> None:
    root = tmp_path / ("p" * 120)
    text = describe_editor(_launched(root, root / "files" / "course.kcl"), "custom")
    first = text.splitlines()[0]
    assert first == f"custom was started (process 321) with {Path('files', 'course.kcl')}."
    outside = tmp_path / "elsewhere" / "course.kcl"
    text = describe_editor(_launched(root, outside), "custom")
    assert text.splitlines()[0].endswith(f"with {outside}.")  # outside: the whole path


def test_blender_started_names_its_file_relative_to_the_project(tmp_path: Path) -> None:
    root = tmp_path / "Piste"
    result = _launched(root, root / "source.blend")
    blender = LaunchResult(
        result.project, root, result.manifest, None, result.receipt
    )  # no editor action: the Blender path
    assert describe_launch(blender).splitlines()[0] == (
        "Blender was started (process 321) with source.blend."
    )


@pytest.mark.parametrize("enlarged", [False, True], ids=["normal", "enlarged"])
def test_the_wizard_path_lines_stay_in_the_wizard_at_800_px(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path, enlarged: bool
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    location = tmp_path / ("w" * 120)
    location.mkdir()
    with visual_style(app, False, enlarged):
        wizard = make_wizard(qtbot, creator, choices, location)
        wizard.resize(800, 560)
        edit(wizard, "trackName").setText("Ma piste")
        preview = wizard.findChild(PathLabel, "folderPreview")
        assert preview is not None and preview.full_text == str(location / "Ma piste")
        preview.copy_action.trigger()
        assert QApplication.clipboard().text() == str(location / "Ma piste")  # only the path
        QApplication.processEvents()
        assert inside(wizard, preview), "the folder preview runs off the wizard"
        to_summary(wizard, "Ma piste", location)
        folder = wizard.findChild(PathLabel, "summaryFolder")
        assert folder is not None and folder.full_text == str(location / "Ma piste")
        QApplication.processEvents()
        assert inside(wizard, folder), "the summary's folder runs off the wizard"


def test_the_opened_folder_notice_names_it_in_the_project(tmp_path: Path) -> None:
    root = tmp_path / ("p" * 120)
    project = cast(Project, object())
    manifest = cast(Manifest, object())

    def opened(folder: Path) -> str:
        receipt = corefolders.OpenedFolder(folder, 42)
        return describe_launch(LaunchResult(project, root, manifest, "kcl", receipt))

    assert opened(root / "files").startswith('Asked the system to open the folder "files". ')
    assert opened(root).startswith("Asked the system to open the project folder. ")


def test_a_launch_notice_is_whole_on_hover(qtbot: QtBot, tmp_path: Path) -> None:
    with build_window(qtbot, tmp_path) as (view, _project, _fake):
        text = f"Viewer was started (process 7) with {UNBROKEN}."
        view.dashboard.show_launch_note(text)
        notice = view.dashboard.launch_notice
        assert notice.isVisible() and notice.toolTip() == text


def test_the_wizard_caption_shows_only_with_a_folder_and_placeholders_are_not_copied(
    qtbot: QtBot, creator: Creator, choices: Choices, tmp_path: Path
) -> None:
    wizard = make_wizard(qtbot, creator, choices, tmp_path)
    caption = wizard.findChild(QLabel, "folderPreviewCaption")
    assert caption is not None and caption.isHidden(), "a caption with no folder"
    edit(wizard, "trackName").setText("...")  # no usable folder name
    assert caption.isHidden()
    edit(wizard, "trackName").setText("Ma piste")
    assert not caption.isHidden()
    to_summary(wizard, "Ma piste", tmp_path)
    blend = wizard.findChild(PathLabel, "summaryBlend")
    assert blend is not None and blend.full_text.startswith("none yet")
    assert not blend.copy_action.isEnabled(), "the placeholder is offered as a path"
    folder = wizard.findChild(PathLabel, "summaryFolder")
    assert folder is not None and folder.copy_action.isEnabled()
