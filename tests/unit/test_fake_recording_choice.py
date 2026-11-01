"""Which recording each fake replays on each OS (P2-T08b).

Linux recordings exist for more tools than the fakes model. A fake switches to a Linux
recording only when that pair is listed in ``LINUX_REPLAYED``; the rest keep replaying
the Windows run (translated by each fake) until a later task moves them over.
"""

from __future__ import annotations

import json

import fake_runtime  # type: ignore[reportMissingImports] - tests/fakes on sys.path
import pytest


def _source(monkeypatch: pytest.MonkeyPatch, os_name: str, tool: str, version: str, kind: str):
    monkeypatch.setattr(fake_runtime.os, "name", os_name)
    loaded = fake_runtime.recordings(tool, version, kind)
    folder = fake_runtime.RECORDINGS / tool / version
    for system in ("windows", "linux"):
        path = folder / f"{system}-{kind}.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) == loaded:
            return system
    raise AssertionError((tool, kind))


def test_only_listed_linux_recordings_are_replayed() -> None:
    assert fake_runtime.LINUX_REPLAYED == frozenset({("rszst", "cli")})


def test_linux_replays_rszst_cli_from_its_own_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _source(monkeypatch, "posix", "rszst", "5.11.5", "cli") == "linux"
    assert _source(monkeypatch, "nt", "rszst", "5.11.5", "cli") == "windows"


@pytest.mark.parametrize(
    ("tool", "version", "kind"),
    [
        ("wszst", "2.42a", "help"),
        ("wszst", "2.42a", "ops"),
        ("wkclt", "2.42a", "options"),
        ("abmatt", "1.3.2", "help"),
        ("blender", "5.2.2", "ops"),
        ("blender", "5.2.2", "help"),
    ],
)
def test_other_linux_recordings_wait_for_their_fake(
    monkeypatch: pytest.MonkeyPatch, tool: str, version: str, kind: str
) -> None:
    assert (fake_runtime.RECORDINGS / tool / version / f"linux-{kind}.json").exists()
    assert _source(monkeypatch, "posix", tool, version, kind) == "windows"
