"""P2-T08d: rszst.exe through Wine as a ``rszst`` launcher in .tools/ for Linux tests."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tool_catalogue as tc  # type: ignore[reportMissingImports] - scripts path inserted above
import tool_paths as tp  # type: ignore[reportMissingImports] - scripts path inserted above
import wine_rszst  # type: ignore[reportMissingImports] - scripts path inserted above


def _release(root: Path) -> Path:
    """What install_wine leaves: the release folder with rszst.exe in it."""
    exe = wine_rszst.wine_executable(root)
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    return exe


def test_release_folder_is_rszst_so_the_launcher_lives_in_bin(tmp_path: Path) -> None:
    assert wine_rszst.wine_executable(tmp_path) == tmp_path / "rszst" / "rszst.exe"
    assert wine_rszst.launcher_path(tmp_path) == tmp_path / "bin" / "rszst"


def test_launcher_runs_the_exe_through_wine_in_its_quiet_prefix(tmp_path: Path) -> None:
    root = tmp_path / "tools dir" / "riistudio-wine"
    text = wine_rszst.launcher_text(Path("/usr/bin/wine stable"), root)
    lines = text.splitlines()
    assert lines[0] == "#!/bin/sh"
    assert f"export WINEPREFIX={shlex.quote((root / 'prefix').as_posix())}" in lines
    assert "export WINEDEBUG=-all" in lines
    assert "export WINEDLLOVERRIDES=mscoree,mshtml=" in lines
    exported = {line.split()[1].split("=")[0] for line in lines if line.startswith("export ")}
    assert exported == set(wine_rszst.wine_environment(root))  # same as CT Studio's route
    exe = shlex.quote((root / "rszst" / "rszst.exe").as_posix())
    assert lines[-1] == f"exec '/usr/bin/wine stable' {exe} \"$@\""


def test_setup_installs_then_writes_an_executable_launcher(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path]] = []

    def install(root: Path, *, wine: Path) -> Path:
        calls.append((root, wine))
        return _release(root)

    root = tmp_path / "riistudio-wine"
    launcher = wine_rszst.setup(
        root, wine=Path("/usr/bin/wine"), install=install, state=tmp_path / "installed.json"
    )
    assert calls == [(root, Path("/usr/bin/wine"))]
    assert launcher == root / "bin" / "rszst"
    assert (root / "rszst" / "rszst.exe").read_bytes() == b"MZ"
    expected = wine_rszst.launcher_text(Path("/usr/bin/wine"), root)
    assert launcher.read_bytes() == expected.encode("utf-8")
    if os.name != "nt":
        assert launcher.stat().st_mode & 0o111 == 0o111


def test_setup_writes_no_launcher_when_the_install_fails(tmp_path: Path) -> None:
    def install(root: Path, *, wine: Path) -> Path:
        raise RuntimeError("download failed")

    with pytest.raises(RuntimeError):
        wine_rszst.setup(
            tmp_path / "w",
            wine=Path("/usr/bin/wine"),
            install=install,
            state=tmp_path / "installed.json",
        )
    assert not (tmp_path / "w" / "bin").exists()


def test_main_refuses_on_windows_and_without_wine(capsys: pytest.CaptureFixture[str]) -> None:
    assert wine_rszst.main(platform="win32", which=lambda _name: "/usr/bin/wine") == 2
    assert "bootstrap_tools.py --only riistudio" in capsys.readouterr().out
    assert wine_rszst.main(platform="linux", which=lambda _name: None) == 1
    assert "sudo apt install -y wine" in capsys.readouterr().out


def test_main_sets_up_into_the_tools_folder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    seen: list[tuple[Path, Path]] = []

    def setup(root: Path, *, wine: Path, state: Path) -> Path:
        seen.append((root, wine))
        assert state == tp.TOOLS_DIR / "installed.json"
        return root / "bin" / "rszst"

    monkeypatch.setattr(wine_rszst, "setup", setup)
    assert wine_rszst.main(platform="linux", which=lambda _name: "/usr/bin/wine") == 0
    assert seen == [(tp.TOOLS_DIR / "riistudio-wine", Path("/usr/bin/wine"))]
    assert str(tp.TOOLS_DIR / "riistudio-wine" / "bin" / "rszst") in capsys.readouterr().out


@pytest.mark.parametrize(
    ("os_name", "present", "expected"),
    [
        ("posix", {"native", "wine"}, "native"),
        ("posix", {"wine"}, "wine"),
        ("posix", set(), "native"),
        ("nt", {"wine", "release"}, "release"),
        ("nt", {"wine"}, "native"),
    ],
)
def test_rszst_prefers_a_native_build_then_wine_on_linux(
    tmp_path: Path, os_name: str, present: set[str], expected: str
) -> None:
    suffix = ".exe" if os_name == "nt" else ""
    paths = {
        "native": tmp_path / "riistudio-build-pinned" / "source" / "cli" / f"rszst{suffix}",
        "wine": tmp_path / "riistudio-wine" / "bin" / "rszst",
        "release": tmp_path / "riistudio" / f"rszst{suffix}",
    }
    for name in present:
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(b"")
    assert tp.rszst_path(tmp_path, os_name) == paths[expected]


def test_rszst_constant_uses_this_system() -> None:
    assert tp.rszst_path(tp.TOOLS_DIR, os.name) == tp.RSZST


@pytest.mark.skipif(os.name == "nt", reason="the launcher is a POSIX shell script")
def test_launcher_passes_arguments_and_exit_code_through(tmp_path: Path) -> None:
    fake_wine = tmp_path / "bin" / "wine"
    fake_wine.parent.mkdir()
    fake_wine.write_text(
        '#!/bin/sh\nprintf "%s|" "$WINEPREFIX" "$WINEDEBUG" "$@"\nexit 7\n', encoding="utf-8"
    )
    fake_wine.chmod(0o755)

    def install(root: Path, *, wine: Path) -> Path:
        return _release(root)

    root = tmp_path / "riistudio wine"
    launcher = wine_rszst.setup(
        root, wine=fake_wine, install=install, state=tmp_path / "installed.json"
    )
    result = subprocess.run(  # noqa: S603 - test launcher, argv only
        [str(launcher), "import-brres", "a b.dae", "out.brres"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 7
    exe = root / "rszst" / "rszst.exe"
    assert result.stdout == f"{root / 'prefix'}|-all|{exe}|import-brres|a b.dae|out.brres|"


def test_through_wine_names_only_the_wine_launcher(tmp_path: Path) -> None:
    assert tp.through_wine(tmp_path / "riistudio-wine" / "bin" / "rszst")
    assert not tp.through_wine(tmp_path / "riistudio-build-pinned" / "source" / "cli" / "rszst")
    assert not tp.through_wine(tmp_path / "riistudio" / "rszst.exe")
    assert not tp.through_wine(tmp_path / "other" / "bin" / "rszst")
    assert not tp.through_wine(wine_rszst.wine_executable(tmp_path / "riistudio-wine"))
    assert tp.through_wine(wine_rszst.launcher_path(wine_rszst.ROOT))


def test_setup_marks_the_launcher_executable_on_every_system(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modes: list[tuple[str, int]] = []
    monkeypatch.setattr(Path, "chmod", lambda self, mode: modes.append((self.name, mode)))
    wine_rszst.setup(
        tmp_path / "w",
        wine=Path("/usr/bin/wine"),
        install=lambda root, *, wine: _release(root),
        state=tmp_path / "installed.json",
    )
    assert modes == [("rszst", 0o755)]


def test_setup_records_the_pinned_release_in_installed_json(tmp_path: Path) -> None:
    """The recorders read the pin from installed.json (record_tool_help.pinned_version)."""
    state = tmp_path / "installed.json"
    state.write_text('{"abmatt": {"version": "1.3.2"}}\n', encoding="utf-8")
    wine_rszst.setup(tmp_path / "w", wine=Path("/usr/bin/wine"), install=_release_ok, state=state)
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["abmatt"] == {"version": "1.3.2"}  # other tools untouched
    assert saved["riistudio"] == {
        "platform": "linux-x86_64-wine",
        "sha256": wine_rszst.PIN.windows_zip_sha256,
        "url": wine_rszst.PIN.windows_zip_url,
        "verify": wine_rszst.PIN.banner,
        "version": wine_rszst.PIN.version,
    }
    # record_tool_help.pinned_version compares it with the catalogue pin.
    assert saved["riistudio"]["version"] == tc.ALL_TOOLS["riistudio"].version


def test_setup_creates_installed_json_when_missing(tmp_path: Path) -> None:
    state = tmp_path / "tools" / "installed.json"
    wine_rszst.setup(tmp_path / "w", wine=Path("/usr/bin/wine"), install=_release_ok, state=state)
    assert list(json.loads(state.read_text(encoding="utf-8"))) == ["riistudio"]


def test_failed_setup_leaves_installed_json_alone(tmp_path: Path) -> None:
    state = tmp_path / "installed.json"
    state.write_text("{}\n", encoding="utf-8")

    def install(root: Path, *, wine: Path) -> Path:
        raise RuntimeError("download failed")

    with pytest.raises(RuntimeError):
        wine_rszst.setup(tmp_path / "w", wine=Path("/usr/bin/wine"), install=install, state=state)
    assert state.read_text(encoding="utf-8") == "{}\n"


def _release_ok(root: Path, *, wine: Path) -> Path:
    return _release(root)
