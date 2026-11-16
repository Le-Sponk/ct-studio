"""Saved native choices reach real children; no real editor loading/save is claimed."""

from pathlib import Path
from typing import Literal

import pytest
from saved_choice_process_helpers import check_helpers, exercise, request, windows

from ctstudio.core.tools import custom_editors, editors
from ctstudio.core.tools.saved_editors import EditorChoice


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
@pytest.mark.parametrize("tool_id", ["brawlcrate", "riistudio"])
def test_saved_native_two_fresh_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    tool_id: str,
) -> None:
    monkeypatch.setattr(editors, "current_os", windows)
    monkeypatch.setattr(custom_editors, "current_os", windows)
    monkeypatch.setenv("WINEPREFIX", "inherited native sentinel")
    results: list[tuple[int, int]] = []
    for revision in range(2):
        item = request(tmp_path, EditorChoice(namespace, tool_id), revision)
        results.append(exercise(item))
        check_helpers(item)
    assert len({launch for launch, _ in results}) == 2
    assert len({writer for _, writer in results}) == 2
