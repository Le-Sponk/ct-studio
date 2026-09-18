"""Tests for scripts/bootstrap_tools.py (P0-T02).

These cover the catalogue's shape and the bootstrap script's failure paths, which are
the parts that could silently install the wrong thing. They never hit the network: the
one test that needs a real archive builds a tiny one locally.

Run: uv run --with pytest --no-project python -m pytest tests/unit/test_bootstrap_tools.py
(Phase 1 wires this into scripts/check.py; see ADR-016.)
"""

from __future__ import annotations

import dataclasses
import shutil
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bootstrap_tools as bt
import tool_catalogue as tc

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Temp dir on the repo volume, cleaned up afterwards.

    Overrides pytest's built-in fixture: the dev container mounts /tmp noexec and
    several tests write a fake tool and execute it (docs/dev/ENVIRONMENT.md).
    """
    base = REPO_ROOT / ".ctstudio" / "pytest-tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# --- catalogue -------------------------------------------------------------------


def test_every_tool_has_a_linux_build_and_verify_command() -> None:
    for tool in tc.TOOLS:
        assert "linux-x86_64" in tool.downloads, f"{tool.name} cannot be installed on Linux CI"
        assert tool.verify is not None, f"{tool.name} would install unverified"
        assert tool.executables, f"{tool.name} exposes no executables"


def test_download_urls_are_https_and_name_their_archive() -> None:
    for tool in tc.ALL_TOOLS.values():
        for plat, spec in tool.downloads.items():
            assert spec.url.startswith("https://"), f"{tool.name}/{plat} is not HTTPS"
            assert spec.url.endswith(spec.archive), (
                f"{tool.name}/{plat}: url does not end with archive name {spec.archive}"
            )


def test_pinned_versions_appear_in_their_urls() -> None:
    """A version bump that forgets the URL (or vice versa) must not pass review."""
    for tool in tc.ALL_TOOLS.values():
        for plat, spec in tool.downloads.items():
            assert tool.version in spec.url, f"{tool.name}/{plat}: {tool.version} not in URL"


def test_published_checksums_are_full_sha256() -> None:
    for tool in tc.ALL_TOOLS.values():
        for spec in tool.downloads.values():
            if spec.sha256 is not None:
                assert len(spec.sha256) == 64, f"{tool.name}: sha256 is not 64 hex chars"
                int(spec.sha256, 16)  # raises if it is not hex


# --- platform handling -----------------------------------------------------------


def test_pick_download_rejects_unsupported_platform_with_guidance() -> None:
    with pytest.raises(bt.BootstrapError) as excinfo:
        bt.pick_download(tc.WIIMMS, "linux-arm64")
    message = str(excinfo.value)
    assert "no linux-arm64 build" in message
    assert "TOOLS.md" in message, "the error should point at the documented alternative"


def test_lorenzi_editor_is_not_auto_installed() -> None:
    """It ships no Linux build, so it must stay out of the default set (needs Wine)."""
    assert "lorenzi-kmp-editor" not in tc.ALL_TOOLS
    assert "lorenzi-kmp-editor" in tc.WINDOWS_ONLY


# --- unpacking -------------------------------------------------------------------


def _tar_with(
    tmp_path: Path,
    names: dict[str, str],
    prefix: str,
    executable: tuple[str, ...] = (),
) -> Path:
    archive = tmp_path / "sample.tar.gz"
    payload = tmp_path / "payload"
    (payload / prefix).mkdir(parents=True)
    for name, text in names.items():
        target = payload / prefix / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if name in executable:
            target.chmod(0o755)
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload / prefix, arcname=prefix)
    return archive


def test_unpack_strips_the_leading_directory(tmp_path: Path) -> None:
    archive = _tar_with(tmp_path, {"hello.txt": "hi"}, prefix="tool-1.0-linux")
    dest = tmp_path / "out"
    bt.unpack(archive, dest, "tool-1.0-linux")
    assert (dest / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert not (dest / "tool-1.0-linux").exists()


def test_unpack_falls_back_when_the_prefix_was_renamed(tmp_path: Path) -> None:
    """Publishers rename top-level dirs between builds; a lone dir is still usable."""
    archive = _tar_with(tmp_path, {"hello.txt": "hi"}, prefix="actually-named-differently")
    dest = tmp_path / "out"
    bt.unpack(archive, dest, "expected-name")
    assert (dest / "hello.txt").exists()


def test_unpack_replaces_an_existing_install(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "stale.txt").write_text("old", encoding="utf-8")
    archive = _tar_with(tmp_path, {"fresh.txt": "new"}, prefix="tool")
    bt.unpack(archive, dest, "tool")
    assert (dest / "fresh.txt").exists()
    assert not (dest / "stale.txt").exists(), "stale files must not survive a reinstall"


def test_unpack_refuses_zip_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "nope")
    with pytest.raises(bt.BootstrapError, match="unsafe path"):
        bt.unpack(archive, tmp_path / "out", None)
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_unpack_rejects_unknown_archive_types(tmp_path: Path) -> None:
    archive = tmp_path / "tool.rar"
    archive.write_bytes(b"not an archive")
    with pytest.raises(bt.BootstrapError, match="unpack"):
        bt.unpack(archive, tmp_path / "out", None)


# --- verification ----------------------------------------------------------------


def _fake_tool(tmp_path: Path, script: str, *, name: str = "faketool") -> Path:
    tool_dir = tmp_path / name
    (tool_dir / "bin").mkdir(parents=True)
    exe = tool_dir / "bin" / name
    exe.write_text(script, encoding="utf-8")
    exe.chmod(0o755)
    return tool_dir


def test_run_verify_accepts_a_matching_banner(tmp_path: Path) -> None:
    tool_dir = _fake_tool(tmp_path, "#!/bin/sh\necho 'FakeTool v1.2.3'\n")
    tool = dataclasses.replace(
        tc.WIIMMS, name="faketool", verify=(("faketool", "version"), "FakeTool v1.2.3")
    )
    assert bt.run_verify(tool, tool_dir) == "FakeTool v1.2.3"


def test_run_verify_skips_decoration_lines(tmp_path: Path) -> None:
    """ABMatt opens with a rule of '='; the recorded banner must be the real line."""
    tool_dir = _fake_tool(tmp_path, "#!/bin/sh\necho '======'\necho 'REAL BANNER'\n")
    tool = dataclasses.replace(
        tc.ABMATT, name="faketool", verify=(("faketool", "--help"), "REAL BANNER")
    )
    assert bt.run_verify(tool, tool_dir) == "REAL BANNER"


def test_run_verify_fails_on_nonzero_exit(tmp_path: Path) -> None:
    tool_dir = _fake_tool(tmp_path, "#!/bin/sh\necho boom >&2\nexit 3\n")
    tool = dataclasses.replace(tc.WIIMMS, name="faketool", verify=(("faketool", "v"), "boom"))
    with pytest.raises(bt.BootstrapError, match="exited 3"):
        bt.run_verify(tool, tool_dir)


def test_run_verify_fails_when_the_banner_is_wrong(tmp_path: Path) -> None:
    """Guards against a tool being silently replaced by something else."""
    tool_dir = _fake_tool(tmp_path, "#!/bin/sh\necho 'SomeOtherTool'\n")
    tool = dataclasses.replace(
        tc.WIIMMS, name="faketool", verify=(("faketool", "version"), "Wiimms SZS Tool")
    )
    with pytest.raises(bt.BootstrapError, match="expected"):
        bt.run_verify(tool, tool_dir)


def test_executable_path_reports_a_missing_binary(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(bt.BootstrapError, match="not found"):
        bt.executable_path(tmp_path / "empty", "wszst")


# --- checksums and state ---------------------------------------------------------


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    import hashlib

    blob = tmp_path / "blob.bin"
    payload = b"ct studio" * 1000
    blob.write_bytes(payload)
    assert bt.sha256_file(blob) == hashlib.sha256(payload).hexdigest()


def test_install_rejects_a_checksum_mismatch_and_deletes_the_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-released archive must fail loudly, not install."""
    monkeypatch.setattr(bt, "TOOLS_DIR", tmp_path / ".tools")
    monkeypatch.setattr(bt, "STATE_PATH", tmp_path / ".tools" / "installed.json")

    archive_name = "sample.tar.gz"
    source = _tar_with(tmp_path, {"bin/faketool": "x"}, prefix="sample")
    cached = bt.TOOLS_DIR / "_downloads" / archive_name
    cached.parent.mkdir(parents=True)
    cached.write_bytes(source.read_bytes())

    tool = dataclasses.replace(
        tc.WIIMMS,
        name="faketool",
        downloads={
            "linux-x86_64": tc.Download(
                url=f"https://example.invalid/{archive_name}",
                archive=archive_name,
                sha256="0" * 64,
            )
        },
    )
    with pytest.raises(bt.BootstrapError, match="checksum mismatch"):
        bt.install(tool, "linux-x86_64", force=False)
    assert not cached.exists(), "a corrupt download must not be left on disk"


def test_install_refetches_when_the_catalogue_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A version/URL/checksum re-pin must not be satisfied by the old install."""
    monkeypatch.setattr(bt, "TOOLS_DIR", tmp_path / ".tools")
    monkeypatch.setattr(bt, "STATE_PATH", tmp_path / ".tools" / "installed.json")
    (bt.TOOLS_DIR / "faketool").mkdir(parents=True)
    bt.save_state(
        {
            "faketool": {
                "version": "1.0.0",
                "url": "https://example.invalid/old.tar.gz",
                "sha256": "a" * 64,
            }
        }
    )

    # Stub the network: "downloading" copies a locally built archive into place.
    source = _tar_with(
        tmp_path,
        {"bin/faketool": "#!/bin/sh\necho 'FakeTool v2'\n"},
        prefix="new",
        executable=("bin/faketool",),
    )
    calls: list[str] = []

    def fake_download(url: str, dest: Path) -> None:
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    monkeypatch.setattr(bt, "download", fake_download)

    tool = dataclasses.replace(
        tc.WIIMMS,
        name="faketool",
        version="2.0.0",
        verify=(("faketool", "version"), "FakeTool v2"),
        downloads={
            "linux-x86_64": tc.Download(
                url="https://example.invalid/new.tar.gz",
                archive="new.tar.gz",
                strip_prefix="new",
            )
        },
    )
    (bt.TOOLS_DIR / "faketool" / "bin").mkdir(parents=True, exist_ok=True)
    record = bt.install(tool, "linux-x86_64", force=False)

    assert calls == ["https://example.invalid/new.tar.gz"], "expected a re-fetch of the new URL"
    assert record["version"] == "2.0.0"
    assert record["sha256"] == bt.sha256_file(source)


def test_state_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bt, "STATE_PATH", tmp_path / "installed.json")
    record = {
        "wiimms-szs-tools": {
            "version": "2.42a",
            "url": "https://example.invalid/a.tar.gz",
        }
    }
    bt.save_state(record)
    assert bt.load_state() == record


def test_load_state_is_empty_before_the_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bt, "STATE_PATH", tmp_path / "nope.json")
    assert bt.load_state() == {}


def test_download_refuses_non_https(tmp_path: Path) -> None:
    """The catalogue is HTTPS-only; a file:// or http:// pin must never be fetched."""
    with pytest.raises(bt.BootstrapError, match="non-HTTPS"):
        bt.download("http://example.invalid/tool.tar.gz", tmp_path / "out.tar.gz")
    with pytest.raises(bt.BootstrapError, match="non-HTTPS"):
        bt.download("file:///etc/passwd", tmp_path / "out.tar.gz")
