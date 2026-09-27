"""P1-T05 platform information and sandbox detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core import platform as ct_platform


def test_os_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, expected in (("Windows", "windows"), ("Linux", "linux"), ("Darwin", "other")):
        monkeypatch.setattr(ct_platform.platform, "system", lambda value=name: value)
        assert ct_platform.current_os() == expected


def test_user_directories_come_from_platformdirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    functions = ("user_config_dir", "user_data_dir", "user_cache_dir", "user_log_dir")
    for name in functions:
        monkeypatch.setattr(
            ct_platform.platformdirs, name, lambda app, dirname=name: str(tmp_path / dirname / app)
        )
    dirs = ct_platform.user_directories()
    assert dirs.config == tmp_path / "user_config_dir" / "ctstudio"
    assert dirs.data == tmp_path / "user_data_dir" / "ctstudio"
    assert dirs.cache == tmp_path / "user_cache_dir" / "ctstudio"
    assert dirs.logs == tmp_path / "user_log_dir" / "ctstudio"
    assert not dirs.config.exists()  # Querying paths is not creating files.


def test_sandbox_environment_and_flatpak_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("FLATPAK_ID", "SNAP", "SNAP_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ct_platform.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ct_platform, "_FLATPAK_INFO", Path("unavailable-flatpak-info"))
    assert ct_platform.sandbox_kind() is None
    monkeypatch.setenv("FLATPAK_ID", "org.blender.Blender")
    assert ct_platform.sandbox_kind() == "flatpak"
    monkeypatch.delenv("FLATPAK_ID")
    monkeypatch.setenv("SNAP_NAME", "blender")
    assert ct_platform.sandbox_kind() == "snap"
    monkeypatch.delenv("SNAP_NAME")
    monkeypatch.setattr(ct_platform, "_FLATPAK_INFO", Path(__file__))
    assert ct_platform.sandbox_kind() == "flatpak"
    monkeypatch.setattr(ct_platform.platform, "system", lambda: "Windows")
    assert ct_platform.sandbox_kind() is None
