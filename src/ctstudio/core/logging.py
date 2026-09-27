"""Package-scoped JSON-lines file logging and an optional human-readable CLI stream."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import platformdirs

from ctstudio.core.errors import ProjectError

_LOGGER_NAME = "ctstudio"
_FILE_HANDLER_NAME = "ctstudio:file"
_CONSOLE_HANDLER_NAME = "ctstudio:console"


class _JSONLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; call ``configure_logging`` once at application start."""
    return logging.getLogger(name)


def configure_logging(
    *,
    log_dir: Path | None = None,
    console: bool = False,
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> Path:
    """Set up CT Studio handlers and return the file path.

    Reconfiguring closes only our own handlers so Windows can rotate/rename the old
    file and a caller's handlers are left intact. The log directory is app-managed.
    """
    directory = log_dir if log_dir is not None else Path(platformdirs.user_log_dir(_LOGGER_NAME))
    path = directory / "ctstudio.log"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
    except OSError as exc:
        raise ProjectError(
            "Could not open CT Studio log.",
            hint="Check the log folder permissions and free space, then try again.",
            details=f"path={path}; error={exc}",
        ) from exc
    root = logging.getLogger(_LOGGER_NAME)
    for handler in list(root.handlers):
        if handler.name in (_FILE_HANDLER_NAME, _CONSOLE_HANDLER_NAME):
            root.removeHandler(handler)
            handler.close()
    file_handler.set_name(_FILE_HANDLER_NAME)
    file_handler.setFormatter(_JSONLineFormatter())
    root.addHandler(file_handler)
    if console:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.set_name(_CONSOLE_HANDLER_NAME)
        stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(stream_handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    return path
