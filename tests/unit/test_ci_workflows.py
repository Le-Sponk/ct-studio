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


def _steps_running(steps: list[dict], text: str) -> list[dict]:
    return [step for step in steps if text in step.get("run", "")]


def test_nightly_integration_bootstraps_real_tools_and_explains_every_skip() -> None:
    workflow = _workflow("integration.yml")
    triggers = workflow["on"]
    assert "workflow_dispatch" in triggers and triggers["schedule"][0]["cron"]
    watched = triggers["push"]["paths"]
    for path in (
        ".github/workflows/integration.yml",
        "scripts/ci_network.py",
        "scripts/tool_catalogue.py",
        "tests/integration/expected_skips.toml",
    ):
        assert path in watched
    job = workflow["jobs"]["integration"]
    assert job["strategy"]["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    assert job["strategy"]["fail-fast"] is False
    assert job["env"]["QT_QPA_PLATFORM"] == "offscreen"
    assert job["env"]["CTSTUDIO_RSZST_WINE"] == "1"
    steps = job["steps"]
    caches = [s for s in steps if s.get("uses", "").startswith("actions/cache@")]
    assert len(caches) == 1
    assert caches[0]["with"]["path"] == ".tools/_downloads"
    assert "hashFiles('scripts/tool_catalogue.py')" in caches[0]["with"]["key"]
    linux = [s for s in steps if s.get("if") == "runner.os == 'Linux'"]
    assert any("wine" in s.get("run", "") and "libegl1" in s.get("run", "") for s in linux)
    assert _steps_running(steps, "python scripts/bootstrap_tools.py")
    windows = [s for s in steps if s.get("if") == "runner.os == 'Windows'"]
    assert any("bootstrap_tools.py --only riistudio" in s.get("run", "") for s in windows)
    assert _steps_running(steps, "python scripts/fixtures/make_fixtures.py")
    assert _steps_running(steps, "python spikes/s2_blender.py")
    tests = _steps_running(steps, "pytest")
    assert len(tests) == 1
    assert '-m "(integration or network) and not slow"' in tests[0]["run"]
    assert "--junitxml=tests/artifacts/integration.xml" in tests[0]["run"]
    reporters = _steps_running(steps, "scripts/ci_network.py")
    assert len(reporters) == 1 and reporters[0].get("if") == "always()"
    assert "--expected tests/integration/expected_skips.toml" in reporters[0]["run"]
    assert "--os ${{ runner.os == 'Windows' && 'windows' || 'linux' }}" in reporters[0]["run"]
    uploads = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@")]
    assert uploads and uploads[0].get("if") == "always()"
    assert "tests/artifacts/integration.xml" in uploads[0]["with"]["path"]


def test_the_expected_skip_list_parses_for_both_oses() -> None:
    import sys

    sys.path.insert(0, str(WORKFLOWS.parents[1] / "scripts"))
    from ci_network import load_expected

    listed = WORKFLOWS.parents[1] / "tests" / "integration" / "expected_skips.toml"
    for os_name in ("linux", "windows"):
        assert load_expected(listed, os_name)  # each OS has explained skips
