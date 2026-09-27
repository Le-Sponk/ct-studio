"""P1-T08 contributor docs describe the actual skeleton and preserve licence evidence."""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GPL3_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_readme_has_ten_line_description_and_runnable_quick_start() -> None:
    text = _text("README.md")
    description, quick_start = text.split("## Development quick start", maxsplit=1)
    prose = [line for line in description.splitlines() if line.strip() and not line.startswith("#")]
    assert len(prose) >= 10
    assert "dashboard" in description.lower() and "not yet" in description.lower()
    for command in (
        "uv sync --locked",
        "uv run ctstudio --version",
        "uv run ctstudio",
        "uv run python scripts/check.py",
    ):
        assert command in quick_start


@pytest.mark.parametrize("name", ["README.md", "CONTRIBUTING.md", "THIRD_PARTY_NOTICES.md"])
def test_contributor_document_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", _text(name)):
        if not target.startswith(("https://", "http://")):
            assert (path.parent / target.split("#", maxsplit=1)[0]).is_file(), target


def test_contributor_guide_points_to_rules_and_cross_platform_checks() -> None:
    text = _text("CONTRIBUTING.md")
    for item in ("AGENTS.md", "STATUS.md", "uv sync --locked", "scripts/check.py", "not network"):
        assert item in text
    assert "Nintendo" in text and "local_fixtures/" in text


def test_license_is_unmodified_official_gplv3_with_or_later_project_declaration() -> None:
    license_bytes = (ROOT / "LICENSE").read_bytes()
    # The canonical legal text is 674 lines: unlike source files it cannot be shortened.
    assert hashlib.sha256(license_bytes).hexdigest() == GPL3_SHA256
    assert "GPL-3.0-or-later" in _text("README.md")
    assert tomllib.loads(_text("pyproject.toml"))["project"]["license"] == "GPL-3.0-or-later"


def test_third_party_inventory_is_candid_and_covers_direct_dependencies() -> None:
    text = _text("THIRD_PARTY_NOTICES.md").lower()
    deps = tomllib.loads(_text("pyproject.toml"))["project"]["dependencies"]
    for dependency in deps:
        package = re.split(r"[<>=!~; ]", dependency, maxsplit=1)[0]
        assert package.lower() in text
    assert "blender-mkw-utilities" in text and "gpl-2.0-or-later" in text
    assert "not bundled" in text and "phase 12" in text
    assert (ROOT / "vendor" / "blender-mkw-utilities" / "NOTICE.md").is_file()


def test_benchmark_guidance_keeps_the_measured_baseline_without_inventing_linux_time() -> None:
    text = _text("docs/dev/BENCHMARKS.md")
    assert "0.394 s" in text and "200 MiB" in text
    assert "same machine" in text.lower() and "no performance threshold" in text.lower()
    assert "Linux" in text and "timing not recorded" in text
