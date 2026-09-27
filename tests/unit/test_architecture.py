"""P1-T03: prove the architecture gate rejects forbidden imports, not just config syntax."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.timeout(90)
ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "ctstudio"


def _sandbox(tmp_path: Path) -> Path:
    """Copy only the package, config and gate into a path with spaces and Unicode."""
    root = tmp_path / "contracts é with spaces"
    root.mkdir()
    shutil.copytree(
        PACKAGE, root / "src" / "ctstudio", ignore=shutil.ignore_patterns("__pycache__")
    )
    (root / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / "check.py", root / "scripts" / "check.py")
    for name in (".importlinter", "pyproject.toml", "vulture_whitelist.py"):
        shutil.copy2(ROOT / name, root / name)
    (root / "tests").mkdir()
    (root / "tests" / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n", encoding="utf-8"
    )
    return root


def _run(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(root / "src"), env.get("PYTHONPATH")) if p)
    return subprocess.run(  # noqa: S603 - own interpreter/installed tool, argv list
        [*argv],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _write_module(root: Path, relative: str, content: str) -> None:
    path = root / "src" / "ctstudio" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent != root / "src" / "ctstudio":
        (path.parent / "__init__.py").touch()
    path.write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    ("source", "import_line", "forbidden"),
    [
        ("core/work.py", "from ctstudio.gui import view\n", "ctstudio.gui"),
        ("core/work.py", "from ..gui import view\n", "ctstudio.gui"),
        ("core/work.py", "from ctstudio.cli import command\n", "ctstudio.cli"),
        ("cli/work.py", "from ctstudio.gui import view\n", "ctstudio.gui"),
        ("core/work.py", "from PySide6 import QtCore\n", "PySide6"),
        ("core/work.py", "from PySide6.QtCore import QObject\n", "PySide6"),
        ("__main__.py", "import spikes.probe\n", "spikes"),
    ],
)
def test_import_linter_rejects_each_boundary(
    tmp_path: Path, source: str, import_line: str, forbidden: str
) -> None:
    root = _sandbox(tmp_path)
    _write_module(root, "gui/view.py", "VALUE = 1\n")
    _write_module(root, "cli/command.py", "VALUE = 1\n")
    _write_module(root, source, import_line)
    script = Path(sys.executable).parent / (
        "lint-imports.exe" if sys.platform == "win32" else "lint-imports"
    )
    result = _run(root, str(script), "--no-logo", "--no-cache")
    assert result.returncode != 0, result.stdout + result.stderr
    assert forbidden in result.stdout + result.stderr
    assert "1 broken." in result.stdout


def test_gate_rejects_qt_import_in_core(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _write_module(
        root,
        "core/deep/work.py",
        "import PySide6\n\nNAME = PySide6.__name__\n",
    )
    result = _run(root, sys.executable, str(root / "scripts" / "check.py"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL  lint-imports" in result.stdout
    assert "PySide6" in result.stdout
    assert "PASS  ruff format" in result.stdout
    assert "PASS  ruff check" in result.stdout


def import_names(tree: ast.AST) -> list[str]:
    """Return import targets (including nested and relative imports) from a Python AST."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return names


def bad_blender_imports(tree: ast.AST) -> list[str]:
    return [
        name
        for name in import_names(tree)
        if name.startswith(".")
        or name.split(".", maxsplit=1)[0] not in {*sys.stdlib_module_names, "bpy"}
    ]


def bad_spike_imports(tree: ast.AST) -> list[str]:
    return [name for name in import_names(tree) if name.split(".", maxsplit=1)[0] == "spikes"]


def test_blender_bridge_import_scan_covers_nested_and_relative_imports() -> None:
    allowed = ast.parse(
        "from __future__ import annotations\nimport json, bpy\n"
        "from os import path\nfrom bpy import types\n"
    )
    assert bad_blender_imports(allowed) == []
    for code, expected in (
        ("import bpy, numpy", "numpy"),
        ("if True:\n    from PySide6 import QtCore", "PySide6"),
        ("from ctstudio.core import errors", "ctstudio.core"),
        ("from . import exporters", "."),
        ("import bpy_extras", "bpy_extras"),
    ):
        assert expected in bad_blender_imports(ast.parse(code))


def test_project_import_scan_rejects_spikes_in_scripts_and_tests() -> None:
    assert bad_spike_imports(ast.parse("import json\n")) == []
    assert "spikes.s7" in bad_spike_imports(ast.parse("import os, spikes.s7\n"))
    assert "spikes" in bad_spike_imports(ast.parse("from spikes import s7\n"))


def repository_import_violations(root: Path) -> list[str]:
    bridge = root / "src" / "ctstudio" / "blender_bridge"
    violations: list[str] = []
    for directory in (root / "src", root / "scripts", root / "tests"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if path.is_relative_to(bridge):
                violations.extend(
                    f"{path.relative_to(root)}: {name}" for name in bad_blender_imports(tree)
                )
            violations.extend(
                f"{path.relative_to(root)}: {name}" for name in bad_spike_imports(tree)
            )
    return violations


def test_filesystem_scan_rejects_forbidden_bridge_and_spike_imports(tmp_path: Path) -> None:
    bridge = tmp_path / "src" / "ctstudio" / "blender_bridge"
    bridge.mkdir(parents=True)
    (bridge / "run_job.py").write_text("import bpy, numpy\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("from spikes import s1\n", encoding="utf-8")
    violations = repository_import_violations(tmp_path)
    assert any("blender_bridge" in line and "numpy" in line for line in violations)
    assert any("scripts" in line and "spikes" in line for line in violations)


def test_repository_imports_obey_the_bridge_and_spike_boundaries() -> None:
    violations = repository_import_violations(ROOT)
    assert not violations, "Forbidden imports:\n" + "\n".join(violations)
