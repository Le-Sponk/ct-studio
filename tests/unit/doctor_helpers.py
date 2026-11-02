"""Shared helpers for the doctor unit tests: fake trees, environments and a probe stub."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest

from ctstudio.core.tools import doctor
from ctstudio.core.tools.discovery import DiscoveryEnvironment, ToolLocation
from ctstudio.core.tools.doctor import ToolCheck, diagnose
from ctstudio.core.tools.spec import ToolSpec
from ctstudio.core.tools.versions import VersionCache, VersionResult


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake binary", encoding="utf-8")
    path.chmod(0o755)
    return path


def _env(
    tmp_path: Path, platform: Literal["windows", "linux"], path: str = ""
) -> DiscoveryEnvironment:
    return DiscoveryEnvironment(
        platform=platform,
        root=tmp_path / "system",
        home=tmp_path / "home",
        variables={"PATH": path, "ProgramFiles": str(tmp_path / "Program Files")},
        sandbox=None,
    )


def stub_probes(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Answer every probe with version 9.9 (or what ``versions`` maps a tool id to)."""
    calls: list[dict[str, object]] = []
    versions: dict[str, VersionResult | str] = {}

    def fake_probe(
        items: list[tuple[ToolSpec, ToolLocation]], **kwargs: object
    ) -> list[VersionResult]:
        calls.append({"ids": [spec.id for spec, _ in items], **kwargs})
        out = []
        for spec, location in items:
            answer = versions.get(spec.id, "9.9")
            if isinstance(answer, VersionResult):
                out.append(replace(answer, location=location))
            else:
                out.append(VersionResult(spec.id, replace(location, version=answer), "probed"))
        return out

    monkeypatch.setattr(doctor, "probe_versions", fake_probe)
    calls.append({"versions": versions})
    return calls


def _versions(probes: list[dict[str, object]]) -> dict[str, VersionResult | str]:
    return probes[0]["versions"]  # type: ignore[return-value]


def _check(report: doctor.Report, tool_id: str) -> ToolCheck:
    [check] = [c for c in report.tools if c.tool_id == tool_id]
    return check


def _run(tmp_path: Path, env: DiscoveryEnvironment, **kwargs: object) -> doctor.Report:
    return diagnose(
        environment=env,
        dev_root=tmp_path / "no-dev-tools",
        cache=VersionCache(tmp_path / "cache.json"),
        **kwargs,  # type: ignore[arg-type]
    )
