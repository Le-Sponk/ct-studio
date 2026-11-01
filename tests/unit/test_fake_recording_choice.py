"""Which recording each fake replays on each OS (P2-T08b).

Linux recordings exist for more tools than the fakes model. A fake switches to a Linux
recording only when that pair is listed in ``LINUX_REPLAYED``; the rest keep replaying
the Windows run (translated by each fake) until a later task moves them over.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import fake_runtime  # type: ignore[reportMissingImports] - tests/fakes on sys.path
import pytest


def _source(monkeypatch: pytest.MonkeyPatch, os_name: str, tool: str, version: str, kind: str):
    """Which file ``recordings`` reads, using stand-in files that differ per OS."""
    real = fake_runtime.RECORDINGS / tool / version
    assert (real / f"windows-{kind}.json").exists() and (real / f"linux-{kind}.json").exists()
    root = Path(tempfile.mkdtemp())
    folder = root / tool / version
    folder.mkdir(parents=True)
    for system in ("windows", "linux"):
        (folder / f"{system}-{kind}.json").write_text(json.dumps(system), encoding="utf-8")
    monkeypatch.setattr(fake_runtime, "RECORDINGS", root)
    monkeypatch.setattr(fake_runtime.os, "name", os_name)
    try:
        return fake_runtime.recordings(tool, version, kind)
    finally:
        monkeypatch.undo()
        shutil.rmtree(root)


HELP = [("wszst", "2.42a"), ("wkclt", "2.42a"), ("wkmpt", "2.42a"), ("wimgt", "2.42a")]
HELP += [("abmatt", "1.3.2"), ("blender", "5.2.2")]
OPTIONS = [(tool, "options") for tool, _version in HELP[:4]]


def test_only_listed_linux_recordings_are_replayed() -> None:
    expected = {("rszst", "cli"), *((tool, "help") for tool, _v in HELP), *OPTIONS}
    assert fake_runtime.LINUX_REPLAYED == frozenset(expected)


@pytest.mark.parametrize(
    ("tool", "version", "kind"),
    [("rszst", "5.11.5", "cli"), *((tool, version, "help") for tool, version in HELP)]
    + [(tool, "2.42a", "options") for tool, _kind in OPTIONS],
)
def test_linux_replays_its_own_help_cli_and_options(
    monkeypatch: pytest.MonkeyPatch, tool: str, version: str, kind: str
) -> None:
    assert _source(monkeypatch, "posix", tool, version, kind) == "linux"
    assert _source(monkeypatch, "nt", tool, version, kind) == "windows"


@pytest.mark.parametrize(
    ("tool", "version"),
    [
        ("wszst", "2.42a"),
        ("wkclt", "2.42a"),
        ("wkmpt", "2.42a"),
        ("wimgt", "2.42a"),
        ("blender", "5.2.2"),
    ],
)
def test_operations_still_replay_the_windows_run(
    monkeypatch: pytest.MonkeyPatch, tool: str, version: str
) -> None:
    # Linux ops equal Windows apart from the listed text differences (test_linux_ops.py).
    assert (fake_runtime.RECORDINGS / tool / version / "linux-ops.json").exists()
    assert _source(monkeypatch, "posix", tool, version, "ops") == "windows"
