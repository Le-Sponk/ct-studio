"""P2-T06b: the real rszst setup routes, end to end.

* Windows: download the pinned official release (44 MB) into a temporary data folder, verify
  the checksum and the banner, then discovery and doctor see it as "downloaded". Needs the
  network, so it is ``network``-marked (nightly / on demand, not ``check.py``).
* Linux: build the pinned source (about 1 hour, ~4 GB). Opt-in only:
  ``CTSTUDIO_RSZST_BUILD=1 uv run pytest -m slow tests/integration/test_rszst_setup_real.py``.
Neither copies anything into the repository.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ctstudio.core.tools.discovery import DiscoveryEnvironment, discover
from ctstudio.core.tools.doctor import diagnose
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.rszst_install import build_linux, download_windows, read_banner
from ctstudio.core.tools.rszst_setup import PIN, managed_root, preflight, read_record
from ctstudio.core.tools.versions import VersionCache

pytestmark = pytest.mark.integration


def _env(data: Path) -> DiscoveryEnvironment:
    system = DiscoveryEnvironment.from_system()
    return DiscoveryEnvironment(
        system.platform, system.root, system.home, {"PATH": ""}, None, data_dir=data
    )


def _seen_by_doctor(data: Path, tmp_path: Path, route: str) -> None:
    env = _env(data)
    found = discover(TOOL_BY_ID["rszst"], environment=env)
    assert found is not None and found.source == "managed"
    report = diagnose(
        environment=env, dev_root=tmp_path / "none", cache=VersionCache(tmp_path / "v")
    )
    [check] = [c for c in report.tools if c.tool_id == "rszst"]
    assert (check.status, check.version, check.route) == ("found", PIN.version, route)


@pytest.mark.network
@pytest.mark.timeout(600)
@pytest.mark.skipif(sys.platform != "win32", reason="the official release is Windows-only")
def test_windows_download_route(tmp_path: Path) -> None:
    data = tmp_path / "données é"
    root = managed_root(data)
    exe = download_windows(root)
    assert read_record(root) is not None
    assert PIN.banner in read_banner(exe)
    _seen_by_doctor(data, tmp_path, "download")


@pytest.mark.slow
@pytest.mark.timeout(5 * 3600)
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the source build is for Linux")
@pytest.mark.skipif(
    os.environ.get("CTSTUDIO_RSZST_BUILD") != "1",
    reason="takes about an hour; set CTSTUDIO_RSZST_BUILD=1 to run it",
)
def test_linux_source_build_route(tmp_path: Path) -> None:
    keep = os.environ.get("CTSTUDIO_RSZST_BUILD_DIR")  # reuse a build between attempts
    data = Path(keep) if keep else tmp_path / "data"
    root = managed_root(data)
    checked = preflight(root)
    assert checked.ok, "\n".join(checked.lines())
    exe = build_linux(
        root,
        jobs=max(1, (os.cpu_count() or 2) // 2),
        preflight_result=checked,
        on_step=lambda n, total, step: print(f"step {n}/{total}: {step.name}", flush=True),
    )
    assert PIN.banner in read_banner(exe)
    _seen_by_doctor(data, tmp_path, "build")
