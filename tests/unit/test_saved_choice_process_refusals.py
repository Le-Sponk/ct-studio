"""Fresh real-owner refusals after a successful saved-choice process request."""

import sys
import time
from pathlib import Path
from types import FrameType
from typing import Literal

import pytest
from saved_choice_process_helpers import (
    Request,
    check_helpers,
    exercise,
    linux,
    request,
    snapshot,
    windows,
)

from ctstudio.core.errors import CTStudioError, ToolNotFound
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools import custom_editors, editors, process, wine
from ctstudio.core.tools.editors import Launched
from ctstudio.core.tools.saved_editors import EditorChoice

CASES = [
    ("builtin", "corrupt"),
    ("custom", "corrupt"),
    ("custom", "settings-missing"),
    ("custom", "custom-removed"),
    ("builtin", "executable"),
    ("custom", "executable"),
    ("builtin", "document"),
    ("custom", "document"),
    ("custom", "project"),
    ("builtin", "prefix"),
    ("custom", "prefix"),
]


def remove_fixture_file(path: Path) -> None:
    """Windows launcher shims may still hold the file just after child publication."""
    deadline = time.monotonic() + 10
    while path.exists() and time.monotonic() < deadline:
        try:
            path.unlink()
        except PermissionError:
            time.sleep(0.02)
    assert not path.exists(), "owned synthetic launcher did not release its file"


def invalidate(item: Request, fault: str) -> tuple[type[CTStudioError], str]:
    if fault == "corrupt":
        item.settings.write_bytes(b'{"format": 1, broken JSON\xff')
        return SettingsError, "cannot be read"
    if fault == "settings-missing":
        item.settings.unlink()
        return editors.EditorError, "saved custom editor is missing"
    if fault == "custom-removed":
        item.fields["custom_tools"] = {}
        item.save()
        return editors.EditorError, "saved custom editor is missing"
    if fault == "prefix":
        (item.prefix / "system.reg").unlink()
        return wine.WineError, "not a Wine prefix"
    if fault == "project":
        (item.project / "ctstudio.toml").unlink()
        item.project.rmdir()
        return editors.EditorError, "project"
    path = item.executable if fault == "executable" else item.document
    remove_fixture_file(path)
    return (ToolNotFound, "") if fault == "executable" else (editors.EditorError, "document")


def observed_open(item: Request) -> tuple[Launched | Exception, list[str]]:
    """Observe the real spawn boundary without replacing the runner or waiting for files."""
    starts: list[str] = []
    previous = sys.getprofile()

    def observe(frame: FrameType, event: str, argument: object) -> None:
        if event == "call" and frame.f_code in (
            process.launch_detached.__code__,
            process.run.__code__,
        ):
            starts.append(frame.f_code.co_name)

    sys.setprofile(observe)
    try:
        result = item.open()
    finally:
        sys.setprofile(previous)
    return result, starts


@pytest.mark.parametrize(("namespace", "fault"), CASES)
def test_saved_choice_refusal_starts_no_additional_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    fault: str,
) -> None:
    through_wine = fault == "prefix"
    system = linux if through_wine else windows
    monkeypatch.setattr(editors, "current_os", system)
    monkeypatch.setattr(custom_editors, "current_os", system)
    monkeypatch.setenv("WINEPREFIX", "inherited native sentinel")
    item = request(tmp_path, EditorChoice(namespace, "brawlcrate"), 0, wine=through_wine)
    exercise(item)
    check_helpers(item)
    expected, text = invalidate(item, fault)
    before = snapshot(tmp_path)
    child_before = snapshot(tmp_path / "receipts")
    result, starts = observed_open(item)
    assert isinstance(result, expected), result
    assert text in str(result) and result.hint
    assert starts == [], "refused request reached the real process-start boundary"
    assert snapshot(tmp_path) == before
    assert snapshot(tmp_path / "receipts") == child_before
