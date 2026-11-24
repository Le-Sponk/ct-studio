"""Settings → Advanced (P5-T08e1) in tests: a project whose file saves reserved Wiimm
arguments, and a finder that opens the page on the real main window."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from editor_request_helpers import settled
from pytestqt.qtbot import QtBot
from settings_window_helpers import action, go, settings_dialog

from ctstudio.core.project.project import Project
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.views.advanced_page import AdvancedPage


def project_with_args(folder: Path, arguments: Sequence[str], name: str = "Advanced é") -> Project:
    """A new project whose ``ctstudio.toml`` saves ``arguments`` as ``extra_wszst_args``."""
    created = Project.create(folder / name, name)
    root = created.root
    created.close()
    path = root / "ctstudio.toml"
    text = path.read_text(encoding="utf-8")
    assert text.count("extra_wszst_args = []") == 1, "the new project file changed shape"
    saved = f"extra_wszst_args = {json.dumps(list(arguments), ensure_ascii=False)}"
    path.write_text(text.replace("extra_wszst_args = []", saved), encoding="utf-8")
    project = Project.open(root)
    assert project.manifest.build.extra_wszst_args == tuple(arguments)
    return project


def open_advanced(qtbot: QtBot, window: MainWindow) -> AdvancedPage:
    action(window, "settingsAction").trigger()
    go(settings_dialog(window), "Advanced")
    page = window.settings_window.advanced_page
    assert page is not None, "the Advanced page was not made"
    assert settled(qtbot, lambda: not page.busy), "the Advanced page never finished reading"
    return page


def pick(page: AdvancedPage, shown: bool) -> None:
    """Choose Shown or Hidden as a user would (Qt emits ``activated`` for user picks only)."""
    combo = page.commands.combo
    index = combo.findData(shown)
    assert index >= 0, f"{shown!r} is not offered"
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
