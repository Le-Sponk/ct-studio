"""P3-T07: ``ctstudio new``, ``status`` and ``open`` as real processes against fake tools.

Each run gets its own user folders (settings, logs, caches) and puts the fake Wiimm, rszst,
ABMatt and Blender programs first on PATH, exactly as installed tools would be. ``open``
launches a fake editor that writes down the arguments it was given; no real editor runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import install as fake_install  # tests/fakes is put on sys.path by tests/conftest.py
import pytest

pytestmark = pytest.mark.timeout(120)


def _environment(tmp_path: Path, path: str) -> dict[str, str]:
    users = tmp_path / "user folders é"
    env = dict(os.environ)
    env.update(
        PATH=path,
        PYTHONIOENCODING="utf-8",
        WIN_PD_OVERRIDE_LOCAL_APPDATA=str(users / "local"),
        WIN_PD_OVERRIDE_APPDATA=str(users / "roaming"),
        XDG_CONFIG_HOME=str(users / "config"),
        XDG_DATA_HOME=str(users / "data"),
        XDG_CACHE_HOME=str(users / "cache"),
        XDG_STATE_HOME=str(users / "state"),
    )
    return env


def _ctstudio(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - our own interpreter
        [sys.executable, "-m", "ctstudio", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=100,
        check=False,
    )


def test_new_then_status_with_the_fake_tools(tmp_path: Path, fake_tools_path: Any) -> None:
    env = _environment(tmp_path, os.environ["PATH"])
    root = tmp_path / "Sponk Raceway é"
    blend = tmp_path / "track.blend"
    blend.write_bytes(b"BLENDER-v300REND")

    made = _ctstudio(env, "new", str(root), "--slot", "GCN Mario Circuit", "--blend", str(blend))
    assert made.returncode == 0, made.stderr
    assert "replacing GCN Mario Circuit (Leaf Cup, track 4)" in made.stdout

    status = _ctstudio(env, "status", str(root), "--json")
    assert status.returncode == 0, status.stderr
    data = json.loads(status.stdout)
    assert data["project"]["slot"] == "old_mario_gc"
    states = {part["id"]: part["state"] for part in data["parts"]}
    assert states == {
        "course_model": "missing",
        "kcl": "missing",
        "minimap": "missing",
        "skybox": "missing",
        "kmp": "missing",
        "posteffect": "missing",
        "objects": "ready",
        "track_info": "warning",
    }, "every tool a part needs was found, so nothing is a problem"
    assert fake_tools_path.calls() == [], "a status check starts no tool"

    table = _ctstudio(env, "status", str(root))
    assert table.returncode == 0, table.stderr
    assert table.stdout.startswith("Sponk Raceway é, replacing GCN Mario Circuit")
    assert table.stdout.endswith("Nothing listed here stops a build.\n")


def test_command_line_mistakes_exit_2_and_project_problems_exit_1(tmp_path: Path) -> None:
    env = _environment(tmp_path, os.environ.get("PATH", ""))
    bad_slot = _ctstudio(env, "new", str(tmp_path / "p"), "--slot", "begginer_course")
    assert bad_slot.returncode == 2
    assert "Did you mean beginner_course (Luigi Circuit)?" in bad_slot.stderr

    no_project = _ctstudio(env, "status", str(tmp_path))
    assert no_project.returncode == 1
    assert "There is no ctstudio.toml in" in no_project.stderr
    assert no_project.stdout == ""


def test_open_launches_the_editor_on_the_document(tmp_path: Path) -> None:
    record = tmp_path / "editor argv.json"
    editors = tmp_path / "editors é"
    fake_install.install_program(
        editors / "blender",
        "import json, os, sys\n"
        f"open({str(record)!r}, 'w', encoding='utf-8').write("
        "json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))\n",
    )
    env = _environment(tmp_path, str(editors) + os.pathsep + os.environ.get("PATH", ""))
    document = tmp_path / "files é" / "track.blend"
    document.parent.mkdir()
    document.write_bytes(b"BLENDER-v300REND")

    opened = _ctstudio(env, "open", str(document))
    assert opened.returncode == 0, opened.stderr
    assert opened.stdout.startswith("Started Blender for track.blend (process ")

    deadline = time.monotonic() + 30
    while not record.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    launched = json.loads(record.read_text(encoding="utf-8"))
    assert launched == {"argv": [str(document.resolve())], "cwd": str(document.parent.resolve())}


def test_the_new_commands_never_import_qt(tmp_path: Path) -> None:
    root = tmp_path / "p"
    code = (
        "import sys\n"
        "from ctstudio.cli import status\n"
        "status.available_tools = lambda **k: frozenset()\n"
        "from ctstudio.__main__ import main\n"
        f"assert main(['new', {str(root)!r}]) == 0\n"
        f"assert main(['status', {str(root)!r}, '--json']) == 1\n"
        f"assert main(['open', {str(root / 'missing.blend')!r}]) == 1\n"
        "assert not any(m.startswith('PySide6') for m in sys.modules), 'Qt imported'\n"
        "assert 'ctstudio.gui' not in sys.modules\n"
    )
    result = subprocess.run(  # noqa: S603 - our own interpreter
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=_environment(tmp_path, os.environ.get("PATH", "")),
        timeout=100,
        check=False,
    )
    assert result.returncode == 0, result.stderr
