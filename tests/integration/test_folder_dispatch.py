"""Real Linux xdg-open dispatch with an isolated synthetic XFCE handler, not pixels."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import install
import pytest

from ctstudio.core.errors import ToolFailed
from ctstudio.core.tools import folders, process

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(40),
    pytest.mark.skipif(os.name == "nt", reason="Linux xdg-open contract"),
]


def test_real_xdg_open_preserves_folder_and_reports_handler_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_testsuite_property: Callable[[str, object], None],
) -> None:
    """Native dispatcher, synthetic desktop handler; no real file manager is launched."""
    located = shutil.which("xdg-open")
    assert located is not None, "Install xdg-utils to measure the native Linux dispatcher."
    executable = Path(located).resolve()
    folder = tmp_path / "folder café 日本"
    folder.mkdir()
    marker = folder / "unchanged.txt"
    marker.write_bytes(b"synthetic folder marker\n")
    receipt = tmp_path / "handler.json"
    helper = install.install_program(
        tmp_path / "bin" / "exo-open",
        "import json, os, sys\nfrom pathlib import Path\n"
        "if sys.argv[1:] == ['--help']: raise SystemExit(0)\n"
        f"Path({str(receipt)!r}).write_text(json.dumps("
        "{'argv': sys.argv[1:], 'cwd': os.getcwd()}, ensure_ascii=False), encoding='utf8')\n"
        "raise SystemExit(int(os.environ.get('CTSTUDIO_HANDLER_EXIT', '0')))\n",
    )
    monkeypatch.setenv("PATH", str(helper.parent) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "XFCE")
    monkeypatch.setenv("DESKTOP_SESSION", "xfce")
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.delenv("CTSTUDIO_HANDLER_EXIT", raising=False)
    version = process.run([executable, "--version"], cwd=folder, timeout=10).stdout_tail
    assert "xdg-open" in version
    result = process.run([executable, folder], cwd=folder, timeout=10)
    assert result.exit_code == 0
    expected = {"argv": [str(folder.resolve())], "cwd": str(folder.resolve())}
    assert json.loads(receipt.read_text(encoding="utf8")) == expected
    monkeypatch.setenv("CTSTUDIO_HANDLER_EXIT", "4")
    failed = process.run([executable, folder], cwd=folder, timeout=10, check=False)
    assert failed.exit_code == 4
    # Check the requested production watch, but allow slow CI startup in this native probe.
    # The unit contracts independently pin 0.4 s; this probe measures native argv/error mapping.
    detached = process.launch_detached

    def observed_dispatch(cmd: list[str | Path], *, cwd: Path, watch: float) -> int:
        assert watch == 0.4
        return detached(cmd, cwd=cwd, watch=5.0)

    monkeypatch.setattr(process, "launch_detached", observed_dispatch)
    with pytest.raises(ToolFailed) as error:
        folders.open_folder(folder)
    assert error.value.exit_code == 4
    assert marker.read_bytes() == b"synthetic folder marker\n"
    assert sorted(p.name for p in folder.iterdir()) == ["unchanged.txt"]
    record_testsuite_property("folder_dispatcher_version", version)
    record_testsuite_property("folder_dispatcher_contract", "Unicode argv/cwd; exit 0 and 4")
