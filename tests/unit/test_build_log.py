"""P4-T03b: the per-build log ``.ctstudio/logs/build-<UTC time>.log``.

One readable line per event (time, step, what happened, issues and hints), so a user can send
it when asking for help. Only the newest 20 logs are kept. A log that cannot be written
never fails the build.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest
from build_runner_helpers import build, fail, make_root, step

from ctstudio.core.build import build_log
from ctstudio.core.build.build_log import KEEP, LOG_DIR, BuildLog
from ctstudio.core.build.events import (
    BuildFinished,
    BuildStarted,
    BuildSummary,
    LogLine,
    NodeFailed,
    NodeFinished,
    NodeSkipped,
    NodeStarted,
)
from ctstudio.core.build.node import BuildContext, NodeResult
from ctstudio.core.validation.issues import Issue

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


def logs(root: Path) -> list[Path]:
    return sorted((root / LOG_DIR).glob("build-*.log"))


def test_a_build_writes_one_readable_log(root: Path) -> None:
    def talk(ctx: BuildContext) -> NodeResult:
        ctx.log("wszst: 3 files staged")
        issue = Issue("warning", "kmp", "kmp.x", "No checkpoints.", "Add some in KMP Cloud.", "x")
        return NodeResult(issues=(issue,))

    summary, _ = build(root, [step(root, "a", talk), step(root, "b", fail)], jobs=1)
    [log] = logs(root)
    assert summary.log == log
    text = log.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0].endswith("Build started: 2 steps (a, b)")
    assert any(line.endswith("[a] started") for line in lines)
    assert any(line.endswith("[a] wszst: 3 files staged") for line in lines)
    assert any(
        line.endswith("[a] warning: No checkpoints. Add some in KMP Cloud.") for line in lines
    )
    failed = [line for line in lines if "[b] FAILED: " in line]
    assert len(failed) == 1 and "wszst" in failed[0], failed
    assert "Build failed: 1 ran, 0 skipped, 1 failed, 0 not run in " in lines[-1]
    assert all(line[:2] == "20" and line[10] == "T" for line in lines), "UTC timestamps"


def test_skips_and_a_successful_build(root: Path) -> None:
    build(root, [step(root, "a")])
    summary, _ = build(root, [step(root, "a")])
    text = summary.log.read_text(encoding="utf-8") if summary.log else ""
    assert "[a] skipped: nothing it uses changed" in text
    assert "Build succeeded: 0 ran, 1 skipped, 0 failed, 0 not run in " in text.splitlines()[-1]


def test_each_build_gets_its_own_log_and_only_twenty_are_kept(root: Path) -> None:
    folder = root / LOG_DIR
    folder.mkdir(parents=True)
    for i in range(25):
        (folder / f"build-2026-01-01T00-00-{i:02d}.000000Z.log").write_text("old", encoding="utf-8")
    (folder / "notes.txt").write_text("mine", encoding="utf-8")
    summary, _ = build(root, [step(root, "a")])
    kept = logs(root)
    assert len(kept) == KEEP == 20
    assert summary.log in kept
    assert kept[0].name == "build-2026-01-01T00-00-06.000000Z.log", "the oldest went first"
    assert (folder / "notes.txt").exists(), "only build logs are pruned"


def test_two_logs_in_the_same_microsecond_do_not_collide(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = datetime(2026, 11, 3, 1, 2, 3, 456789, tzinfo=UTC)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Frozen:
            return cls.fromtimestamp(frozen.timestamp(), tz)

    monkeypatch.setattr(build_log, "datetime", Frozen)
    opened = [BuildLog.open(root) for _ in range(3)]
    names = [log.path.name for log in opened if log.path]
    assert names == [
        "build-2026-11-03T01-02-03.456789Z.log",
        "build-2026-11-03T01-02-03.456789Z-1.log",
        "build-2026-11-03T01-02-03.456789Z-2.log",
    ]
    for log in opened:
        log.close()


def test_the_log_can_be_read_during_the_build_and_is_closed_after(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written line by line (a crash keeps what happened) and let go afterwards (Windows)."""
    seen: list[str] = []

    def peek(_ctx: BuildContext) -> NodeResult:
        [log] = logs(root)
        seen.append(log.read_text(encoding="utf-8"))
        return NodeResult()

    closed: list[Path | None] = []
    real_close = BuildLog.close

    def close(self: BuildLog) -> None:
        closed.append(self.path)
        real_close(self)

    monkeypatch.setattr(BuildLog, "close", close)
    summary, _ = build(root, [step(root, "a", peek)])
    # Lines written before the step began are already on disk. ("[a] started" is written
    # by the build's own thread and may land just after the step starts, so not that one.)
    assert "Build started: 1 steps (a)" in seen[0]
    assert summary.log is not None
    assert closed == [summary.log], "closed by the build, not left to the garbage collector"
    summary.log.unlink()  # Windows refuses to delete a file that is still open
    assert not summary.log.exists()


def test_an_unwritable_log_does_not_fail_the_build(
    root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (root / ".ctstudio").mkdir()
    (root / LOG_DIR).write_text("a file where the folder should be", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        summary, _ = build(root, [step(root, "a")])
    assert summary.outcome == "succeeded"
    assert summary.log is None
    assert "build log" in caplog.text


def test_every_event_kind_has_a_line(root: Path) -> None:
    log = BuildLog.open(root)
    summary = BuildSummary("cancelled", (), (), (), ("a",), ("b",), (), 1.5, None)
    for event in (
        BuildStarted(("a", "b")),
        NodeStarted("a"),
        LogLine("a", "hello\nsecond line"),
        NodeSkipped("c"),
        NodeFinished("a", 0.25, ()),
        NodeFailed("a", "a was cancelled.", None, True),
        NodeFailed("b", "b failed.", None, False, details="tool said\nthis"),
        BuildFinished(summary),
    ):
        log.write(event)
    log.close()
    assert log.path is not None
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert [line.split(" ", 1)[1] for line in lines] == [
        "Build started: 2 steps (a, b)",
        "[a] started",
        "[a] hello",
        "[a] second line",
        "[c] skipped: nothing it uses changed",
        "[a] finished in 0.25 s",
        "[a] cancelled: a was cancelled.",
        "[b] FAILED: b failed.",
        "[b] tool output: tool said",
        "[b] tool output: this",
        "Build cancelled: 0 ran, 0 skipped, 0 failed, 1 not run (1 cancelled) in 1.5 s",
    ]
