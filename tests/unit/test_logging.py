"""P1-T04: a real rotating UTF-8 JSON-lines log, scoped to CT Studio."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.logging import configure_logging, get_logger

pytestmark = pytest.mark.timeout(30)


@pytest.fixture(autouse=True)
def cleanup_loggers() -> Iterator[None]:
    root = logging.getLogger("ctstudio")
    original_level, original_propagate = root.level, root.propagate
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if handler.name and handler.name.startswith("ctstudio:"):
                root.removeHandler(handler)
                handler.close()  # Windows cannot remove an open log file.
        root.setLevel(original_level)
        root.propagate = original_propagate


def _lines(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_log_file_in_unicode_path_contains_json_records(tmp_path: Path) -> None:
    directory = tmp_path / "track é logs"
    log_file = configure_logging(log_dir=directory)
    logger = get_logger("ctstudio.core.test")
    logger.info("Built %s", "course é")
    assert log_file == directory / "ctstudio.log"
    assert log_file.is_file()
    assert "course é" in log_file.read_text(encoding="utf-8")  # UTF-8, not escaped ASCII.
    records = _lines(log_file)
    assert len(records) == 1
    assert records[0]["level"] == "INFO"
    assert records[0]["logger"] == "ctstudio.core.test"
    assert records[0]["message"] == "Built course é"
    assert records[0]["timestamp"].endswith("Z")


def test_default_log_directory_comes_from_platformdirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctstudio.core.logging as module

    def fake_log_dir(appname: str) -> str:
        assert appname == "ctstudio"
        return str(tmp_path / "default logs")

    monkeypatch.setattr(module.platformdirs, "user_log_dir", fake_log_dir)
    log_file = configure_logging()
    get_logger("ctstudio.core.test").warning("visible")
    assert log_file == tmp_path / "default logs" / "ctstudio.log"
    assert _lines(log_file)[0]["message"] == "visible"


def test_reconfigure_replaces_own_handlers_without_duplicate_console_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = configure_logging(log_dir=tmp_path / "first", console=True)
    other = logging.NullHandler()
    root = logging.getLogger("ctstudio")
    root.addHandler(other)
    try:
        second = configure_logging(log_dir=tmp_path / "second", console=True)
        assert other in root.handlers  # Never tear down handlers installed by the caller.
        get_logger("ctstudio.core.test").error("failed once")
        assert capsys.readouterr().err.count("failed once") == 1
        assert len(_lines(second)) == 1
        assert _lines(first) == []  # Closed and detached before the new log.
        assert len([h for h in root.handlers if h.name == "ctstudio:file"]) == 1
        assert len([h for h in root.handlers if h.name == "ctstudio:console"]) == 1
    finally:
        root.removeHandler(other)
        other.close()


def test_rotates_with_complete_json_lines(tmp_path: Path) -> None:
    log_file = configure_logging(log_dir=tmp_path, max_bytes=250, backup_count=1)
    logger = get_logger("ctstudio.core.test")
    logger.warning("marker-%s", "é" * 160)
    logger.warning("marker-%s", "ß" * 160)
    backup = tmp_path / "ctstudio.log.1"
    assert backup.is_file()
    assert len(_lines(backup)) == 1
    assert len(_lines(log_file)) == 1
    assert "é" in _lines(backup)[0]["message"]
    assert "ß" in _lines(log_file)[0]["message"]


def test_multiline_message_and_exception_stay_in_single_json_line(tmp_path: Path) -> None:
    log_file = configure_logging(log_dir=tmp_path)
    try:
        raise ValueError("invalid é")
    except ValueError:
        get_logger("ctstudio.core.test").exception("line one\nline two")
    records = _lines(log_file)
    assert len(records) == 1
    assert records[0]["message"] == "line one\nline two"
    assert "ValueError: invalid é" in records[0]["exception"]


def test_unwritable_log_location_reports_actionable_error(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "occupied"
    not_a_directory.write_text("user work", encoding="utf-8")
    with pytest.raises(ProjectError, match="Could not open CT Studio log") as error:
        configure_logging(log_dir=not_a_directory)
    assert "Next: " in str(error.value)
    assert not_a_directory.read_text(encoding="utf-8") == "user work"


def test_get_logger_has_no_qt_dependency() -> None:
    assert get_logger("ctstudio.core.example").name == "ctstudio.core.example"
