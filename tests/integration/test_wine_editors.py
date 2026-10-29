"""Linux + Wine editor launches through ``open_in`` (P2-T05g2), run on a real desktop.

Reuses what ``spikes/p2t05g2_wine_probe.py`` left in ``~/ct-studio-wine-probe`` (or
``$CTSTUDIO_WINE_PROBE``): the three pinned editors, ``prefix64`` (win64) and ``prefix32``
(win32 + dotnet48 + win10). Documents are copies of self-made recording inputs in a
``dossier é 日本`` folder. Windows are read with ``wmctrl``; every prefix used is stopped
with ``wineserver -k`` afterwards. Skips unless all of that is present.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from ctstudio.core.tools.editors import Launched, open_in
from ctstudio.core.tools.wine import WineError

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "tests" / "fakes" / "recordings"
WORK = Path(os.environ.get("CTSTUDIO_WINE_PROBE", Path.home() / "ct-studio-wine-probe"))
EDITORS = {
    "riistudio": WORK / "editors" / "riistudio" / "RiiStudio.exe",
    "brawlcrate": WORK / "editors" / "brawlcrate" / "BrawlCrate.exe",
    "kmp_editor_lorenzi": WORK / "editors" / "lorenzi" / "Lorenzi's KMP Editor.exe",
}
PREFIX64, PREFIX32 = WORK / "prefix64", WORK / "prefix32"
WINE, WINESERVER, WMCTRL = (shutil.which(n) for n in ("wine", "wineserver", "wmctrl"))
READY = (
    os.name == "posix"
    and bool(os.environ.get("DISPLAY"))
    and None not in (WINE, WINESERVER, WMCTRL)
    and all(p.is_file() for p in EDITORS.values())
    and (PREFIX64 / "system.reg").is_file()
    and (PREFIX32 / "drive_c" / "windows" / "dotnet48.installed.workaround").exists()
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(240),
    pytest.mark.skipif(
        not READY, reason="needs Linux desktop, Wine, wmctrl and the P2-T05g2 probe"
    ),
]


def _windows() -> dict[str, str]:
    out = subprocess.run(  # noqa: S603 - fixed argv
        [str(WMCTRL), "-l"], capture_output=True, text=True, timeout=10, check=True
    ).stdout
    return {
        parts[0]: parts[3] if len(parts) > 3 else ""
        for parts in (line.split(None, 3) for line in out.splitlines())
        if parts
    }


def _stop(prefix: Path) -> None:
    env = {**os.environ, "WINEPREFIX": str(prefix)}
    subprocess.run([str(WINESERVER), "-k"], env=env, timeout=30, check=False)  # noqa: S603
    subprocess.run([str(WINESERVER), "-w"], env=env, timeout=60, check=False)  # noqa: S603


@pytest.fixture
def docs(tmp_path: Path) -> dict[str, Path]:
    folder = tmp_path / "dossier é 日本"
    folder.mkdir()
    out = {}
    for key, source in {
        "brres": REC / "wszst/2.42a/inputs/map_model.brres",
        "kmp": REC / "wkmpt/2.42a/inputs/course.kmp",
    }.items():
        out[key] = folder / f"pièce {source.name}"
        shutil.copyfile(source, out[key])
    return out


@pytest.fixture
def stopped() -> Iterator[list[Path]]:
    prefixes: list[Path] = []
    yield prefixes
    for prefix in prefixes:
        _stop(prefix)


def _new_windows(before: dict[str, str], seconds: float = 45.0) -> dict[str, str]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        new = {k: v for k, v in _windows().items() if k not in before and v}
        if new:
            time.sleep(2.0)  # let the title settle on the document
            return {k: v for k, v in _windows().items() if k not in before and v}
        time.sleep(0.5)
    return {}


@pytest.mark.parametrize(
    ("tool", "doc", "prefix", "named"),
    [
        ("riistudio", "brres", PREFIX64, False),
        ("kmp_editor_lorenzi", "kmp", PREFIX64, True),
        ("brawlcrate", "brres", PREFIX32, True),
    ],
)
def test_editor_starts_in_its_prefix_on_a_unicode_path(
    tool: str,
    doc: str,
    prefix: Path,
    named: bool,
    docs: dict[str, Path],
    stopped: list[Path],
) -> None:
    stopped.append(prefix)
    before = _windows()
    result = open_in(tool, docs[doc], executable=EDITORS[tool], wine_prefix=prefix)
    assert result == Launched(tool, result.pid, docs[doc], ())
    titles = list(_new_windows(before).values())
    assert titles, f"{tool}: no window appeared"
    if named:
        assert any(docs[doc].name in t.replace("\\", "/") for t in titles), titles


def test_a_64_bit_editor_in_a_32_bit_prefix_is_refused_before_starting(
    docs: dict[str, Path], stopped: list[Path]
) -> None:
    stopped.append(PREFIX32)
    before = _windows()
    with pytest.raises(WineError, match="64-bit"):
        open_in("riistudio", docs["brres"], executable=EDITORS["riistudio"], wine_prefix=PREFIX32)
    time.sleep(3)
    assert {k for k in _windows() if k not in before} == set()


def test_brawlcrate_without_dotnet_is_reported_with_the_fix(
    docs: dict[str, Path], stopped: list[Path], tmp_path: Path
) -> None:
    prefix = tmp_path / "préfixe sans .NET"
    stopped.append(prefix)
    env = {
        **os.environ,
        "WINEPREFIX": str(prefix),
        "WINEARCH": "win32",
        "WINEDLLOVERRIDES": "mscoree,mshtml=",  # as the probe: no Wine Mono prompt
        "WINEDEBUG": "-all",
    }
    subprocess.run([str(WINE), "wineboot", "-u"], env=env, timeout=600, check=True)  # noqa: S603
    _stop(prefix)
    started = time.monotonic()
    with pytest.raises(WineError, match=r"\.NET") as caught:
        open_in("brawlcrate", docs["brres"], executable=EDITORS["brawlcrate"], wine_prefix=prefix)
    assert time.monotonic() - started < 30
    assert caught.value.hint is not None and "dotnet48" in caught.value.hint
