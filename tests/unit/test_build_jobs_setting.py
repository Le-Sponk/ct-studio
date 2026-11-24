"""P5-T08c: how many build steps may run at once on this computer (``build_jobs``).

A machine setting in ``settings.json``: absent means automatic (the runner's own
``min(4, CPUs)``), otherwise a whole number from 1 to ``MAX_BUILD_JOBS``. Anything else makes
the file damaged: it is refused by load and by save and never overwritten. ``build_project``
hands the number to the runner, and ``ctstudio build`` reads it fresh for every build.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ctstudio.__main__ import main
from ctstudio.cli import build as cli_build
from ctstudio.core.build import project_build
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent, BuildSummary
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.project_build import BuildPlan
from ctstudio.core.build.runner import BuildRequest
from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import (
    BUILD_JOBS,
    MAX_BUILD_JOBS,
    SettingsError,
    UserSettings,
    load,
    save,
)
from ctstudio.core.tools.process import CancelToken

pytestmark = pytest.mark.timeout(60)
DONE = BuildSummary("succeeded", (), (), (), (), (), (), 0.0, None)


def _file(tmp_path: Path) -> Path:
    return tmp_path / "config é" / "settings.json"


def outcome(call: Callable[[], object]) -> object:
    """What ``call`` returned, or the exception it raised."""
    try:
        return call()
    except Exception as exc:
        return exc


def test_no_choice_means_automatic() -> None:
    assert UserSettings().build_jobs() is None
    assert UserSettings(other={"future": 1}).build_jobs() is None


def test_a_chosen_number_is_saved_read_back_and_cleared(tmp_path: Path) -> None:
    path = _file(tmp_path)
    kept = UserSettings({"wszst": "w é"}, {"future": {"x": 1}})
    save(kept.with_build_jobs(3), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[BUILD_JOBS] == 3, "the number was not written"
    assert data["future"] == {"x": 1} and data["tools"] == {"wszst": "w é"}, "other keys lost"
    loaded = load(path)
    assert loaded.build_jobs() == 3
    save(loaded.with_build_jobs(None), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert BUILD_JOBS not in data and data["future"] == {"x": 1}, "automatic kept a number"
    assert load(path).build_jobs() is None


@pytest.mark.parametrize("jobs", [1, 2, MAX_BUILD_JOBS])
def test_every_whole_number_in_range_is_allowed(jobs: int, tmp_path: Path) -> None:
    save(UserSettings().with_build_jobs(jobs), _file(tmp_path))
    assert load(_file(tmp_path)).build_jobs() == jobs


def test_the_highest_number_is_64() -> None:
    assert MAX_BUILD_JOBS == 64


@pytest.mark.parametrize(
    "text",
    ["0", "65", "-1", "2.0", '"4"', "true", "null", "[4]"],
    ids=["zero", "too many", "negative", "a fraction", "text", "true", "null", "a list"],
)
def test_a_bad_value_makes_the_file_damaged_and_it_is_left_alone(text: str, tmp_path: Path) -> None:
    path = _file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(f'{{"format": 1, "{BUILD_JOBS}": {text}}}', encoding="utf-8")
    before = path.read_bytes()
    error = outcome(lambda: load(path))
    assert isinstance(error, SettingsError), f"{text} was accepted: {error!r}"
    assert BUILD_JOBS in str(error) and str(path) in str(error), str(error)
    assert path.read_bytes() == before


@pytest.mark.parametrize("jobs", [0, -1, MAX_BUILD_JOBS + 1, True])
def test_choosing_a_number_out_of_range_is_refused(jobs: int) -> None:
    error = outcome(lambda: UserSettings().with_build_jobs(jobs))
    assert isinstance(error, ValueError), f"{jobs!r} was accepted: {error!r}"
    assert BUILD_JOBS in str(error)


def test_a_bad_value_is_never_saved(tmp_path: Path) -> None:
    path = _file(tmp_path)
    save(UserSettings().with_build_jobs(2), path)
    before = path.read_bytes()
    bad = UserSettings(other={BUILD_JOBS: 0})
    error = outcome(lambda: save(bad, path))
    assert isinstance(error, SettingsError), f"a bad value was saved: {error!r}"
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == ["settings.json"], "a backup appeared"


def test_a_bad_value_made_in_code_is_not_read_as_a_number() -> None:
    error = outcome(lambda: UserSettings(other={BUILD_JOBS: "4"}).build_jobs())
    assert isinstance(error, ValueError), f"a bad value was read: {error!r}"


class Runner:
    """Stands in for ``run_build``: records the number it was given."""

    def __init__(self) -> None:
        self.jobs: list[int | None] = []

    def __call__(
        self,
        _graph: BuildGraph,
        _cache: BuildCache,
        _request: BuildRequest,
        _on_event: Callable[[BuildEvent], None],
        *,
        cancel: CancelToken,
        jobs: int | None = None,
    ) -> BuildSummary:
        assert not cancel.cancelled
        self.jobs.append(jobs)
        return DONE


def ignore(_event: BuildEvent) -> None:
    pass


def test_build_project_hands_the_number_to_the_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner()
    monkeypatch.setattr(project_build, "run_build", runner)
    project = Project.create(tmp_path / "Pistë", "Pistë")
    try:
        request = BuildRequest(project.manifest, "test", {}, {})
        plan = BuildPlan(BuildGraph(project.root, []), request)
        cancel = CancelToken()
        assert project_build.build_project(plan, ignore, cancel=cancel, jobs=3) is DONE
        assert project_build.build_project(plan, ignore, cancel=cancel) is DONE
    finally:
        project.close()
    assert runner.jobs == [3, None], "the runner did not get the number"


@pytest.fixture
def cli_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    users = tmp_path / "users"
    for name in ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA"):
        monkeypatch.setenv(name, str(users / name))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(users / name))
    project = tmp_path / "Pistë 日本"
    Project.create(project, "Pistë", slot="castle_course").close()
    return project


def empty_plan(root: Path, manifest: Manifest, profile: Profile, **_kw: object) -> BuildPlan:
    return BuildPlan(BuildGraph(root, []), BuildRequest(manifest, profile, {}, {}))


@pytest.fixture
def cli_runner(monkeypatch: pytest.MonkeyPatch) -> Runner:
    """``ctstudio build`` with the real ``build_project`` and a recording runner."""
    runner = Runner()
    monkeypatch.setattr(cli_build, "plan_build", empty_plan)
    monkeypatch.setattr(project_build, "run_build", runner)
    return runner


def test_ctstudio_build_runs_the_saved_number_of_steps_at_once(
    cli_root: Path, cli_runner: Runner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["build", str(cli_root)]) == 0
    save(UserSettings().with_build_jobs(3))
    assert main(["build", str(cli_root)]) == 0
    save(load().with_build_jobs(None))
    assert main(["build", str(cli_root)]) == 0
    assert cli_runner.jobs == [None, 3, None], "a build did not read the saved number"
    assert capsys.readouterr().err == ""


def test_ctstudio_build_with_a_damaged_file_warns_and_lets_the_runner_choose(
    cli_root: Path, cli_runner: Runner, capsys: pytest.CaptureFixture[str]
) -> None:
    path = settings.default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{{"format": 1, "{BUILD_JOBS}": 0}}', encoding="utf-8")
    before = path.read_bytes()
    assert main(["build", str(cli_root)]) == 0
    assert cli_runner.jobs == [None]
    err = capsys.readouterr().err
    assert err.startswith("Warning: ") and BUILD_JOBS in err, err
    assert "build steps" in err and "ignored for this build" in err, err
    assert path.read_bytes() == before, "the damaged file was changed"
