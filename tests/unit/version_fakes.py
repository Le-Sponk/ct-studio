"""Version-probe fakes: standalone executables with their own path, size and mtime.

Windows: a copy of the venv's launcher plus `pyvenv.cfg` (the launcher finds the base
interpreter through it). Linux: a shebang script. Each fake runs ``code`` via ``-c`` passed
as the spec's version arguments, so probes exercise real process spawning.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.spec import ToolSpec


def fake_executable(folder: Path, name: str = "fake tool") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        launcher = Path(sys.executable)
        config = launcher.parent.parent / "pyvenv.cfg"
        if not config.is_file():
            pytest.skip("Windows fake executables need the tests to run inside a venv")
        bin_dir = folder / "Scripts"
        bin_dir.mkdir(exist_ok=True)
        shutil.copy2(config, folder / "pyvenv.cfg")
        target = bin_dir / f"{name}.exe"
        shutil.copy2(launcher, target)
        return target
    target = folder / name
    # A shebang passes `-c <code>` to the script, not the interpreter: run it explicitly.
    body = (
        "import sys\n"
        "if sys.argv[1:2] == ['-c']:\n"
        "    sys.argv = sys.argv[2:]\n"
        "    exec(sys.argv[0])\n"
    )
    target.write_text(f"#!{Path(sys.executable).resolve()}\n{body}", encoding="utf-8")
    target.chmod(0o755)
    return target


def spec_running(code: str, *, tool_id: str = "fake", regex: str | None = None) -> ToolSpec:
    return ToolSpec(
        id=tool_id,
        name=f"Fake {tool_id}",
        kind="cli",
        exe_names={"windows": ("fake.exe",), "linux": ("fake",)},
        version_args=("-c", code),
        version_regex=regex if regex is not None else r"(?m)^fake v(\d+\.\d+)\b",
        min_version=None,
        homepage="https://example.invalid/",
        download_page="https://example.invalid/download",
        licence="test",
        used_for="tests",
    )


# Appends one "x" to argv[1] per run, so tests can count real spawns.
_COUNT = (
    "import pathlib, sys\n"
    "counter = pathlib.Path(sys.argv[1])\n"
    "counter.write_text((counter.read_text() if counter.exists() else '') + 'x')\n"
)


def counting_spec(counter: Path, body: str = "print('fake v1.2')") -> ToolSpec:
    spec = spec_running(_COUNT + body)
    return replace(spec, version_args=(*spec.version_args, str(counter)))


def runs(counter: Path) -> int:
    return len(counter.read_text(encoding="utf-8")) if counter.exists() else 0


def direct(path: Path) -> ToolLocation:
    return ToolLocation(path, None, "path", "direct")
