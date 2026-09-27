"""Create the Qt application only on GUI paths; headless smoke exits without an event loop."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from ctstudio.core.errors import ProjectError
from ctstudio.gui.main_window import MainWindow


def _save_smoke(window: MainWindow, path: Path) -> None:
    """Save PNG exclusively so a smoke test cannot overwrite someone's screenshot."""
    image = QBuffer()
    image.open(QIODevice.OpenModeFlag.WriteOnly)
    if not window.grab().save(image, "PNG"):
        raise ProjectError("Could not render the screenshot.", hint="Try a new output path.")
    staged: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            staged = Path(stream.name)
            stream.write(image.data().data())
            stream.flush()
            os.fsync(stream.fileno())
        # Linking publishes a complete file without replacing an existing screenshot.
        os.link(staged, path)
    except FileExistsError as exc:
        raise ProjectError(
            f"Screenshot already exists: {path.name}.",
            hint="Choose a new output name to keep the existing file.",
        ) from exc
    except OSError as exc:
        raise ProjectError(
            f"Could not save screenshot: {path.name}.",
            hint="Check the output folder and available disk space, then try again.",
            details=str(exc),
        ) from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def run_gui(smoke_path: Path | None = None) -> int:
    """Launch the app, or render and save one offscreen frame for CI."""
    app = QApplication([])
    app.setApplicationName("CT Studio")
    window = MainWindow()
    window.show()
    if smoke_path is not None:
        app.processEvents()
        try:
            _save_smoke(window, smoke_path)
        finally:
            window.close()
        return 0
    return app.exec()
