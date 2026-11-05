"""Exercise the real detached process runner with a synthetic editor, not Blender."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from install import install_program
from pytestqt.qtbot import QtBot

from ctstudio.core.project import settings
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.gui.blender_launch import BlenderLaunchService


def test_service_reaches_real_process_runner(
    tmp_path: Path, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def undiscovered(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(editors, "discover", undiscovered)
    receipt = tmp_path / "launch-receipt.json"
    source = tmp_path / "source café 空.blend"
    source.write_bytes(b"synthetic argv fixture; not a Blender document")
    executable = install_program(
        tmp_path / "tools café 空" / "blender",
        "import json, os, sys\nfrom pathlib import Path\n"
        f"target = Path({str(receipt)!r})\n"
        "pending = target.with_suffix('.pending')\n"
        "pending.write_text(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}), "
        "encoding='utf-8')\npending.replace(target)\n",
    )
    path = tmp_path / "settings.json"
    settings.save(settings.UserSettings({"blender": str(executable)}), path)
    with Project.create(tmp_path / "project café 空", "Process proof", blend=source) as project:
        before = (project.manifest_path.read_bytes(), source.read_bytes(), path.read_bytes())
        result = BlenderLaunchService(settings_path=path).launch(project)
        qtbot.waitUntil(receipt.is_file, timeout=10000)
        assert json.loads(receipt.read_text(encoding="utf-8")) == {
            "argv": [str(source.resolve())],
            "cwd": str(source.parent.resolve()),
        }
        qtbot.waitUntil(
            lambda: all(t.name != f"reap-{result.pid}" for t in threading.enumerate()),
            timeout=10000,
        )
        assert result.pid > 0 and result.document == source.resolve()
        assert (
            project.manifest_path.read_bytes(),
            source.read_bytes(),
            path.read_bytes(),
        ) == before
