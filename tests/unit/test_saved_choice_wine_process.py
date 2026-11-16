"""Synthetic Linux Wine routes use real helpers/children, never installed Wine."""

from pathlib import Path
from typing import Literal

import pytest
from saved_choice_process_helpers import check_helpers, exercise, linux, request

from ctstudio.core.tools import custom_editors, editors, wine
from ctstudio.core.tools.saved_editors import EditorChoice


@pytest.mark.parametrize("namespace", ["builtin", "custom"])
@pytest.mark.parametrize("tool_id", ["brawlcrate", "riistudio"])
def test_saved_wine_two_fresh_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    namespace: Literal["builtin", "custom"],
    tool_id: str,
) -> None:
    monkeypatch.setattr(editors, "current_os", linux)
    monkeypatch.setattr(custom_editors, "current_os", linux)
    monkeypatch.setenv("WINEPREFIX", "inherited native sentinel")
    results: list[tuple[int, int]] = []
    assert wine.WATCH_SECONDS == 3.0
    for revision in range(2):
        item = request(tmp_path, EditorChoice(namespace, tool_id), revision, wine=True)
        results.append(exercise(item))
        check_helpers(item)
    assert len({launch for launch, _ in results}) == 2
    assert len({writer for _, writer in results}) == 2
    assert wine.WATCH_SECONDS == 3.0
