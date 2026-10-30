"""P2-T06b: ``ctstudio.core.tools.rszst_setup`` — the pinned routes to a working ``rszst``.

Pure planning: no network, no subprocess. A fake filesystem root stands in for a Linux
machine so the preflight's command, header and disk checks are deterministic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ctstudio.core.tools import rszst_setup as setup
from ctstudio.core.tools.rszst_setup import (
    BUILD_PACKAGES,
    PIN,
    SetupRecord,
    build_steps,
    managed_executable,
    managed_root,
    missing_fix,
    preflight,
    read_record,
    write_record,
)

pytestmark = pytest.mark.timeout(30)
GB = 1024**3


# --- the pin -----------------------------------------------------------------------------------


def test_the_pin_matches_the_measured_release_and_source() -> None:
    assert PIN.version == "5.11.5"
    assert PIN.windows_zip_url == (
        "https://github.com/snailspeed3/RiiStudio/releases/download/Alpha-5.11.5/"
        "RiiStudio_Windows.zip"
    )
    assert PIN.windows_zip_sha256 == (
        "79f4f76158d21b90a401c64d38f5e577138889f15ccc4ea8af8ddb15775c8a38"
    )
    assert PIN.windows_zip_bytes == 43_609_164
    assert (PIN.source_url, PIN.source_tag, PIN.source_commit) == (
        "https://github.com/snailspeed3/RiiStudio.git",
        "Alpha-5.11.5",
        "09e5754d56562219c87390c8d64ef31110725ccd",
    )
    assert (PIN.corrosion_url, PIN.corrosion_tag, PIN.corrosion_commit) == (
        "https://github.com/corrosion-rs/corrosion.git",
        "v0.4.10",
        "9943de73df25ddb06bf6105baeca002ae54e45f3",
    )
    assert PIN.banner == "RiiStudio CLI Alpha 5.11.5"


# --- the managed folder ------------------------------------------------------------------------


def test_the_managed_folder_is_versioned_under_user_data(tmp_path: Path) -> None:
    assert managed_root(tmp_path / "data é") == tmp_path / "data é" / "tools" / "riistudio-5.11.5"


@pytest.mark.parametrize(
    ("platform", "relative"),
    [("windows", "rszst.exe"), ("linux", "build/source/cli/rszst")],
)
def test_the_managed_executable_depends_on_the_route(
    platform: str, relative: str, tmp_path: Path
) -> None:
    assert managed_executable(tmp_path, platform) == tmp_path / relative  # type: ignore[arg-type]


def test_a_record_round_trips_and_is_written_last(tmp_path: Path) -> None:
    exe = tmp_path / "rszst.exe"
    exe.write_bytes(b"x")
    write_record(tmp_path, SetupRecord("download", "5.11.5", "rszst.exe"))
    data = json.loads((tmp_path / "setup.json").read_text(encoding="utf-8"))
    assert data == {
        "format": 1,
        "route": "download",
        "version": "5.11.5",
        "executable": "rszst.exe",
    }
    assert read_record(tmp_path) == SetupRecord("download", "5.11.5", "rszst.exe")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rszst.exe", "setup.json"]


@pytest.mark.parametrize(
    "content",
    [
        None,
        "not json",
        '{"format": 2, "route": "download", "version": "5.11.5", "executable": "rszst.exe"}',
        '{"format": 1, "route": "teleport", "version": "5.11.5", "executable": "rszst.exe"}',
        '{"format": 1, "route": "download", "version": "5.11.4", "executable": "rszst.exe"}',
        '{"format": 1, "route": "download", "version": "5.11.5", "executable": "../rszst.exe"}',
        '{"format": 1, "route": "download", "version": "5.11.5", "executable": "gone.exe"}',
        "[1, 2]",
    ],
)
def test_an_unfinished_or_foreign_folder_is_not_a_setup(
    content: str | None, tmp_path: Path
) -> None:
    (tmp_path / "rszst.exe").write_bytes(b"x")
    (tmp_path.parent / "rszst.exe").write_bytes(b"x")
    if content is not None:
        (tmp_path / "setup.json").write_text(content, encoding="utf-8")
    assert read_record(tmp_path) is None


def test_a_missing_folder_is_not_a_setup(tmp_path: Path) -> None:
    assert read_record(tmp_path / "nowhere") is None


# --- Linux build steps ---------------------------------------------------------------------------

TOOLS = setup.Toolchain("clang-19", "clang++-19", Path("/usr/lib/rust-1.85/bin"), (1, 85))


def test_build_steps_are_the_pinned_s3a_recipe(tmp_path: Path) -> None:
    root = tmp_path / "riistudio-5.11.5"
    steps = build_steps(root, jobs=3, toolchain=TOOLS, path="/usr/bin")
    assert [step.name for step in steps] == [
        "Download RiiStudio source",
        "Check out the pinned commit",
        "Download Corrosion",
        "Check out the pinned Corrosion commit",
        "Configure",
        "Compile (the long part)",
    ]
    src, corrosion, build = root / "source", root / "corrosion", root / "build"
    assert steps[0].argv == (
        "git", "clone", "--branch", "Alpha-5.11.5", "--depth", "1",
        "https://github.com/snailspeed3/RiiStudio.git", str(src),
    )  # fmt: skip
    assert steps[1].argv == (
        "git", "-C", str(src), "checkout", "--detach", "09e5754d56562219c87390c8d64ef31110725ccd",
    )  # fmt: skip
    assert steps[2].argv[-1] == str(corrosion) and "v0.4.10" in steps[2].argv
    assert steps[3].argv[-1] == "9943de73df25ddb06bf6105baeca002ae54e45f3"
    configure = steps[4].argv
    assert configure[:5] == ("cmake", "-S", str(src), "-B", str(build))
    rust = Path("/usr/lib/rust-1.85/bin")
    for flag in (
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_COMPILER=clang-19",
        "-DCMAKE_CXX_COMPILER=clang++-19",
        "-DCMAKE_CXX_FLAGS=-include memory",
        "-DCMAKE_CXX_STANDARD_LIBRARIES=-lstdc++exp",
        f"-DCPM_corrosion_SOURCE={corrosion}",
        f"-DRust_COMPILER={rust / 'rustc'}",
        f"-DRust_CARGO={rust / 'cargo'}",
    ):
        assert flag in configure
    assert steps[5].argv == (
        "cmake", "--build", str(build), "--target", "cli", "--parallel", "3",
    )  # fmt: skip
    # Git dependencies via the git CLI: Ubuntu's cargo-1.85 libgit2 bug (Mint run 2).
    rust_path = {
        "CARGO_NET_GIT_FETCH_WITH_CLI": "true",
        "PATH": os.pathsep.join([str(rust), "/usr/bin"]),
    }
    assert steps[4].env == rust_path
    assert steps[5].env == {"CXXFLAGS": "-include memory", **rust_path}
    assert steps[0].env == {}
    assert all(step.cwd == root for step in steps)
    assert steps[5].timeout >= 3 * 3600 and all(step.timeout > 0 for step in steps)


def test_rust_from_path_adds_no_rust_flags(tmp_path: Path) -> None:
    plain = setup.Toolchain("clang", "clang++", None, None)
    steps = build_steps(tmp_path, jobs=1, toolchain=plain, path="/usr/bin")
    assert not [arg for arg in steps[4].argv if arg.startswith("-DRust_")]
    assert "-DCMAKE_C_COMPILER=clang" in steps[4].argv
    cli = {"CARGO_NET_GIT_FETCH_WITH_CLI": "true"}
    assert steps[4].env == cli and steps[5].env == {"CXXFLAGS": "-include memory", **cli}


def test_jobs_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="jobs"):
        build_steps(tmp_path, jobs=0, toolchain=TOOLS)


# --- Linux preflight -----------------------------------------------------------------------------

READY_COMMANDS = (*setup.COMMANDS, "clang-19", "clang++-19")


def _machine(
    tmp_path: Path,
    *,
    commands: tuple[str, ...] = (),
    headers: bool = False,
    rust: tuple[str, ...] = ("1.85",),
) -> Path:
    root = tmp_path / "root"
    (root / "usr/bin").mkdir(parents=True)
    for name in commands:
        _tool(root / "usr/bin" / name)
    for version in rust:
        for name in ("rustc", "cargo"):
            _tool(root / "usr/lib" / f"rust-{version}" / "bin" / name)
    if headers:
        for header in setup.HEADERS.values():
            target = root / "usr/include" / header
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
    return root


def _tool(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    path.chmod(0o755)


def _free(gigabytes: float) -> setup.FreeSpace:
    return lambda _path: int(gigabytes * GB)


def test_a_ready_machine_passes_preflight(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True, rust=("1.75", "1.85", "1.80"))
    result = preflight(tmp_path / "data" / "x", root=root, path="", free_space=_free(20))
    assert result.ok
    assert (result.missing_commands, result.missing_headers) == ((), ())
    assert result.install_command is None
    assert result.free_bytes == 20 * GB
    assert "about 1 hour" in result.estimate
    assert result.toolchain == setup.Toolchain(
        "clang-19", "clang++-19", root / "usr/lib/rust-1.85/bin", (1, 85)
    )
    assert result.lines() == []


def test_plain_clang_is_used_when_clang_19_is_absent(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=(*setup.COMMANDS, "clang", "clang++"), headers=True)
    result = preflight(tmp_path / "d", root=root, path="", free_space=_free(9))
    assert result.toolchain is not None and (result.toolchain.cc, result.toolchain.cxx) == (
        "clang",
        "clang++",
    )


def test_clang_19_is_preferred_when_both_are_installed(tmp_path: Path) -> None:
    both = (*READY_COMMANDS, "clang", "clang++")
    root = _machine(tmp_path, commands=both, headers=True)
    result = preflight(tmp_path / "d", root=root, path="", free_space=_free(9))
    assert result.toolchain is not None and result.toolchain.cc == "clang-19"


def test_clang_19_without_its_cxx_half_falls_back_to_plain_clang(tmp_path: Path) -> None:
    commands = (*setup.COMMANDS, "clang-19", "clang", "clang++")
    root = _machine(tmp_path, commands=commands, headers=True)
    result = preflight(tmp_path / "d", root=root, path="", free_space=_free(9))
    assert result.toolchain is not None
    assert (result.toolchain.cc, result.toolchain.cxx) == ("clang", "clang++")


def test_a_rust_folder_without_cargo_does_not_count(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True, rust=("1.80",))
    _tool(root / "usr/lib/rust-1.85/bin/rustc")  # newer, but no cargo beside it
    result = preflight(tmp_path / "d", root=root, path="", free_space=_free(9))
    assert result.toolchain is not None
    assert result.toolchain.rust_bin == root / "usr/lib/rust-1.80/bin"


def test_the_versioned_rust_wins_over_rust_on_path(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True)
    mine = tmp_path / "cargo bin"
    for name in ("rustc", "cargo"):
        _tool(mine / name)
    result = preflight(tmp_path / "d", root=root, path=str(mine), free_space=_free(9))
    assert result.toolchain is not None
    assert result.toolchain.rust_bin == root / "usr/lib/rust-1.85/bin"


def test_rustc_on_path_without_cargo_is_missing(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True, rust=())
    mine = tmp_path / "half"
    _tool(mine / "rustc")
    result = preflight(tmp_path / "d", root=root, path=str(mine), free_space=_free(9))
    assert result.missing_commands == (setup.RUST_LABEL,)


def test_rust_older_than_1_78_does_not_count(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True, rust=("1.75",))
    result = preflight(tmp_path / "d", root=root, path="", free_space=_free(9))
    assert not result.ok and result.toolchain is None
    assert result.missing_commands == (setup.RUST_LABEL,)


def test_rust_on_path_is_used_with_a_version_note(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True, rust=())
    mine = tmp_path / "cargo bin"
    for name in ("rustc", "cargo"):
        _tool(mine / name)
    result = preflight(tmp_path / "d", root=root, path=str(mine), free_space=_free(9))
    assert result.ok
    assert result.toolchain == setup.Toolchain("clang-19", "clang++-19", None, None)
    assert result.lines() == [f"Rust version not checked: the build needs {setup.RUST_LABEL}."]


def test_an_empty_machine_lists_everything_and_the_apt_command(tmp_path: Path) -> None:
    root = _machine(tmp_path, rust=())
    result = preflight(tmp_path / "data", root=root, path="", free_space=_free(20))
    assert not result.ok
    assert result.missing_commands == (*setup.COMMANDS, "clang", setup.RUST_LABEL)
    assert result.missing_headers == tuple(setup.HEADERS)
    assert result.install_command == "sudo apt install -y " + " ".join(BUILD_PACKAGES)
    for package in ("git", "clang-19", "rustc-1.85", "cargo-1.85", "libstdc++-14-dev"):
        assert package in BUILD_PACKAGES


def test_commands_on_path_count(tmp_path: Path) -> None:
    root = _machine(tmp_path, headers=True)
    elsewhere = tmp_path / "my bin"
    for name in READY_COMMANDS:
        _tool(elsewhere / name)
    result = preflight(
        tmp_path / "d",
        root=root,
        path=os.pathsep.join(["/nope", str(elsewhere)]),
        free_space=_free(9),
    )
    assert result.missing_commands == ()
    assert result.toolchain is not None and result.toolchain.cc == "clang-19"


def test_one_missing_header_is_named(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True)
    (root / "usr/include" / setup.HEADERS["libassimp-dev"]).unlink()
    result = preflight(tmp_path / "d", root=root, path="", free_space=_free(9))
    assert result.missing_headers == ("libassimp-dev",)
    assert not result.ok


@pytest.mark.parametrize(("gigabytes", "ok"), [(3.99, False), (4.0, True)])
def test_disk_space_needs_the_estimate(gigabytes: float, ok: bool, tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=READY_COMMANDS, headers=True)
    seen: list[Path] = []

    def free(path: Path) -> int:
        seen.append(path)
        return int(gigabytes * GB)

    target = tmp_path / "data" / "tools" / "riistudio-5.11.5"
    result = preflight(target, root=root, path="", free_space=free)
    assert result.ok is ok
    assert result.need_bytes == 4 * GB
    assert seen == [tmp_path]  # the nearest folder that exists


def test_preflight_lines_are_plain_words(tmp_path: Path) -> None:
    root = _machine(tmp_path, commands=("git",), rust=())
    lines = preflight(tmp_path / "d", root=root, path="", free_space=_free(1)).lines()
    text = "\n".join(lines)
    assert f"Missing programs: cmake, make, pkg-config, clang, {setup.RUST_LABEL}" in text
    assert "Missing libraries (development files): " in text
    assert "Not enough free disk space: 1.0 GB free, about 4.0 GB needed." in text
    assert "Install them with:\n  sudo apt install -y " in text


# --- doctor wording ------------------------------------------------------------------------------


def test_missing_fix_on_windows_offers_the_download() -> None:
    text = missing_fix("windows")
    assert "ctstudio setup rszst" in text
    assert "44 MB" in text and PIN.windows_zip_url.split("/download/")[0] in text


def test_missing_fix_on_linux_offers_the_build_honestly() -> None:
    text = missing_fix("linux")
    assert "ctstudio setup rszst" in text
    assert "build" in text and "about 1 hour" in text
    assert "PATH" in text


def test_the_features_lost_without_rszst_are_named() -> None:
    assert "ABMatt" in setup.WITHOUT_RSZST
    assert "material preset" in setup.WITHOUT_RSZST
