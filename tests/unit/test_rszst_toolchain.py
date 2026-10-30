"""Which Rust the Linux rszst build uses: Ubuntu's broken versioned cargo is skipped.

Mint run 3 (P2-T06c): Ubuntu's cargo-1.85 could not open RiiStudio's git dependencies
("invalid version 0 on git_proxy_options", Launchpad bug 2139436, Won't Fix for 1.83-1.89;
fixed in 1.91), even with CARGO_NET_GIT_FETCH_WITH_CLI. So those versions never build.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.tools import rszst_setup as setup

GB = 1024**3
COMMANDS = (*setup.COMMANDS, "clang-19", "clang++-19")


def _ready(tmp_path: Path, *rust: str) -> Path:
    root = tmp_path / "root"
    for name in COMMANDS:
        _tool(root / "usr/bin" / name)
    for version in rust:
        for name in ("rustc", "cargo"):
            _tool(root / "usr/lib" / f"rust-{version}" / "bin" / name)
    for header in setup.HEADERS.values():
        (root / "usr/include" / header).parent.mkdir(parents=True, exist_ok=True)
        (root / "usr/include" / header).write_text("", encoding="utf-8")
    return root


def _tool(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    path.chmod(0o755)


def _check(tmp_path: Path, *rust: str, path: str = "") -> setup.Preflight:
    root = _ready(tmp_path, *rust)
    return setup.preflight(tmp_path / "d", root=root, path=path, free_space=lambda _p: 20 * GB)


@pytest.mark.parametrize("version", ["1.83", "1.85", "1.89", "1.90"])
def test_a_broken_ubuntu_cargo_is_not_used(tmp_path: Path, version: str) -> None:
    result = _check(tmp_path, version)
    assert not result.ok and result.toolchain is None
    assert result.missing_commands == (setup.RUST_LABEL,)
    assert result.skipped_rust == (version,)
    note = (
        f"Not used: Rust {version} from Ubuntu, whose cargo cannot download RiiStudio's"
        " git dependencies (Ubuntu bug 2139436). The apt line above installs Rust 1.91,"
        " which works."
    )
    lines = result.lines()
    assert lines[0] == f"Missing programs: {setup.RUST_LABEL}"
    assert lines[-3:-1] == ["Install them with:", f"  {result.install_command}"]
    assert "rustc-1.91 cargo-1.91" in lines[-2]
    assert lines[-1] == note


@pytest.mark.parametrize(("installed", "chosen"), [
    (("1.82", "1.85"), "1.82"),
    (("1.85", "1.91"), "1.91"),
    (("1.89", "1.78"), "1.78"),
])  # fmt: skip
def test_the_newest_working_rust_is_chosen(
    tmp_path: Path, installed: tuple[str, ...], chosen: str
) -> None:
    result = _check(tmp_path, *installed)
    assert result.ok and result.toolchain is not None
    assert result.toolchain.rust_bin == tmp_path / "root/usr/lib" / f"rust-{chosen}" / "bin"
    assert result.toolchain.rust_version == tuple(int(part) for part in chosen.split("."))
    assert result.lines() == []  # a working Rust was found: no note about the broken one


def test_several_broken_versions_are_listed_oldest_first(tmp_path: Path) -> None:
    result = _check(tmp_path, "1.89", "1.75", "1.85")
    assert result.skipped_rust == ("1.85", "1.89")
    assert result.lines()[-1].startswith("Not used: Rust 1.85, 1.89 from Ubuntu,")


def test_the_listing_order_does_not_depend_on_the_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_glob = Path.glob

    def backwards(self: Path, pattern: str) -> list[Path]:
        return sorted(real_glob(self, pattern), reverse=True)  # ext4 order is arbitrary

    monkeypatch.setattr(Path, "glob", backwards)
    result = _check(tmp_path, "1.85", "1.89")
    assert result.skipped_rust == ("1.85", "1.89")


def test_rust_on_path_is_still_used_beside_a_broken_versioned_one(tmp_path: Path) -> None:
    mine = tmp_path / "cargo bin"
    for name in ("rustc", "cargo"):
        _tool(mine / name)
    result = _check(tmp_path, "1.85", path=str(mine))
    assert result.ok and result.toolchain == setup.Toolchain("clang-19", "clang++-19", None, None)


def test_the_apt_line_installs_the_fixed_rust() -> None:
    assert ("rustc-1.91", "cargo-1.91") == tuple(p for p in setup.BUILD_PACKAGES if "-1." in p)
    assert setup.EXPECTED_TOOLCHAIN.rust_version == (1, 91)
