"""Shared pytest fixtures (TESTING_STRATEGY §2).

``fake_tools_path`` puts real executables for the fake external tools (``tests/fakes``)
first on PATH, so discovery, version probes and the runner see them exactly as they would
see installed tools. Each test gets its own call log.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fakes"))

import install as fake_install
from fake_runtime import LOG_ENV


@dataclass(frozen=True)
class FakeTools:
    directory: Path
    executables: dict[str, Path]
    log: Path

    def resolve(self, tool: str) -> Path:
        return self.executables[tool]

    def calls(self) -> list[dict[str, object]]:
        """Every fake invocation in this test, in call order, as ``{"tool", "argv", "cwd"}``."""
        return [
            json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.log.glob("*.json"))
        ]


@pytest.fixture(scope="session")
def _fake_tool_executables(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, Path]]:
    directory = tmp_path_factory.mktemp("fake tools é")
    return directory, fake_install.install(directory)


@pytest.fixture
def fake_tools_path(
    _fake_tool_executables: tuple[Path, dict[str, Path]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FakeTools:
    directory, executables = _fake_tool_executables
    log = tmp_path / "fake-calls"
    log.mkdir()
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv(LOG_ENV, str(log))
    return FakeTools(directory, executables, log)
