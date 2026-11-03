"""P4-T06: issues kept on disk, and a skipped step still reports what it found.

``Issue`` goes to and from plain JSON (``issues.json``, the build cache). A file inside the
project is stored relative to it, so a moved project still points at the right file. The
cache keeps each step's issues with its entry; a step skipped as unchanged reports them
again (P4-T05b's object warnings were lost on a skipped assemble).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from build_runner_helpers import Recorder, make_root, step

from ctstudio.core.build.cache import CACHE_FILE, BuildCache
from ctstudio.core.build.events import BuildSummary, NodeSkipped
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import BuildContext, NodeResult
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue, issue_from_json, issue_to_json

pytestmark = pytest.mark.timeout(60)


def test_an_issue_round_trips_with_project_files_stored_relative(tmp_path: Path) -> None:
    root = tmp_path / "Pistë 日本"
    full = Issue(
        "error",
        "minimap",
        "VALIDATE_PART_MISSING",
        "Minimap (map_model.brres) is not in castle_course.szs.",
        "Choose it on the dashboard.",
        "wszst analyze",
        root / "build" / "castle_course.szs",
        "https://mkwiiki.org/wiki/Creating_a_Minimap",
    )
    data = issue_to_json(full, root)
    assert data["file"] == "build/castle_course.szs"
    assert issue_from_json(data, root) == full
    moved = tmp_path / "moved"
    assert issue_from_json(data, moved).file == moved / "build" / "castle_course.szs"
    outside = Issue("warning", "objects", "X", "m", None, "wkmpt", tmp_path / "lib")
    assert issue_from_json(issue_to_json(outside, root), root) == outside
    bare = Issue("hint", "kmp", "WSZST_HINT", "Self linked item route.", None, "wszst check")
    assert issue_to_json(bare, root) == {
        "severity": "hint",
        "component": "kmp",
        "code": "WSZST_HINT",
        "message": "Self linked item route.",
        "hint": None,
        "source": "wszst check",
        "file": None,
        "wiki": None,
    }
    assert issue_from_json(issue_to_json(bare, root), root) == bare


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"severity": "fatal", "component": "a", "code": "C", "message": "m", "source": "s"},
        {"severity": "error", "component": 1, "code": "C", "message": "m", "source": "s"},
        {"severity": "error", "component": "a", "code": "C", "message": "m"},
        {
            "severity": "error",
            "component": "a",
            "code": "C",
            "message": "m",
            "source": "s",
            "hint": 5,
        },
        {
            "severity": "error",
            "component": "a",
            "code": "C",
            "message": "m",
            "source": "s",
            "file": "",
        },
    ],
    ids=["a list", "severity", "component", "no source", "hint", "empty file"],
)
def test_a_damaged_issue_is_refused(bad: object, tmp_path: Path) -> None:
    with pytest.raises((TypeError, ValueError, KeyError)):
        issue_from_json(bad, tmp_path)


MANIFEST = Manifest(project=ProjectInfo(name="T", slot="castle_course"))
WARNING = Issue(
    "warning", "objects", "OBJECTS_FILES_MISSING", "itembox needs …", "Add it.", "wkmpt"
)


def _warns(_ctx: BuildContext) -> NodeResult:
    return NodeResult((WARNING,))


def _build(root: Path, cache: BuildCache) -> tuple[BuildSummary, Recorder]:
    recorder = Recorder()
    summary = run_build(
        BuildGraph(root, [step(root, "a", _warns)]),
        cache,
        BuildRequest(MANIFEST, "test", {}, {}),
        recorder,
        cancel=CancelToken(),
    )
    return summary, recorder


def test_a_skipped_step_reports_the_issues_it_found_when_it_ran(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    first, _ = _build(root, BuildCache.load(root))
    assert first.ran == ("a",) and first.issues == (WARNING,)
    again, recorder = _build(root, BuildCache.load(root))  # a new process: read from disk
    assert again.skipped == ("a",)
    assert again.issues == (WARNING,), "still true: nothing it read changed"
    assert NodeSkipped("a", (WARNING,)) in recorder.events
    assert again.log is not None
    lines = again.log.read_text(encoding="utf-8")
    assert "[a] warning: itembox needs … Add it. (found before)" in lines


def test_a_step_that_must_run_again_gets_no_old_issues(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    _build(root, BuildCache.load(root))
    cache = BuildCache.load(root)
    node = step(root, "a", _warns, params={"changed": True})
    lookup = cache.check(node, {})
    assert not lookup.fresh and lookup.issues == ()


@pytest.mark.parametrize("issues", ["{}", '""', '"x"', "5"])
def test_a_cache_entry_with_a_damaged_issue_list_is_ignored(tmp_path: Path, issues: str) -> None:
    root = make_root(tmp_path)
    _build(root, BuildCache.load(root))
    path = root / CACHE_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["nodes"]["a"]["issues"] = json.loads(issues)
    path.write_text(json.dumps(data), encoding="utf-8")
    again, _ = _build(root, BuildCache.load(root))
    assert again.ran == ("a",), "a damaged cache reads as empty, so the step runs"
