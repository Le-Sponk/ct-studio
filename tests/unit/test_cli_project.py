"""P3-T07: ``ctstudio new``, ``status`` and ``open`` as real processes against fake tools.

Each run gets its own user folders (settings, logs, caches) and puts the fake Wiimm, rszst,
ABMatt and Blender programs first on PATH, exactly as installed tools would be. ``open``
launches a fake editor that writes down the arguments it was given; no real editor runs.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fakes import install as fake_install

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
        f"with open({str(record.with_suffix('.tmp'))!r}, 'w', encoding='utf-8') as receipt:\n"
        "    receipt.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))\n"
        f"os.replace({str(record.with_suffix('.tmp'))!r}, {str(record)!r})\n",
    )
    env = _environment(tmp_path, str(editors) + os.pathsep + os.environ.get("PATH", ""))
    document = tmp_path / "files é" / "track.blend"
    document.parent.mkdir()
    document.write_bytes(b"BLENDER-v300REND")

    opened = _ctstudio(env, "open", str(document))
    assert opened.returncode == 0, opened.stderr
    assert opened.stdout.startswith("Started Blender for track.blend (process ")

    # The editor is detached and gives no signal but the file it writes, so poll for it.
    deadline = time.monotonic() + 30
    while not record.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    launched = json.loads(record.read_text(encoding="utf-8"))
    assert launched == {"argv": [str(document.resolve())], "cwd": str(document.parent.resolve())}


def _gated_editor_code(code: str, address: tuple[str, int]) -> str:
    """Pause the actual detached writer after open, before its first write."""
    return (
        "import builtins, socket\n"
        "real_open = builtins.open\n"
        f"gate = socket.create_connection({address!r}, timeout=30)\n"
        "writer = None\n"
        "def gated_open(*args, **kwargs):\n"
        "    global writer\n"
        "    writer = real_open(*args, **kwargs)\n"
        "    gate.sendall(b'O')\n"
        "    assert gate.recv(1) == b'G'\n"
        "    return writer\n"
        "builtins.open = gated_open\n" + code + "gate.sendall(b'C' if writer.closed else b'U')\n"
        "gate.close()\n"
    )


def test_open_receipt_is_not_published_until_the_writer_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "editor argv.json"
    install_program, ctstudio, exists = fake_install.install_program, _ctstudio, Path.exists
    connection: socket.socket | None = None
    released = False
    completion = b""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(30)
        address = ("127.0.0.1", int(server.getsockname()[1]))

        def install_gated(path: Path, code: str) -> Path:
            return install_program(path, _gated_editor_code(code, address))

        def launch_gated(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
            nonlocal connection
            opened = ctstudio(env, *args)
            connection, _ = server.accept()
            connection.settimeout(30)
            assert connection.recv(1) == b"O", "child reached open before write"
            return opened

        def exists_while_gated(path: Path) -> bool:
            nonlocal released
            visible = exists(path)
            if path == record and not visible and connection is not None and not released:
                connection.sendall(b"G")
                released = True
            return visible

        monkeypatch.setattr(fake_install, "install_program", install_gated)
        monkeypatch.setattr(sys.modules[__name__], "_ctstudio", launch_gated)
        monkeypatch.setattr(Path, "exists", exists_while_gated)
        try:
            test_open_launches_the_editor_on_the_document(tmp_path)
        except json.JSONDecodeError as exc:
            raise AssertionError("detached writer exposed unfinished JSON") from exc
        finally:
            if connection is not None:
                if not released:
                    connection.sendall(b"G")
                completion = connection.recv(1)
                connection.close()
        assert completion == b"C", "the detached receipt writer explicitly closed its file"


@pytest.mark.parametrize("json_output", [True, False])
def test_redirected_output_survives_a_non_ascii_project(tmp_path: Path, json_output: bool) -> None:
    """Windows writes redirected output in the ANSI code page unless told otherwise."""
    env = _environment(tmp_path, os.environ.get("PATH", ""))
    for name in ("PYTHONIOENCODING", "PYTHONUTF8"):
        env.pop(name, None)
    root = tmp_path / "Pistë 日本"
    assert _ctstudio(env, "new", str(root)).returncode == 0
    args = [
        sys.executable,
        "-m",
        "ctstudio",
        "status",
        str(root),
        *(["--json"] if json_output else []),
    ]
    result = subprocess.run(args, capture_output=True, env=env, timeout=100, check=False)  # noqa: S603
    assert result.returncode == 1, result.stderr.decode("utf-8", "replace")
    assert b"Traceback" not in result.stderr
    if json_output:
        assert json.loads(result.stdout.decode("utf-8"))["project"]["name"] == "Pistë 日本"
    else:
        assert result.stdout.decode("utf-8").startswith("Pistë 日本, replacing Luigi Circuit")


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
