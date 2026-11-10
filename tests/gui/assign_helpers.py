"""Synthetic files, drops and gated assignment work for P5-T04b GUI tests."""

import struct
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QWidget
from test_new_project_window import FakeBuilds

from ctstudio.core.components.assign import Assigned, assign_file
from ctstudio.core.project.project import Project
from ctstudio.gui.build_controller import BuildController
from ctstudio.gui.launch_controller import LaunchController
from ctstudio.gui.services import AppServices
from ctstudio.gui.status_service import StatusService

ATTACHABLE = ("course_model", "kcl", "minimap", "skybox", "kmp", "posteffect")


def kcl_bytes(size: int = 0x400) -> bytes:
    """A collision file the magic check accepts (same layout as tests/unit/test_magic.py)."""
    offsets = (0x3C, 0x3C + 12 * 4, 0x100, 0x200)
    head = struct.pack(">4If3f", *offsets, 300.0, -1.0, -2.0, -3.0)
    head += struct.pack(">3I3If", 0xFFFF0000, 0xFFFFE000, 0xFFFF0000, 13, 3, 3, 250.0)
    return head + bytes(size - len(head))


def png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + bytes(17)


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def mime(urls: list[QUrl]) -> QMimeData:
    data = QMimeData()
    data.setUrls(urls)
    return data


def local(*paths: Path) -> list[QUrl]:
    return [QUrl.fromLocalFile(str(path)) for path in paths]


def drag_enter(widget: QWidget, urls: list[QUrl]) -> bool:
    """Send a synthetic drag-enter; True when the widget would take the drop."""
    data = mime(urls)
    event = QDragEnterEvent(
        QPoint(5, 5),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)
    return event.isAccepted()


def drop(widget: QWidget, urls: list[QUrl]) -> bool:
    """Send a synthetic drop (after a drag-enter, as a real drag does); True when accepted."""
    drag_enter(widget, urls)
    data = mime(urls)
    event = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)
    return event.isAccepted()


class AssignWork:
    """Records each call (with its thread); can hold it open or fail; else does the real work."""

    def __init__(self) -> None:
        self.gate: threading.Event | None = None
        self.error: BaseException | None = None
        self.done = threading.Event()  # set once the real work has finished
        self.release: threading.Event | None = None  # if set, holds the result until released
        self.calls: list[tuple[str, Path, bool, threading.Thread]] = []

    def __call__(
        self, project: Project, part: str, source: Path, *, reference: bool = False
    ) -> Assigned:
        self.calls.append((part, source, reference, threading.current_thread()))
        gate = self.gate
        if gate is not None:
            assert gate.wait(10)
        if self.error is not None:
            raise self.error
        assigned = assign_file(project, part, source, reference=reference)
        self.done.set()
        release = self.release
        if release is not None:
            assert release.wait(10)
        return assigned


def assign_services(
    assign: Callable[..., Assigned] = assign_file, builds: FakeBuilds | None = None
) -> AppServices:
    """Real services whose status check and build touch no tool; real or injected assignment."""
    fake = builds if builds is not None else FakeBuilds()
    status = StatusService(evaluate=lambda _project, _tools: {}, find_tools=lambda **_kw: ())
    return AppServices(
        status=status,
        build=BuildController(plan=fake.plan, build=fake.run),
        launch=LaunchController(assign=assign),
    )
