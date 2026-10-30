"""P2-T06b: ``ctstudio.core.tools.rszst_install`` — carry out a setup route.

The network is a fake opener returning bytes; ``rszst --version`` and the build commands are
replaced by recording stubs, except one test that runs a real process for the banner check.
A setup only counts once ``setup.json`` is written, so every failure must leave none.
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from version_fakes import fake_executable

from ctstudio.core.errors import Cancelled, CTStudioError
from ctstudio.core.tools import rszst_install as install
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.rszst_install import SetupFailed, download_windows
from ctstudio.core.tools.rszst_setup import PIN, SetupRecord, read_record

pytestmark = pytest.mark.timeout(60)
BANNER = "RiiStudio Parser 1.0\nRiiStudio CLI Alpha 5.11.5 (Built May 22 2025, Clang 19.1.5)"


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


GOOD = _zip({"rszst.exe": b"MZ cli", "RiiStudio.exe": b"MZ gui", "fonts/a.ttf": b"font"})


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> Callable[[bytes], None]:
    """Pin the checksum and size to whatever archive a test serves."""

    def use(data: bytes) -> None:
        fake = replace(
            PIN,
            windows_zip_sha256=hashlib.sha256(data).hexdigest(),
            windows_zip_bytes=len(data),
        )
        monkeypatch.setattr(install, "PIN", fake)

    return use


class Trickle(io.BytesIO):
    """A response that hands out at most ``chunk`` bytes per read, like a slow socket."""

    def __init__(self, data: bytes, chunk: int) -> None:
        super().__init__(data)
        self.chunk = chunk

    def read(self, size: int | None = -1, /) -> bytes:
        limit = self.chunk if size is None or size < 0 else min(size, self.chunk)
        return super().read(limit)


class Opener:
    def __init__(self, data: bytes, chunk: int = 7) -> None:
        self.data, self.chunk, self.urls = data, chunk, list[str]()

    def __call__(self, url: str) -> Trickle:
        self.urls.append(url)
        return Trickle(self.data, self.chunk)


def _banner(text: str = BANNER) -> Callable[[Path], str]:
    return lambda _exe: text


# --- Windows download ----------------------------------------------------------------------------


def test_download_fetches_checks_unpacks_verifies_and_records(
    pinned: Callable[[bytes], None], tmp_path: Path
) -> None:
    pinned(GOOD)
    root = tmp_path / "données" / "riistudio-5.11.5"
    opener, progress = Opener(GOOD), list[tuple[int, int]]()
    exe = download_windows(
        root, opener=opener, banner=_banner(), on_progress=lambda a, b: progress.append((a, b))
    )
    assert exe == root / "rszst.exe" and exe.read_bytes() == b"MZ cli"
    assert (root / "fonts" / "a.ttf").read_bytes() == b"font"
    assert opener.urls == [PIN.windows_zip_url]
    assert read_record(root) == SetupRecord("download", "5.11.5", "rszst.exe")
    assert progress[-1] == (len(GOOD), len(GOOD))
    assert [done for done, _ in progress] == sorted(done for done, _ in progress)
    assert sorted(p.name for p in root.parent.iterdir()) == ["riistudio-5.11.5"]


def test_a_finished_setup_is_not_downloaded_again(
    pinned: Callable[[bytes], None], tmp_path: Path
) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"
    download_windows(root, opener=Opener(GOOD), banner=_banner())
    again = Opener(GOOD)
    assert download_windows(root, opener=again, banner=_banner()) == root / "rszst.exe"
    assert again.urls == []


def test_an_unfinished_folder_is_replaced(pinned: Callable[[bytes], None], tmp_path: Path) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"
    (root / "junk").mkdir(parents=True)
    (root / "rszst.exe").write_bytes(b"half")
    download_windows(root, opener=Opener(GOOD), banner=_banner())
    assert not (root / "junk").exists()
    assert (root / "rszst.exe").read_bytes() == b"MZ cli"


def _fails(root: Path, call: Callable[[], object], *words: str) -> SetupFailed:
    with pytest.raises(SetupFailed) as caught:
        call()
    assert read_record(root) is None
    assert not root.exists()
    assert sorted(p.name for p in root.parent.iterdir()) == []
    for word in words:
        assert word in caught.value.user_message + (caught.value.hint or "")
    return caught.value


def test_a_wrong_checksum_is_refused_and_nothing_is_kept(
    pinned: Callable[[bytes], None], tmp_path: Path
) -> None:
    pinned(GOOD)
    bad = GOOD[:-1] + bytes([GOOD[-1] ^ 1])
    root = tmp_path / "riistudio-5.11.5"
    error = _fails(
        root,
        lambda: download_windows(root, opener=Opener(bad), banner=_banner()),
        "did not match",
    )
    assert "Nothing was installed" in (error.hint or "")


def test_a_short_download_is_refused(pinned: Callable[[bytes], None], tmp_path: Path) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"
    _fails(root, lambda: download_windows(root, opener=Opener(GOOD[:100]), banner=_banner()))


def test_an_oversized_download_stops_early(pinned: Callable[[bytes], None], tmp_path: Path) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"
    huge = Opener(GOOD + b"x" * 10_000, chunk=1000)
    error = _fails(root, lambda: download_windows(root, opener=huge, banner=_banner()))
    assert error.details is not None and "larger" in error.details
    assert sum(1 for _ in huge.urls) == 1


def test_a_network_error_is_explained(pinned: Callable[[bytes], None], tmp_path: Path) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"

    def offline(_url: str) -> io.BufferedReader:
        raise OSError("Name or service not known")

    error = _fails(root, lambda: download_windows(root, opener=offline, banner=_banner()))
    assert "internet" in (error.hint or "")
    assert error.details is not None and "Name or service not known" in error.details


@pytest.mark.parametrize("member", ["../evil.exe", "/abs/evil.exe", "C:/evil.exe", "a/../../x"])
def test_an_archive_escaping_the_folder_is_refused(
    member: str, pinned: Callable[[bytes], None], tmp_path: Path
) -> None:
    data = _zip({"rszst.exe": b"MZ", member: b"evil"})
    pinned(data)
    root = tmp_path / "sub" / "riistudio-5.11.5"
    root.parent.mkdir()
    _fails(root, lambda: download_windows(root, opener=Opener(data), banner=_banner()), "unsafe")
    assert not (tmp_path / "evil.exe").exists() and not (tmp_path / "x").exists()


def test_an_archive_without_rszst_is_refused(
    pinned: Callable[[bytes], None], tmp_path: Path
) -> None:
    data = _zip({"RiiStudio.exe": b"MZ"})
    pinned(data)
    root = tmp_path / "riistudio-5.11.5"
    _fails(root, lambda: download_windows(root, opener=Opener(data), banner=_banner()), "rszst")


def test_a_wrong_banner_is_refused(pinned: Callable[[bytes], None], tmp_path: Path) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"
    error = _fails(
        root,
        lambda: download_windows(
            root, opener=Opener(GOOD), banner=_banner("RiiStudio CLI Alpha 5.11.4")
        ),
        "5.11.5",
    )
    assert error.details is not None and "5.11.4" in error.details


def test_cancel_stops_the_download(pinned: Callable[[bytes], None], tmp_path: Path) -> None:
    pinned(GOOD)
    root = tmp_path / "riistudio-5.11.5"
    token = CancelToken()

    def progress(done: int, _total: int) -> None:
        if done > 20:
            token.cancel()

    with pytest.raises(Cancelled):
        download_windows(
            root, opener=Opener(GOOD), banner=_banner(), cancel=token, on_progress=progress
        )
    assert not root.exists() and list(tmp_path.iterdir()) == []


def test_the_real_banner_check_runs_the_executable_and_ignores_its_exit_code(
    tmp_path: Path,
) -> None:
    exe = fake_executable(tmp_path / "fake é")
    code = "import sys; print('RiiStudio CLI Alpha 5.11.5'); sys.exit(-1)"  # as rszst does
    assert "RiiStudio CLI Alpha 5.11.5" in install.read_banner(exe, ("-c", code))


def test_the_banner_check_reports_a_missing_program(tmp_path: Path) -> None:
    with pytest.raises(CTStudioError):
        install.read_banner(tmp_path / ("nothing.exe" if sys.platform == "win32" else "nothing"))
