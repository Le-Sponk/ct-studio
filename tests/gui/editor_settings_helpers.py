"""Settings → Editors… on the real main window (P5-T07f1): settings-file helpers and a
held service. The settings file is the per-test one ``conftest`` points CT Studio at."""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from editor_menu_helpers import all_ready, offered, row_texts
from editor_owner_helpers import outcome
from editor_request_helpers import no_tools, settled
from editor_tools_helpers import project_for
from launch_controller_helpers import LaunchWork
from PySide6.QtWidgets import QComboBox
from pytestqt.qtbot import QtBot

from ctstudio.core.project import settings
from ctstudio.core.tools.spec import CustomTool
from ctstudio.gui.editor_launch import EditorLaunchService
from ctstudio.gui.editor_settings import EditorKinds, EditorPreferencesService
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.main_window import MainWindow
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService
from ctstudio.gui.views.editors_page import EditorsPage


class HeldPreferences(EditorPreferencesService):
    """The real service; each call records its thread, then waits for ``gate``."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.gate.set()
        self.threads: list[threading.Thread] = []
        self.loads = 0
        self.saves: list[tuple[str, str | None]] = []  # every save the page asked for
        self.customs: list[tuple[str | None, CustomTool | None]] = []  # every custom save

    def load(self) -> EditorKinds:
        gate = self.gate  # tests swap the gate while a call waits
        self.threads.append(threading.current_thread())
        self.loads += 1
        gate.wait(10)
        return super().load()

    def save(self, kind: str, tool: str | None) -> EditorKinds:
        gate = self.gate
        self.threads.append(threading.current_thread())
        self.saves.append((kind, tool))
        gate.wait(10)
        return super().save(kind, tool)

    def save_custom(self, tool_id: str | None, tool: CustomTool | None) -> EditorKinds:
        gate = self.gate
        self.threads.append(threading.current_thread())
        self.customs.append((tool_id, tool))
        gate.wait(10)
        return super().save_custom(tool_id, tool)


def settings_file() -> Path:
    return settings.default_path()


def write_settings(data: object) -> bytes:
    """Write the settings file (a str is written as it is) and return its bytes."""
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path.read_bytes()


def saved() -> dict[str, object]:
    loaded: object = json.loads(settings_file().read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"settings is not an object: {loaded!r}"
    return dict(loaded)  # pyright: ignore[reportUnknownArgumentType]


def backups() -> list[Path]:
    path = settings_file()
    return sorted(path.parent.glob(f"{path.name}.*.bak"))


def combo(page: EditorsPage, kind: str) -> QComboBox:
    box = page.combos.get(kind)
    assert box is not None, f"no choice for {kind}"
    return box


def texts(box: QComboBox) -> list[str]:
    return [box.itemText(index) for index in range(box.count())]


def choose(qtbot: QtBot, page: EditorsPage, kind: str, text: str) -> None:
    """Pick ``text`` the way a user does (Qt emits ``activated`` only for user picks)."""
    box = combo(page, kind)
    index = box.findText(text)
    assert index >= 0, f"{text!r} not offered for {kind}: {texts(box)}"
    box.setCurrentIndex(index)
    box.activated.emit(index)
    assert settled(qtbot, lambda: not page.busy), "the save never finished"


def open_in_rows(qtbot: QtBot, window: MainWindow) -> list[str]:
    """The rows of the course model's next Open in… choice dialog (then closed)."""
    window.dashboard.cards["course_model"].open_action.trigger()
    dialog = offered(qtbot, window.dashboard)
    rows = row_texts(dialog)
    dialog.reject()
    assert settled(qtbot, lambda: not window.services.launch.busy), "the dialog never ended"
    return rows


def editors_page(window: MainWindow) -> EditorsPage:
    page = window.editors_window.page
    assert page is not None, "Settings → Editors… made no page"
    return page


@contextmanager
def editors_window(
    qtbot: QtBot, service: EditorPreferencesService | None = None, *, wait: bool = True
) -> Generator[tuple[MainWindow, EditorsPage]]:
    """The real main window (no project) with Settings → Editors… opened once."""
    services = AppServices(editor_settings=service)
    window = MainWindow(services)
    qtbot.addWidget(window)
    window.show()
    try:
        assert settled(qtbot, lambda: not window.welcome.busy), "the welcome check hung"
        window.editors_action.trigger()
        page = editors_page(window)
        if wait:
            assert settled(qtbot, lambda: not page.busy), "the first read never ended"
        yield window, page
    finally:
        if isinstance(service, HeldPreferences):
            service.gate.set()
        made = window.editors_window.page
        if made is not None:
            assert settled(qtbot, lambda: not made.busy), "editor settings work never ended"
        stopped = outcome(lambda: services.shutdown(10))
        assert stopped is True, f"cleanup shutdown gave {stopped!r}"


@contextmanager
def project_window(
    qtbot: QtBot, folder: Path, editors: EditorLaunchService
) -> Generator[MainWindow]:
    """The real main window on a project whose course model exists, with ``editors``."""
    other = LaunchWork()
    other.gate.set()
    services = AppServices(
        launch=LaunchController(blender=other, folders=other, editors=editors),
        status=StatusService(evaluate=all_ready, find_tools=no_tools),
    )
    with project_for(folder, read_only=False) as project:
        window = MainWindow(services)
        qtbot.addWidget(window)
        window.show()
        try:
            assert settled(qtbot, lambda: not window.welcome.busy), "the welcome check hung"
            window._opened(project)  # pyright: ignore[reportPrivateUsage]
            card = window.dashboard.cards["course_model"]
            assert settled(qtbot, card.can_open), "the course model was never checked"
            yield window
        finally:
            page = window.editors_window.page
            if page is not None:
                assert settled(qtbot, lambda: not page.busy), "editor settings work never ended"
            stopped = outcome(lambda: services.shutdown(10))
            assert stopped is True, f"cleanup shutdown gave {stopped!r}"
