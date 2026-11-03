"""P4-T06: the validate step checks ``build/<slot>.szs`` and writes ``.ctstudio/issues.json``.

``wszst check`` and ``wszst analyze --json`` are replaced by their recorded real 2.42a output
(``tests/fakes/recordings/wszst/2.42a``), so these tests run without Wiimm. Each required
part that ``analyze`` reports missing is one error naming it, whether or not there is a KMP
(``check`` only names missing files when there is one, so its duplicate lines for those
parts are dropped). Test builds never fail on findings; release builds (or ``strict``) fail
when there is any error, and still report every finding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from build_runner_helpers import Recorder, make_root

from ctstudio.core.build import validate
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildSummary, NodeFailed
from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Profile
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.build.validate import ISSUES_FILE, validate_step
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.validation.issues import Issue, issue_from_json
from ctstudio.core.validation.wszst_check import parse_check

pytestmark = pytest.mark.timeout(60)
RECORDINGS = Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "wszst" / "2.42a"
MANIFEST = Manifest(project=ProjectInfo(name="T", slot="castle_course"))
VERSIONS = {"wszst": "2.42a"}


def recorded(case: str) -> dict[str, Any]:
    rows = json.loads((RECORDINGS / "windows-ops.json").read_text(encoding="utf-8"))
    return next(row for row in rows if row["case"] == case)


# The fixture stage (KCL + KMP only): analyze reports the course, skybox and minimap missing.
CHECK = parse_check(recorded("check")["stdout"], Path("t.szs"), exit_code=2)
ANALYZE: dict[str, object] = json.loads(recorded("analyze json")["stdout"])
COMPLETE = {**ANALYZE, "sha1_course": "c9", "sha1_vrcorn": "c9", "sha1_minimap": "c9"}
NO_KMP = {**ANALYZE, "sha1_kmp": ""}


class Wiimm:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.check: list[Issue] = CHECK
        self.analyze: dict[str, object] = ANALYZE
        self.asked: list[Path] = []
        monkeypatch.setattr(validate, "check", self._check)
        monkeypatch.setattr(validate, "analyze", self._analyze)

    def _check(self, szs: Path, **_k: object) -> list[Issue]:
        self.asked.append(szs)
        return self.check

    def _analyze(self, szs: Path, **_k: object) -> dict[str, object]:
        self.asked.append(szs)
        return self.analyze


@pytest.fixture
def wiimm(monkeypatch: pytest.MonkeyPatch) -> Wiimm:
    return Wiimm(monkeypatch)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = make_root(tmp_path)
    (project / "build").mkdir()
    (project / "build" / "castle_course.szs").write_bytes(b"Yaz0 built")
    return project


def run(
    root: Path, profile: Profile = "test", strict: bool | None = None
) -> tuple[BuildSummary, Recorder]:
    recorder = Recorder()
    summary = run_build(
        BuildGraph(root, [validate_step(root, MANIFEST, profile, strict)]),
        BuildCache.load(root),
        BuildRequest(MANIFEST, profile, {}, VERSIONS),
        recorder,
        cancel=CancelToken(),
    )
    return summary, recorder


def written(root: Path) -> list[Issue]:
    data = json.loads((root / ISSUES_FILE).read_text(encoding="utf-8"))
    assert data["format"] == 1 and data["track"] == "build/castle_course.szs"
    return [issue_from_json(item, root) for item in data["issues"]]


def test_the_step_reads_the_slot_szs_and_writes_issues_json(root: Path) -> None:
    node = validate_step(root, MANIFEST, "release")
    assert node.id == "validate"
    assert node.inputs == (root / "build" / "castle_course.szs",)
    assert node.outputs == (root / ".ctstudio" / "issues.json",)
    assert node.tools == ("wszst",)
    assert dict(node.params) == {"strict": True}
    assert dict(validate_step(root, MANIFEST, "test").params) == {"strict": False}
    assert dict(validate_step(root, MANIFEST, "test", strict=True).params) == {"strict": True}
    assert dict(validate_step(root, MANIFEST, "release", strict=False).params) == {"strict": False}


def test_missing_parts_are_errors_and_checks_findings_follow(root: Path, wiimm: Wiimm) -> None:
    summary, _ = run(root)
    assert summary.outcome == "succeeded", "a test build never fails on findings"
    szs = root / "build" / "castle_course.szs"
    assert wiimm.asked == [szs, szs]
    errors = [i for i in summary.issues if i.severity == "error"]
    assert [(i.component, i.code, i.message) for i in errors] == [
        (
            "course_model",
            "VALIDATE_PART_MISSING",
            "Course model (course_model.brres) is not in"
            " castle_course.szs, so the game cannot load the track.",
        ),
        (
            "minimap",
            "VALIDATE_PART_MISSING",
            "Minimap (map_model.brres) is not in"
            " castle_course.szs, so the game cannot load the track.",
        ),
        (
            "skybox",
            "VALIDATE_PART_MISSING",
            "Skybox (vrcorn_model.brres) is not in"
            " castle_course.szs, so the game cannot load the track.",
        ),
    ]
    assert errors[0].hint == "Choose its file on the dashboard, then build again."
    assert errors[0].wiki == "https://mkwiiki.org/wiki/Creating_a_BRRES_with_RiiStudio"
    assert all(i.file == szs and i.source == "wszst analyze" for i in errors)
    rest = summary.issues[len(errors) :]
    assert [i.code for i in rest] == [
        "WSZST_INFO",
        "WSZST_WARNING",
        "WSZST_WARNING",
        "WSZST_HINT",
        "WSZST_HINT",
    ]
    assert not any(i.code == "WSZST_MISSING_FILE" for i in rest), "said once, by analyze"
    assert written(root) == list(summary.issues)


def test_parts_are_found_missing_without_a_kmp_too(root: Path, wiimm: Wiimm) -> None:
    wiimm.check, wiimm.analyze = [], {**COMPLETE, "sha1_kmp": ""}
    summary, _ = run(root)
    assert [i.component for i in summary.issues] == ["kmp"]
    assert summary.issues[0].message.startswith("Course data (course.kmp) is not in")


def test_a_check_missing_file_that_is_not_a_part_is_kept(root: Path, wiimm: Wiimm) -> None:
    other = Issue(
        "warning",
        "itembox",
        "WSZST_MISSING_FILE",
        "Missing file:    ./itembox.brres",
        "Add the missing file to the track stage and rebuild.",
        "wszst check",
        Path("itembox.brres"),
    )
    wiimm.check, wiimm.analyze = [other], COMPLETE
    summary, _ = run(root)
    assert summary.issues == (other,)


def test_a_part_analyze_does_not_mention_is_not_called_missing(root: Path, wiimm: Wiimm) -> None:
    """Only an empty fingerprint means "missing"; a key a newer Wiimm dropped proves nothing."""
    wiimm.check = []
    wiimm.analyze = {k: v for k, v in COMPLETE.items() if k != "sha1_minimap"}
    assert run(root)[0].issues == ()


def test_a_clean_track_writes_an_empty_list(root: Path, wiimm: Wiimm) -> None:
    wiimm.check, wiimm.analyze = [], COMPLETE
    summary, _ = run(root, "release")
    assert summary.outcome == "succeeded" and summary.issues == ()
    assert written(root) == []


def test_a_release_build_fails_on_an_error_and_still_reports_everything(
    root: Path, wiimm: Wiimm
) -> None:
    summary, recorder = run(root, "release")
    assert summary.outcome == "failed" and summary.failed == ("validate",)
    [failed] = [e for e in recorder.events if isinstance(e, NodeFailed)]
    assert failed.message == ("castle_course.szs has 3 errors, so this release build stops here.")
    assert failed.hint == "Fix the errors listed, or make a test build to try the track anyway."
    *found, stop = summary.issues
    assert len(found) == 8 and found[0].code == "VALIDATE_PART_MISSING"
    assert (stop.code, stop.message) == ("VALIDATE_STRICT", failed.message)
    assert failed.issues == summary.issues
    assert written(root) == found, "issues.json is written even when it fails"


def test_warnings_alone_never_fail_a_release_build(root: Path, wiimm: Wiimm) -> None:
    wiimm.analyze = COMPLETE
    wiimm.check = [i for i in CHECK if i.code != "WSZST_MISSING_FILE"]
    summary, _ = run(root, "release")
    assert summary.outcome == "succeeded" and len(summary.issues) == 5


def test_strict_is_the_users_choice_over_the_profile(root: Path, wiimm: Wiimm) -> None:
    assert run(root, "test", strict=True)[0].outcome == "failed"
    assert run(root, "release", strict=False)[0].outcome == "succeeded"


def test_one_error_is_said_in_the_singular(root: Path, wiimm: Wiimm) -> None:
    wiimm.check, wiimm.analyze = [], {**COMPLETE, "sha1_kcl": ""}
    _, recorder = run(root, "release")
    [failed] = [e for e in recorder.events if isinstance(e, NodeFailed)]
    assert failed.message == "castle_course.szs has 1 error, so this release build stops here."


def test_an_unchanged_track_is_not_checked_again_but_its_issues_stay(
    root: Path, wiimm: Wiimm
) -> None:
    first, _ = run(root)
    again, _ = run(root)
    assert again.skipped == ("validate",) and again.issues == first.issues
    assert len(wiimm.asked) == 2, "wszst ran only for the first build"
    (root / "build" / "castle_course.szs").write_bytes(b"Yaz0 built again, longer")
    assert run(root)[0].ran == ("validate",)
