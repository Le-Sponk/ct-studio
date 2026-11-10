"""P5-T04b screenshots: an assigned card, a refusal and the More menu, light and dark."""

from __future__ import annotations

from pathlib import Path

import pytest
from assign_helpers import AssignWork, assign_services, drop, kcl_bytes, local, png_bytes, write
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_component_mode_visual import dark_palette
from wizard_fakes import SCREENS, shot

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def test_assigned_and_refused_cards_and_menu_images(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(assign_services(AssignWork()))
    qtbot.addWidget(window)
    window.resize(1100, 1250)
    window.show()
    qtbot.waitUntil(lambda: not window.welcome.busy)
    window._opened(Project.create(tmp_path / "Pistë 日本", "Pistë 日本"))
    page, services = window.dashboard, window.services
    qtbot.waitUntil(lambda: not page.busy)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    try:
        assert drop(page.cards["kcl"], local(write(tmp_path / "Sources" / "mine.kcl", kcl_bytes())))
        qtbot.waitUntil(lambda: not services.launch.busy and not page.busy)
        assert drop(page.cards["kmp"], local(write(tmp_path / "photo.png", png_bytes())))
        qtbot.waitUntil(lambda: not services.launch.busy and not page.busy)
        assert page.cards["kcl"].assign_note.text().startswith("Now using files/course.kcl")
        assert "wrong type" in page.cards["kmp"].assign_note.text()
        notes = [page.cards[part].assign_note for part in ("kcl", "kmp")]
        squeezed = [n.height() < n.fontMetrics().lineSpacing() for n in notes]
        assert squeezed == [False, False], "the notes are not squeezed"
        shot(window, "p5-t04b-dashboard-light.png")
        original = dark_palette(app)
        try:
            shot(window, "p5-t04b-dashboard-dark.png")
        finally:
            app.setPalette(original)
        card = page.cards["posteffect"]
        menu = card.more_button.menu()
        assert menu is not None
        menu.popup(card.more_button.mapToGlobal(QPoint(0, card.more_button.height())))
        shot(menu, "p5-t04b-more-menu.png")
        menu.close()
        names = ("dashboard-light", "dashboard-dark", "more-menu")
        sizes = [(SCREENS / f"p5-t04b-{name}.png").stat().st_size for name in names]
        assert min(sizes) > 0
    finally:
        window.close()
