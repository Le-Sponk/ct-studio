"""P3 exit check: ``ctstudio new`` + ``ctstudio status --json`` on a fixture project, real tools.

The project uses the generated fixture ``.blend`` and the ``wkmpt``-built ``course.kmp``, and
CT Studio finds the real tools in ``.tools/`` the way it does in a checkout. Settings, logs and
caches live in throwaway user folders, so the developer's own settings are never read.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.project import manifest_io
from ctstudio.core.tools.availability import available_tools

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "generated"
sys.path.insert(0, str(ROOT / "scripts"))
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        not (tp.WSZST.is_file() and tp.WKCLT.is_file() and (FIXTURES / "course.kmp").is_file()),
        reason="Requires Wiimm 2.42a and the generated fixtures (make_fixtures.py)",
    ),
]


def _environment(tmp_path: Path) -> dict[str, str]:
    users = tmp_path / "user folders é"
    env = dict(os.environ)
    env.update(
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
        timeout=200,
        check=False,
    )


def _parts(env: dict[str, str], root: Path) -> dict[str, dict[str, object]]:
    status = _ctstudio(env, "status", str(root), "--json")
    assert status.stdout, status.stderr
    return {part["id"]: part for part in json.loads(status.stdout)["parts"]}


def test_status_of_a_fixture_project_with_the_real_tools(tmp_path: Path) -> None:
    env = _environment(tmp_path)
    root = tmp_path / "Fixture Raceway é"
    files = root / "files"
    files.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "fixture_track_good.blend", files / "track.blend")
    shutil.copyfile(FIXTURES / "course.kmp", files / "course.kmp")

    blend = str(files / "track.blend")
    made = _ctstudio(env, "new", str(root), "--slot", "LC", "--blend", blend, "--force")
    assert made.returncode == 0, made.stderr
    toml = root / manifest_io.FILE_NAME
    manifest = manifest_io.load(toml)
    kmp = dataclasses.replace(manifest.components.kmp, file="files/course.kmp")
    components = dataclasses.replace(manifest.components, kmp=kmp)
    manifest_io.save(dataclasses.replace(manifest, components=components), toml)

    parts = _parts(env, root)
    assert list(parts) == [spec.id for spec in COMPONENTS]
    assert parts["kmp"]["state"] == "manual", parts["kmp"]
    assert parts["objects"]["state"] == "ready"
    assert parts["track_info"]["state"] == "warning"  # no author set
    found = available_tools()
    for spec in COMPONENTS:
        needed = spec.tools_for(spec.default_mode)
        if not needed or spec.id in ("kmp", "objects", "track_info"):
            continue
        part = parts[spec.id]
        lacking = [tool for tool in needed if tool not in found]
        if lacking:
            assert part["state"] == "error", part
        else:
            assert part["state"] == "missing", part  # nothing built yet, every tool there

    shutil.copyfile(FIXTURES / "course.kcl", files / "course.kmp")  # the wrong file type
    parts = _parts(env, root)
    assert parts["kmp"]["state"] == "error"
    assert parts["kmp"]["reasons"] == [
        "files/course.kmp is the wrong type: expected course data file (KMP),"
        " found collision file (KCL)"
    ]
    assert _ctstudio(env, "status", str(root)).returncode == 1
