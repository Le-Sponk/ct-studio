"""P1-T07: workflow contracts so CI cannot silently drop a platform or network signal."""

from __future__ import annotations

from pathlib import Path

import yaml  # Dev dependency via xenon, present in the locked environment.

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # PyYAML's YAML 1.1 resolver turns GitHub's `on:` key into a boolean.
    if True in data:
        data["on"] = data.pop(True)
    return data


def test_local_gate_runs_on_both_oses_and_uploads_evidence() -> None:
    workflow = _workflow("ci.yml")
    assert {"push", "pull_request"} <= workflow["on"].keys()
    job = workflow["jobs"]["check"]
    assert job["strategy"]["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    steps = job["steps"]
    assert any(
        step.get("uses", "").startswith("astral-sh/setup-uv@")
        and step.get("with", {}).get("enable-cache") is True
        for step in steps
    )
    assert any("uv sync --locked" in step.get("run", "") for step in steps)
    assert any("python scripts/check.py" in step.get("run", "") for step in steps)
    assert any("fonts-dejavu-core" in step.get("run", "") for step in steps)
    assert any("coverage xml" in step.get("run", "") for step in steps)
    uploads = [
        step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert uploads and uploads[0].get("if") == "always()"
    assert "tests/artifacts/screens/*.png" in uploads[0]["with"]["path"]
    assert "coverage.xml" in uploads[0]["with"]["path"]


def test_nightly_network_reporter_never_treats_a_skip_as_green() -> None:
    workflow = _workflow("integration.yml")
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["on"]["schedule"][0]["cron"]
    job = workflow["jobs"]["network"]
    assert job["strategy"]["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    steps = job["steps"]
    tests = [step for step in steps if "pytest" in step.get("run", "")]
    assert len(tests) == 1 and "-m network" in tests[0]["run"]
    assert "--junitxml=" in tests[0]["run"]
    reporters = [step for step in steps if "scripts/ci_network.py" in step.get("run", "")]
    assert len(reporters) == 1 and reporters[0].get("if") == "always()"
