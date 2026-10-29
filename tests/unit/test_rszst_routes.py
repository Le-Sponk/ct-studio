"""P2-T06b: the managed ``rszst`` is discovered and ``doctor`` reports which route gave it.

Discovery looks in CT Studio's own folder (``<user data>/tools/riistudio-5.11.5``) only when
``setup.json`` marks it complete, after PATH and the standard folders, before ``.tools/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from ctstudio.core import platform as ct_platform
from ctstudio.core.tools import doctor
from ctstudio.core.tools.discovery import DiscoveryEnvironment, ToolLocation, discover
from ctstudio.core.tools.doctor import diagnose
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.rszst_setup import (
    WITHOUT_RSZST,
    SetupRecord,
    managed_executable,
    managed_root,
    write_record,
)
from ctstudio.core.tools.spec import ToolSpec
from ctstudio.core.tools.versions import VersionCache, VersionResult

pytestmark = pytest.mark.timeout(30)
RSZST = TOOL_BY_ID["rszst"]
Platform = Literal["windows", "linux"]


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake", encoding="utf-8")
    path.chmod(0o755)
    return path


def _env(tmp_path: Path, platform: Platform, path: str = "") -> DiscoveryEnvironment:
    return DiscoveryEnvironment(
        platform=platform,
        root=tmp_path / "system",
        home=tmp_path / "home",
        variables={"PATH": path},
        sandbox=None,
        data_dir=tmp_path / "données",
    )


def _managed(tmp_path: Path, platform: Platform, route: Literal["download", "build"]) -> Path:
    root = managed_root(tmp_path / "données")
    exe = _exe(managed_executable(root, platform))
    write_record(root, SetupRecord(route, "5.11.5", exe.relative_to(root).as_posix()))
    return exe


# --- discovery -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("platform", "route"), [("windows", "download"), ("linux", "build")])
def test_a_completed_managed_copy_is_found(
    platform: Platform, route: Literal["download", "build"], tmp_path: Path
) -> None:
    exe = _managed(tmp_path, platform, route)
    found = discover(RSZST, environment=_env(tmp_path, platform))
    assert found == ToolLocation(exe.resolve(), None, "managed", "direct")


def test_an_unfinished_managed_copy_is_ignored(tmp_path: Path) -> None:
    _exe(managed_executable(managed_root(tmp_path / "données"), "linux"))
    assert discover(RSZST, environment=_env(tmp_path, "linux")) is None


def test_path_wins_over_the_managed_copy(tmp_path: Path) -> None:
    _managed(tmp_path, "linux", "build")
    mine = _exe(tmp_path / "my bin" / "rszst")
    found = discover(RSZST, environment=_env(tmp_path, "linux", str(mine.parent)))
    assert found is not None and (found.path, found.source) == (mine.resolve(), "path")


def test_the_managed_copy_wins_over_developer_tools(tmp_path: Path) -> None:
    exe = _managed(tmp_path, "windows", "download")
    dev = tmp_path / "dev"
    _exe(dev / "riistudio" / "rszst.exe")
    found = discover(RSZST, environment=_env(tmp_path, "windows"), include_dev=True, dev_root=dev)
    assert found is not None and found.path == exe.resolve()


def test_only_rszst_has_a_managed_copy(tmp_path: Path) -> None:
    _managed(tmp_path, "windows", "download")
    assert discover(TOOL_BY_ID["wszst"], environment=_env(tmp_path, "windows")) is None


def test_no_data_folder_means_no_managed_lookup(tmp_path: Path) -> None:
    _managed(tmp_path, "linux", "build")
    env = DiscoveryEnvironment("linux", tmp_path / "s", tmp_path / "h", {"PATH": ""}, None)
    assert discover(RSZST, environment=env) is None


def test_the_system_environment_uses_the_user_data_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dirs = ct_platform.UserDirectories(
        tmp_path / "c", tmp_path / "d", tmp_path / "k", tmp_path / "l"
    )
    monkeypatch.setattr(ct_platform, "user_directories", lambda: dirs)
    assert DiscoveryEnvironment.from_system().data_dir == tmp_path / "d"


# --- doctor --------------------------------------------------------------------------------------


@pytest.fixture
def probed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(items: list[tuple[ToolSpec, ToolLocation]], **_kwargs: object) -> list[VersionResult]:
        return [
            VersionResult(
                s.id, ToolLocation(loc.path, "5.11.5", loc.source, loc.launcher), "probed"
            )
            for s, loc in items
        ]

    monkeypatch.setattr(doctor, "probe_versions", fake)


def _rszst(tmp_path: Path, env: DiscoveryEnvironment) -> doctor.ToolCheck:
    report = diagnose(
        environment=env, dev_root=tmp_path / "none", cache=VersionCache(tmp_path / "v.json")
    )
    [check] = [c for c in report.tools if c.tool_id == "rszst"]
    return check


@pytest.mark.parametrize(("platform", "route"), [("windows", "download"), ("linux", "build")])
def test_doctor_reports_the_managed_route(
    platform: Platform, route: Literal["download", "build"], probed: None, tmp_path: Path
) -> None:
    _managed(tmp_path, platform, route)
    check = _rszst(tmp_path, _env(tmp_path, platform))
    assert (check.status, check.source, check.route, check.version) == (
        "found",
        "managed",
        route,
        "5.11.5",
    )
    assert doctor._check_json(check)["route"] == route


def test_doctor_calls_an_own_install_existing(probed: None, tmp_path: Path) -> None:
    mine = _exe(tmp_path / "bin" / "rszst.exe")
    check = _rszst(tmp_path, _env(tmp_path, "windows", str(mine.parent)))
    assert (check.status, check.route) == ("found", "existing")


@pytest.mark.parametrize(
    ("platform", "words"), [("windows", "download"), ("linux", "build it from source")]
)
def test_doctor_offers_the_route_for_this_os_when_missing(
    platform: Platform, words: str, probed: None, tmp_path: Path
) -> None:
    check = _rszst(tmp_path, _env(tmp_path, platform))
    assert (check.status, check.route) == ("missing", None)
    assert check.fix is not None and "ctstudio setup rszst" in check.fix and words in check.fix
    assert check.note == WITHOUT_RSZST


def test_other_tools_have_no_route(probed: None, tmp_path: Path) -> None:
    report = diagnose(
        environment=_env(tmp_path, "windows"),
        dev_root=tmp_path / "n",
        cache=VersionCache(tmp_path / "v"),
    )
    assert {c.route for c in report.tools if c.tool_id != "rszst"} == {None}
