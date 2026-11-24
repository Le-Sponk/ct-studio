"""P5-T08e2: how many build logs each project keeps (``build_logs_kept``).

A machine setting in ``settings.json``: absent means the default (``build_log.KEEP``, 20),
otherwise a whole number from 1 to ``MAX_BUILD_LOGS_KEPT``. Anything else makes the file
damaged: it is refused by load and by save and never overwritten. ``build_project`` hands
the number to the runner, which keeps only that many ``.ctstudio/logs/build-*.log`` after
every build; ``ctstudio build`` reads it fresh for every build, and a damaged file keeps
the default (with the warning every CLI build gives for it).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ctstudio.__main__ import main
from ctstudio.cli import build as cli_build
from ctstudio.core.build import project_build
from ctstudio.core.build.build_log import KEEP, LOG_DIR
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.project_build import BuildPlan
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import (
    BUILD_IGNORED,
    BUILD_LOGS_KEPT,
    MAX_BUILD_LOGS_KEPT,
    SettingsError,
    UserSettings,
    load,
    save,
)
from ctstudio.core.tools.process import CancelToken

pytestmark = pytest.mark.timeout(60)
BAD: list[object] = [0, -1, MAX_BUILD_LOGS_KEPT + 1, "5", 5.0, True, None, [5]]
OLD = 30  # older logs made before a build: more than the default keeps


def outcome(call: Callable[[], object]) -> object:
    try:
        return call()
    except Exception as exc:  # the error is the result looked at
        return exc


def write(path: Path, data: object) -> str:
    text = json.dumps(data) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def test_absent_means_the_default_and_a_saved_number_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert UserSettings().build_logs_kept() is None
    assert KEEP == 20, "the default changed; the page's wording says 20"
    save(UserSettings().with_build_logs_kept(5), path)
    assert json.loads(path.read_text(encoding="utf-8"))[BUILD_LOGS_KEPT] == 5
    assert load(path).build_logs_kept() == 5
    save(load(path).with_build_logs_kept(MAX_BUILD_LOGS_KEPT), path)
    assert load(path).build_logs_kept() == MAX_BUILD_LOGS_KEPT
    save(load(path).with_build_logs_kept(1), path)
    assert load(path).build_logs_kept() == 1
    save(load(path).with_build_logs_kept(None), path)
    assert BUILD_LOGS_KEPT not in json.loads(path.read_text(encoding="utf-8"))
    assert load(path).build_logs_kept() is None


def test_other_keys_survive_and_the_number_leaves_them_alone(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    write(path, {"format": 1, "future": {"a": [1]}, "build_jobs": 2, "tools": {}})
    save(load(path).with_build_logs_kept(7), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "format": 1,
        "future": {"a": [1]},
        "build_jobs": 2,
        BUILD_LOGS_KEPT: 7,
        "tools": {},
    }


@pytest.mark.parametrize("bad", BAD, ids=[repr(b) for b in BAD])
def test_a_bad_number_makes_the_file_damaged_and_it_is_never_overwritten(
    tmp_path: Path, bad: object
) -> None:
    path = tmp_path / "settings.json"
    text = write(path, {"format": 1, BUILD_LOGS_KEPT: bad})
    error = outcome(lambda: load(path))
    assert isinstance(error, SettingsError), f"{bad!r} was accepted: {error!r}"
    assert f'"{BUILD_LOGS_KEPT}" is not a whole number from 1 to {MAX_BUILD_LOGS_KEPT}' in str(
        error
    )
    refused = outcome(lambda: save(UserSettings(other={BUILD_LOGS_KEPT: bad}), path))
    assert isinstance(refused, SettingsError), f"{bad!r} was saved: {refused!r}"
    assert path.read_text(encoding="utf-8") == text
    assert list(tmp_path.iterdir()) == [path], "a backup was made"
    if bad is not None:  # None asks for the default
        copied = outcome(lambda: UserSettings().with_build_logs_kept(bad))  # type: ignore[arg-type]
        assert isinstance(copied, ValueError), f"{bad!r} was copied in: {copied!r}"


def test_the_damaged_build_notice_names_the_build_logs() -> None:
    assert "build logs" in BUILD_IGNORED, BUILD_IGNORED


def seed(root: Path, count: int = OLD) -> list[Path]:
    """``count`` older build logs (their names sort before any made now)."""
    folder = root / LOG_DIR
    folder.mkdir(parents=True, exist_ok=True)
    made = [folder / f"build-2000-01-01T00-00-{n:02d}.000000Z.log" for n in range(count)]
    for path in made:
        path.write_text("old\n", encoding="utf-8")
    return made


def logs(root: Path) -> list[Path]:
    return sorted((root / LOG_DIR).glob("build-*.log"))


def ignore(_event: BuildEvent) -> None:
    pass


@pytest.mark.parametrize("keep", [None, 1, 3, 25, OLD + 5])
def test_the_runner_keeps_only_that_many_build_logs(tmp_path: Path, keep: int | None) -> None:
    root = tmp_path / "Pistë"
    project = Project.create(root, "Pistë")
    try:
        old = seed(root)
        request = BuildRequest(project.manifest, "test", {}, {})
        graph = BuildGraph(root, [])
        run_build(
            graph, BuildCache.load(root), request, ignore, cancel=CancelToken(), keep_logs=keep
        )
    finally:
        project.close()
    left = logs(root)
    wanted = min(KEEP if keep is None else keep, OLD + 1)
    assert len(left) == wanted, f"{len(left)} build logs left, not {wanted}"
    assert left[-1] not in old, "the new build's log was deleted"
    assert left[:-1] == old[len(old) - (wanted - 1) :], "not the newest logs were kept"


@pytest.mark.parametrize("keep", [1, 2])
def test_the_new_build_log_is_kept_even_when_other_names_sort_after_it(
    tmp_path: Path, keep: int
) -> None:
    root = tmp_path / "Pistë"
    project = Project.create(root, "Pistë")
    folder = root / LOG_DIR
    later = [folder / "build-2099-01-01T00-00-00.000000Z.log", folder / "build-zzz.log"]
    try:
        seed(root, 3)
        for path in later:
            path.write_text("later\n", encoding="utf-8")
        request = BuildRequest(project.manifest, "test", {}, {})
        summary = run_build(
            BuildGraph(root, []),
            BuildCache.load(root),
            request,
            ignore,
            cancel=CancelToken(),
            keep_logs=keep,
        )
    finally:
        project.close()
    left = logs(root)
    assert summary.log is not None and summary.log.exists(), "the new build's log was deleted"
    assert len(left) == keep, f"{len(left)} build logs left, not {keep}"
    newest_others = sorted(later)[len(later) - (keep - 1) :]
    assert set(left) == {summary.log, *newest_others}, left


def test_the_runner_refuses_keeping_no_build_log(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "Pistë", "Pistë")
    try:
        request = BuildRequest(project.manifest, "test", {}, {})
        graph = BuildGraph(project.root, [])
        cache = BuildCache.load(project.root)
        error = outcome(
            lambda: run_build(graph, cache, request, ignore, cancel=CancelToken(), keep_logs=0)
        )
        flag = outcome(
            lambda: run_build(graph, cache, request, ignore, cancel=CancelToken(), keep_logs=True)
        )
    finally:
        project.close()
    assert isinstance(error, ValueError), f"keeping no log was accepted: {error!r}"
    assert isinstance(flag, ValueError), f"true was taken as a number: {flag!r}"
    assert not (project.root / LOG_DIR).exists() or logs(project.root) == [], "it still built"


def test_build_project_hands_the_number_to_the_runner(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "Pistë", "Pistë")
    try:
        seed(project.root)
        request = BuildRequest(project.manifest, "test", {}, {})
        plan = BuildPlan(BuildGraph(project.root, []), request)
        project_build.build_project(plan, ignore, cancel=CancelToken(), keep_logs=4)
        assert len(logs(project.root)) == 4
        project_build.build_project(plan, ignore, cancel=CancelToken())
        assert len(logs(project.root)) == 5, "without a number the default did not apply"
    finally:
        project.close()


@pytest.fixture
def cli_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    users = tmp_path / "users"
    for name in ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA"):
        monkeypatch.setenv(name, str(users / name))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(users / name))
    project = tmp_path / "Pistë 日本"
    Project.create(project, "Pistë", slot="castle_course").close()
    monkeypatch.setattr(cli_build, "plan_build", empty_plan)  # the real runner, no steps
    return project


def empty_plan(root: Path, manifest: Manifest, profile: Profile, **_kw: object) -> BuildPlan:
    return BuildPlan(BuildGraph(root, []), BuildRequest(manifest, profile, {}, {}))


def test_ctstudio_build_keeps_the_saved_number_of_build_logs(
    cli_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(cli_root)
    save(UserSettings().with_build_logs_kept(6))
    assert main(["build", str(cli_root)]) == 0
    assert len(logs(cli_root)) == 6, "ctstudio build did not keep the saved number"
    save(load().with_build_logs_kept(2))
    assert main(["build", str(cli_root)]) == 0
    assert len(logs(cli_root)) == 2, "the next build did not read the setting again"
    save(load().with_build_logs_kept(None))
    seed(cli_root)
    assert main(["build", str(cli_root)]) == 0
    assert len(logs(cli_root)) == KEEP, "back to the default, not 20 logs were kept"
    assert capsys.readouterr().err == ""


def test_ctstudio_build_with_a_damaged_file_keeps_the_default(
    cli_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(cli_root)
    text = write(settings.default_path(), {"format": 1, BUILD_LOGS_KEPT: 0})
    assert main(["build", str(cli_root)]) == 0
    assert len(logs(cli_root)) == KEEP, "a damaged file did not keep the default"
    err = capsys.readouterr().err
    assert BUILD_IGNORED in err, err
    assert settings.default_path().read_text(encoding="utf-8") == text
