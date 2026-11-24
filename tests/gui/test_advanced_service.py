"""P5-T08e1/e2: Settings → Advanced's service reads both machine settings fresh, saves one
at a time, writes nothing for an unchanged choice and refuses a damaged file untouched."""

from __future__ import annotations

from pathlib import Path

import pytest
from editor_owner_helpers import outcome

from ctstudio.core.project import settings
from ctstudio.core.project.settings import BUILD_LOGS_KEPT, SHOW_TOOL_COMMANDS
from ctstudio.gui.advanced import BUILD_LOGS_KEPT as LOGS_CHOICE
from ctstudio.gui.advanced import TOOL_COMMANDS, AdvancedService

pytestmark = pytest.mark.timeout(30)
DAMAGED = '{"format": 1, "build_logs_kept": "all"}\n'


def test_no_file_means_shown_and_the_default_number(tmp_path: Path) -> None:
    service = AdvancedService(settings_path=tmp_path / "s é" / "settings.json")
    assert service.load() == {TOOL_COMMANDS: True, LOGS_CHOICE: None}


def test_tool_commands_are_saved_fresh_and_an_unchanged_save_writes_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "s é" / "settings.json"
    service = AdvancedService(settings_path=path)
    assert service.save_tool_commands(True) is True
    assert not path.exists(), "saving the default into no file wrote one"
    assert service.save_tool_commands(False) is False
    assert settings.load(path).other[SHOW_TOOL_COMMANDS] is False
    before = path.read_bytes()
    made = sorted(path.parent.iterdir())
    assert service.save_tool_commands(False) is False
    assert path.read_bytes() == before and sorted(path.parent.iterdir()) == made
    path.write_text('{"show_tool_commands": true, "build_logs_kept": 7}', encoding="utf-8")
    assert service.load() == {TOOL_COMMANDS: True, LOGS_CHOICE: 7}, "not read again"


def test_build_logs_kept_are_saved_fresh_and_an_unchanged_save_writes_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "s é" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"future": 1, "show_tool_commands": false}', encoding="utf-8")
    service = AdvancedService(settings_path=path)
    assert service.save_build_logs_kept(None) is None
    assert sorted(path.parent.iterdir()) == [path], "an unchanged default was saved"
    assert service.save_build_logs_kept(50) == 50
    saved = settings.load(path)
    assert saved.other == {"future": 1, SHOW_TOOL_COMMANDS: False, BUILD_LOGS_KEPT: 50}
    before = path.read_bytes()
    made = sorted(path.parent.iterdir())
    assert service.save_build_logs_kept(50) == 50
    assert path.read_bytes() == before and sorted(path.parent.iterdir()) == made
    assert service.save_build_logs_kept(None) is None
    assert BUILD_LOGS_KEPT not in settings.load(path).other


def test_a_damaged_file_is_refused_and_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "s é" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(DAMAGED, encoding="utf-8")
    service = AdvancedService(settings_path=path)
    assert isinstance(outcome(service.load), settings.SettingsError)
    assert isinstance(outcome(lambda: service.save_tool_commands(False)), settings.SettingsError)
    assert isinstance(outcome(lambda: service.save_build_logs_kept(5)), settings.SettingsError)
    assert path.read_text(encoding="utf-8") == DAMAGED
    assert sorted(path.parent.iterdir()) == [path], "a refused save made a backup"
