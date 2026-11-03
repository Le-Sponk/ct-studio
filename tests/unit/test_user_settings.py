"""P2-T07a: ``ctstudio.core.project.settings`` — the user's machine settings (tool paths).

Stored as ``settings.json`` in the user config folder (ARCHITECTURE §6), never in a project.
The file is the user's: a damaged one is reported and left alone, keys CT Studio does not
know survive a save, and every save keeps a backup of the previous file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.project import settings
from ctstudio.core.project.settings import SettingsError, UserSettings, load, save

pytestmark = pytest.mark.timeout(30)


def _file(tmp_path: Path) -> Path:
    return tmp_path / "config é" / "settings.json"


def test_the_file_lives_in_the_user_config_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    from ctstudio.core import platform as ct_platform

    dirs = ct_platform.UserDirectories(Path("cfg"), Path("data"), Path("cache"), Path("logs"))
    monkeypatch.setattr(ct_platform, "user_directories", lambda: dirs)
    assert settings.default_path() == Path("cfg") / "settings.json"


def test_no_file_means_nothing_is_set(tmp_path: Path) -> None:
    loaded = load(_file(tmp_path))
    assert loaded == UserSettings() and loaded.tools == {} and loaded.configured() == {}
    assert not _file(tmp_path).exists()  # loading never creates the file


def test_a_set_path_is_saved_and_read_back(tmp_path: Path) -> None:
    exe = tmp_path / "Wiimm é" / "wszst.exe"
    save(UserSettings().with_tool("wszst", exe), _file(tmp_path))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    assert data == {"format": 1, "tools": {"wszst": str(exe)}}
    loaded = load(_file(tmp_path))
    assert loaded.tools == {"wszst": str(exe)} and loaded.configured() == {"wszst": exe}


def test_clearing_a_path_removes_it(tmp_path: Path) -> None:
    chosen = UserSettings().with_tool("wszst", tmp_path / "a").with_tool("blender", tmp_path / "b")
    cleared = chosen.with_tool("wszst", None)
    assert cleared.tools == {"blender": str(tmp_path / "b")}
    assert chosen.tools["wszst"] == str(tmp_path / "a")  # settings are values, not shared
    assert cleared.with_tool("wszst", None) == cleared


def test_an_unknown_tool_id_is_refused() -> None:
    with pytest.raises(ValueError, match="nosuchtool"):
        UserSettings().with_tool("nosuchtool", Path("x"))


def test_keys_ct_studio_does_not_know_survive_a_save(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"format": 1, "theme": "dark", "tools": {"wszst": "/w", "later": "/l"}}),
        encoding="utf-8",
    )
    loaded = load(path)
    assert loaded.configured() == {"wszst": Path("/w")}  # an id from a newer version is kept
    save(loaded.with_tool("blender", Path("/b")), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "format": 1,
        "theme": "dark",
        "tools": {"wszst": "/w", "later": "/l", "blender": str(Path("/b"))},
    }


def test_every_save_keeps_a_backup_of_the_previous_file(tmp_path: Path) -> None:
    path = _file(tmp_path)
    save(UserSettings().with_tool("wszst", Path("/one")), path)
    assert list(path.parent.glob("*.bak")) == []  # nothing to back up the first time
    save(UserSettings().with_tool("wszst", Path("/two")), path)
    [backup] = path.parent.glob("settings.json.*.bak")
    assert json.loads(backup.read_text(encoding="utf-8"))["tools"] == {"wszst": str(Path("/one"))}


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[1, 2]",
        '{"format": 1, "tools": ["wszst"]}',
        '{"format": 1, "tools": {"wszst": 5}}',
        '{"format": 1, "tools": {"wszst": ""}}',
        '{"format": "1", "tools": {}}',
        '{"format": false, "tools": {}}',
        '{"format": 1, "auto_add_library": 5}',
        '{"format": 1, "auto_add_library": ""}',
        b"\xff\xfe".decode("latin-1"),
    ],
    ids=[
        "broken",
        "a list",
        "tools a list",
        "a number",
        "empty path",
        "format text",
        "format false",
        "library a number",
        "library empty",
        "bytes",
    ],
)
def test_a_damaged_file_is_reported_and_left_alone(text: str, tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="latin-1")
    before = path.read_bytes()
    with pytest.raises(SettingsError) as caught:
        load(path)
    assert isinstance(caught.value, ProjectError)
    assert str(path) in str(caught.value) and "Next:" in str(caught.value)
    assert path.read_bytes() == before


def test_the_auto_add_library_is_saved_read_back_and_cleared(tmp_path: Path) -> None:
    library = tmp_path / "my own auto-add é"
    chosen = UserSettings().with_tool("wszst", tmp_path / "w").with_auto_add_library(library)
    save(chosen, _file(tmp_path))
    loaded = load(_file(tmp_path))
    assert loaded.auto_add_library() == library
    assert loaded.configured() == {"wszst": tmp_path / "w"}, "tools are kept"
    assert UserSettings().auto_add_library() is None
    save(loaded.with_auto_add_library(None), _file(tmp_path))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    assert "auto_add_library" not in data and data["tools"] == {"wszst": str(tmp_path / "w")}


def test_a_newer_format_is_not_read_or_overwritten(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"format": 2, "tools": {}}', encoding="utf-8")
    with pytest.raises(SettingsError) as caught:
        load(path)
    assert "newer version of CT Studio" in str(caught.value)


def test_a_file_without_a_format_counts_as_the_first_format(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"tools": {"wszst": "/w"}}', encoding="utf-8")
    assert load(path).configured() == {"wszst": Path("/w")}


def test_settings_that_cannot_be_read_are_a_settings_error(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.mkdir(parents=True)  # a folder where the file should be
    with pytest.raises(SettingsError) as caught:
        load(path)
    assert caught.value.details is not None


def test_load_and_save_default_to_the_user_config_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _file(tmp_path)
    monkeypatch.setattr(settings, "default_path", lambda: path)
    save(UserSettings().with_tool("wszst", Path("/w")))
    assert path.is_file() and load().configured() == {"wszst": Path("/w")}


def test_saving_an_older_file_writes_the_current_format(tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"format": 0, "tools": {}}', encoding="utf-8")
    save(load(path), path)
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == 1
