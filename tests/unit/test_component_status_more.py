"""P3-T04: status beyond the table — paths, the settings key and how often files are hashed."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from test_component_status import ALL_TOOLS, BLEND, World, out
from test_magic import brres

from ctstudio.core import fsutil
from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.state import ProjectState
from ctstudio.core.components.status import ComponentStatus, State, evaluate, settings_key

pytestmark = pytest.mark.timeout(30)


def test_a_manual_file_outside_the_project_is_shown_as_given(tmp_path: Path) -> None:
    w = World(tmp_path / "p")
    shared = tmp_path / "shared é.brres"
    shared.write_bytes(brres())
    w.part("course_model", mode="manual", file=str(shared))
    assert w.status("course_model") == ComponentStatus(State.MANUAL, (f"using {shared}",))


def test_evaluate_reports_every_part_in_dashboard_order(tmp_path: Path) -> None:
    assert list(evaluate(World(tmp_path), ALL_TOOLS)) == [c.id for c in COMPONENTS]


def test_a_given_state_is_used_instead_of_reading_state_json(tmp_path: Path) -> None:
    w = World(tmp_path)
    w.build("kcl")
    assert evaluate(w, ALL_TOOLS)["kcl"].state is State.READY
    assert evaluate(w, ALL_TOOLS, ProjectState({}))["kcl"].state is State.MISSING


def test_the_settings_key_ignores_the_manual_file_but_not_the_mode(tmp_path: Path) -> None:
    w = World(tmp_path)
    key = settings_key(w.manifest, "kcl")
    w.part("kcl", file="files/other.kcl")
    assert settings_key(w.manifest, "kcl") == key
    w.part("kcl", mode="manual")
    assert settings_key(w.manifest, "kcl") != key


def test_the_blend_only_matters_to_parts_made_in_blender(tmp_path: Path) -> None:
    w = World(tmp_path)
    before = {c: settings_key(w.manifest, c) for c in ("course_model", "posteffect", "minimap")}
    w.project(blend="art/other.blend")
    assert settings_key(w.manifest, "course_model") != before["course_model"]
    assert settings_key(w.manifest, "posteffect") == before["posteffect"]
    assert settings_key(w.manifest, "minimap") == before["minimap"]


def test_unknown_keys_of_any_type_still_give_a_settings_key(tmp_path: Path) -> None:
    w = World(tmp_path)
    w.part("kcl", extra={"when": datetime.date(2026, 11, 2)})
    assert settings_key(w.manifest, "kcl") != settings_key(World(tmp_path).manifest, "kcl")
    with pytest.raises(KeyError):
        settings_key(w.manifest, "objects")


def test_untouched_files_are_never_hashed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w = World(tmp_path)
    for c in ("course_model", "kcl", "minimap", "skybox", "posteffect"):
        w.build(c)
    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - a fresh process

    def no_hashing(path: Path) -> str:
        raise AssertionError(f"hashed {path}")

    monkeypatch.setattr(fsutil, "hash_file", no_hashing)
    assert {c: s.state for c, s in evaluate(w, ALL_TOOLS).items()}["posteffect"] is State.READY


def test_after_a_touch_each_file_is_hashed_once_then_never(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = World(tmp_path)
    parts = ("course_model", "kcl", "minimap", "skybox")
    for c in parts:
        w.build(c)
    for c in parts:
        w.touch(out(c))
    w.touch(BLEND)
    calls: list[str] = []
    real = fsutil.hash_file

    def counting(path: Path) -> str:
        calls.append(path.name)
        return real(path)

    fsutil._cached_digest.cache_clear()  # type: ignore[reportPrivateUsage] - a fresh process
    monkeypatch.setattr(fsutil, "hash_file", counting)
    assert all(evaluate(w, ALL_TOOLS)[c].state is State.READY for c in parts)
    assert sorted(calls) == sorted(
        ["course_model.brres", "course.kcl", "map_model.brres", "vrcorn_model.brres", "track.blend"]
    )
    calls.clear()
    evaluate(w, ALL_TOOLS)
    assert calls == []
