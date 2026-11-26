"""P5-T09b acceptance: the end-to-end flow goes on to Open in…, and its pictures.

After the T09a steps (a new project from the wizard, Collision and Course data assigned),
a harmless test program is added as an editor in Settings → Editors…, then Open in… on the
Collision card starts it with the project's ``files/course.kcl``. The program writes the
arguments it got to a receipt file outside the project and exits. The dashboard is then
pictured in a dark palette and with an enlarged font for the screenshot review
(``tests/artifacts/screens/p5-t09-*.png``; REVIEW_CHECKLIST.md §5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from custom_editor_helpers import add
from e2e_helpers import INPUTS, WAIT, idle, studio
from editor_menu_helpers import offered, row_texts
from editor_request_helpers import settled
from editor_settings_helpers import editors_page
from fakes.install import install_program
from outside_visual_helpers import visual_style
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_end_to_end import assigned, created
from wizard_fakes import shot

from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices

pytestmark = [pytest.mark.gui, pytest.mark.timeout(120)]

EDITOR = "Viewer é"


def viewer(folder: Path, receipt: Path) -> Path:
    """A real program that records its arguments in ``receipt`` (atomically) and exits."""
    code = (
        "import json, os, sys\n"
        f"receipt = {str(receipt)!r}\n"
        "with open(receipt + '.part', 'w', encoding='utf-8') as out:\n"
        "    json.dump({'argv': sys.argv[1:]}, out)\n"
        "os.replace(receipt + '.part', receipt)\n"
    )
    return install_program(folder / "viewer é", code)


def added(qtbot: QtBot, window: MainWindow, program: Path) -> None:
    """Add the program as an editor for any file, through Settings → Editors…."""
    window.editors_action.trigger()
    page = editors_page(window)
    assert settled(qtbot, lambda: not page.busy, WAIT), "the editors page never read"
    add(qtbot, page, EDITOR, str(program), "{file}")
    dialog = window.editors_window.dialog
    assert dialog is not None
    page.tabs.setCurrentIndex(1)  # "Your editors", where the new one is listed
    shot(dialog, "p5-t09-6-editors.png")
    dialog.reject()


def opened(qtbot: QtBot, window: MainWindow, services: AppServices) -> str:
    """Open in… on the Collision card, choosing the added editor; the dashboard's notice."""
    card = window.dashboard.cards["kcl"]
    assert settled(qtbot, card.can_open, WAIT), "Open in… never became available"
    card.open_action.trigger()
    dialog = offered(qtbot, window.dashboard)
    assert row_texts(dialog) == [EDITOR]
    shot(dialog, "p5-t09-7-open-in.png")
    dialog.choices.setCurrentRow(0)
    dialog.open_button.click()
    assert settled(qtbot, lambda: idle(window, services), WAIT), "the launch hung"
    return window.dashboard.launch_notice.text()


def pictures(qtbot: QtBot, window: MainWindow) -> None:
    """The dashboard dark, then dark with an enlarged font (about 150 %), at the window's
    size and at the checklist's 1280x720; and light at 1280x720."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    for small in (False, True):
        if small:
            window.resize(1280, 720)
        size = "-1280x720" if small else ""
        for enlarged in (False, True):
            with visual_style(app, dark=True, enlarged=enlarged):
                qtbot.wait(50)  # one layout pass for the new font
                shot(window, f"p5-t09-9-dark{'-large' if enlarged else ''}{size}.png")
    qtbot.wait(50)
    shot(window, "p5-t09-10-light-1280x720.png")


def test_open_in_starts_the_added_editor_with_the_project_file(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tools_path: object
) -> None:
    folder, receipt = tmp_path / "Projets é", tmp_path / "receipt é.json"
    folder.mkdir()
    program = viewer(tmp_path / "Programs é", receipt)
    with studio(qtbot, folder, monkeypatch) as (window, services):
        project = created(qtbot, window, services, folder)
        assigned(qtbot, window, services)
        added(qtbot, window, program)
        notice = opened(qtbot, window, services)
        document = project.root / "files" / "course.kcl"
        assert notice.startswith(f"{EDITOR} was started (process "), notice
        place = Path("files", "course.kcl")  # named by its place in the project (P5-T10c)
        assert f") with {place}." in notice.splitlines()[0], notice
        shot(window, "p5-t09-8-started.png")
        assert settled(qtbot, receipt.is_file, WAIT), "the program never ran"
        got = json.loads(receipt.read_text(encoding="utf-8"))["argv"]
        assert [Path(arg).resolve() for arg in got] == [document.resolve()]
        assert document.read_bytes() == (INPUTS / "course.kcl").read_bytes(), "the file changed"
        pictures(qtbot, window)
