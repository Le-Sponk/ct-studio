"""Tests for the `ctstudio` entry point (P1-T01).

P1-T01's acceptance is "`uv sync` then `uv run ctstudio --version` works". These tests pin the
parts of that which could silently drift: the installed console script, the version string's
single source (pyproject.toml), and that `--version` does not pay for a Qt import.
"""

from __future__ import annotations

import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path

import pytest

from ctstudio import __version__
from ctstudio.__main__ import main

pytestmark = pytest.mark.timeout(30)

REPO_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_S = 25


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv list built from our own interpreter/launcher
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT_S,
        check=False,
    )


def test_version_comes_from_pyproject() -> None:
    assert __version__ == _pyproject_version()


def test_main_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"ctstudio {__version__}"


def test_main_rejects_unknown_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--no-such-option"])
    assert exc.value.code == 2
    assert "--no-such-option" in capsys.readouterr().err


def test_installed_console_script_reports_version() -> None:
    # The `ctstudio` launcher uv sync installs next to the interpreter: this is the
    # command users type, so exercise it rather than only `python -m`.
    suffix = ".exe" if sys.platform == "win32" else ""
    script = Path(sysconfig.get_path("scripts")) / f"ctstudio{suffix}"
    assert script.is_file(), f"console script missing: {script} (run `uv sync`)"
    result = _run([str(script), "--version"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"ctstudio {__version__}"


def test_version_does_not_import_qt() -> None:
    # `--version` must stay cheap; P1-T06 lazy-imports PySide6 only on GUI paths.
    probe = (
        "import sys\n"
        "from ctstudio.__main__ import main\n"
        "try:\n"
        "    main(['--version'])\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in {'PySide6', 'shiboken6'}))\n"
    )
    result = _run([sys.executable, "-c", probe])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "[]"
