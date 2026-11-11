"""P5-T06a: which folders a project's watcher covers, and which changes count.

Pure tests: no watcher thread runs here (``test_project_watcher.py`` runs real ones).
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from ctstudio.core.project import manifest as m
from ctstudio.core.project.watch import ChangeFilter, WatchPlan, watch_plan

pytestmark = pytest.mark.timeout(30)


def manifest(blend: str | None = None, /, **parts: tuple[str, str]) -> m.Manifest:
    """A manifest with an optional .blend and ``part=(mode, file)`` choices."""
    made = m.Manifest(m.ProjectInfo(name="T", blend=blend))
    components = made.components
    for part, (mode, file) in parts.items():
        table = dataclasses.replace(getattr(components, part), mode=mode, file=file)
        components = dataclasses.replace(components, **{part: table})
    return dataclasses.replace(made, components=components)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "Pistë é" / "proj ect"
    folder.mkdir(parents=True)
    return folder


# --- what is watched -------------------------------------------------------------------------


def test_a_project_with_everything_inside_watches_only_its_folder(root: Path) -> None:
    plan = watch_plan(root, manifest("art/track.blend", kcl=("manual", "files/course.kcl")))
    assert plan == WatchPlan(root, {})


def test_an_outside_blend_watches_its_folder_for_that_name(root: Path, tmp_path: Path) -> None:
    blend = tmp_path / "Art é" / "track.blend"
    plan = watch_plan(root, manifest(str(blend)))
    assert plan.root == root
    assert plan.outside == {blend.parent: frozenset({"track.blend"})}


def test_a_relative_path_leading_out_of_the_project_is_outside(root: Path) -> None:
    plan = watch_plan(root, manifest("../shared/track.blend"))
    assert plan.outside == {root.parent / "shared": frozenset({"track.blend"})}


def test_outside_files_in_one_folder_share_it(root: Path, tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    plan = watch_plan(
        root,
        manifest(
            str(shared / "track.blend"),
            kcl=("manual", str(shared / "course.kcl")),
            kmp=("manual", str(tmp_path / "other" / "course.kmp")),
        ),
    )
    assert plan.outside == {
        shared: frozenset({"track.blend", "course.kcl"}),
        tmp_path / "other": frozenset({"course.kmp"}),
    }


def test_a_file_kept_for_an_automatic_part_is_not_watched(root: Path, tmp_path: Path) -> None:
    plan = watch_plan(root, manifest(kcl=("auto", str(tmp_path / "old" / "course.kcl"))))
    assert plan.outside == {}


def test_an_outside_post_effect_folder_is_watched_itself(root: Path, tmp_path: Path) -> None:
    effects = tmp_path / "effects é"
    plan = watch_plan(root, manifest(posteffect=("manual", str(effects))))
    assert plan.outside == {effects: None}


@pytest.mark.parametrize("folder_first", [True, False])
def test_a_watched_folder_wins_over_single_names_in_it(
    root: Path, tmp_path: Path, folder_first: bool
) -> None:
    effects = tmp_path / "effects"
    parts = {"posteffect": ("manual", str(effects)), "kmp": ("manual", str(effects / "c.kmp"))}
    ordered = parts if folder_first else dict(reversed(list(parts.items())))
    assert watch_plan(root, manifest(**ordered)).outside == {effects: None}


# --- which changes count ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "counts"),
    [
        (".ctstudio/stage/course_model.brres", True),  # a made file edited outside
        ("art/track.BLEND1", False),  # Blender's backups in any case (Linux keeps it)
        (".ctstudio/stage/posteffect/posteffect.bfg", True),
        (".ctstudio/stage", True),
        ("ctstudio.toml", True),
        ("files/course.kcl", True),
        ("art/track.blend", True),
        ("buildings/house.brres", True),  # not the build folder
        (".ctstudio-old/x", True),
        ("stage/x", True),
        (".ctstudio", False),
        (".ctstudio/state.json", False),
        (".ctstudio/lock", False),
        (".ctstudio/logs/build.log", False),
        (".ctstudio/backups/2026/files/course.kcl", False),
        (".ctstudio/staged/x", False),
        ("build/track.szs", False),
        (".git/index", False),
        ("art/track.blend1", False),
        ("art/track.blend12", False),
        ("art/track.blend@", False),
        ("", False),  # the project folder itself says nothing
    ],
)
def test_changes_inside_the_project(root: Path, rel: str, counts: bool) -> None:
    check = ChangeFilter.of(WatchPlan(root, {}))
    try:
        got: bool | Exception = check.relevant(str(root / rel) if rel else str(root))
    except Exception as exc:  # a crash is a wrong answer too (it would end the watcher)
        got = exc
    assert got is counts


def test_outside_only_the_watched_names_count(root: Path, tmp_path: Path) -> None:
    art = tmp_path / "Art é"
    check = ChangeFilter.of(WatchPlan(root, {art: frozenset({"track.blend"})}))
    assert check.relevant(str(art / "track.blend"))
    assert not check.relevant(str(art / "track.blend1"))
    assert not check.relevant(str(art / "notes.txt"))
    assert not check.relevant(str(art))
    assert not check.relevant(str(tmp_path / "elsewhere" / "track.blend"))
    assert not check.relevant(str(art / "sub" / "track.blend"))


def test_outside_names_follow_the_systems_case_rule(root: Path, tmp_path: Path) -> None:
    art = tmp_path / "art"
    check = ChangeFilter.of(WatchPlan(root, {art: frozenset({"track.blend"})}))
    assert check.relevant(str(art / "TRACK.BLEND")) is (os.name == "nt")


def test_everything_in_a_watched_outside_folder_counts(root: Path, tmp_path: Path) -> None:
    effects = tmp_path / "effects"
    check = ChangeFilter.of(WatchPlan(root, {effects: None}))
    assert check.relevant(str(effects / "posteffect.blight"))
    assert check.relevant(str(effects))
    assert not check.relevant(str(tmp_path / "effects2" / "posteffect.blight"))


def test_a_change_reported_under_the_real_path_still_counts(tmp_path: Path) -> None:
    real = tmp_path / "real é"
    (real / "art").mkdir(parents=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError as exc:  # Windows without symlink rights: the Linux CI run covers it
        pytest.skip(f"cannot make a folder symlink here: {exc}")
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_outside = tmp_path / "outside link"
    linked_outside.symlink_to(outside, target_is_directory=True)
    check = ChangeFilter.of(WatchPlan(link, {linked_outside: frozenset({"t.blend"})}))
    assert check.relevant(str(real / "art" / "t.blend"))
    assert check.relevant(str(link / "art" / "t.blend"))
    assert check.relevant(str(outside / "t.blend"))
    assert not check.relevant(str(real / ".ctstudio" / "state.json"))
