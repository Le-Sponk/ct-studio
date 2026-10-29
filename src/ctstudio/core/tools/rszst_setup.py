"""The pinned ways to get RiiStudio's CLI (``rszst``) when it is not installed (P2-T06b).

RiiStudio is never bundled (ADR-004): its overall licence is unconfirmed. CT Studio only
detects an existing ``rszst`` or, when the user asks, fetches the official Windows release or
builds the pinned source on Linux into its own folder. This module is planning only: the
pin, the managed folder and its completion record, the Linux build steps and preflight, and
the words ``doctor`` shows. ``rszst_install`` carries the plans out.

A managed copy counts only when ``setup.json`` exists and names an executable inside the
folder; the record is written last, so an interrupted download or build is never "found".
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from ctstudio.core.fsutil import atomic_write_text

Route = Literal["download", "build"]
FreeSpace = Callable[[Path], int]
RECORD = "setup.json"
RECORD_FORMAT = 1
GB = 1024**3


@dataclass(frozen=True)
class Pin:
    version: str
    banner: str
    windows_zip_url: str
    windows_zip_sha256: str
    windows_zip_bytes: int
    source_url: str
    source_tag: str
    source_commit: str
    corrosion_url: str
    corrosion_tag: str
    corrosion_commit: str


# Measured in S3a (Linux build) and P0-T13 (Windows release); SPIKES.md S3.
PIN = Pin(
    version="5.11.5",
    banner="RiiStudio CLI Alpha 5.11.5",
    windows_zip_url=(
        "https://github.com/snailspeed3/RiiStudio/releases/download/Alpha-5.11.5/"
        "RiiStudio_Windows.zip"
    ),
    windows_zip_sha256="79f4f76158d21b90a401c64d38f5e577138889f15ccc4ea8af8ddb15775c8a38",
    windows_zip_bytes=43_609_164,
    source_url="https://github.com/snailspeed3/RiiStudio.git",
    source_tag="Alpha-5.11.5",
    source_commit="09e5754d56562219c87390c8d64ef31110725ccd",
    corrosion_url="https://github.com/corrosion-rs/corrosion.git",
    corrosion_tag="v0.4.10",
    corrosion_commit="9943de73df25ddb06bf6105baeca002ae54e45f3",
)
RELEASES_PAGE = PIN.windows_zip_url.split("/download/")[0]

# Linux build needs. S3a used Debian 13 (Rust 1.85, clang 19, GCC 14). Ubuntu 24.04 / Mint 22
# ship Rust 1.75 by default, which cannot read the pinned Cargo.lock (version 4 needs Cargo
# 1.78), so the versioned rustc-1.85/cargo-1.85 packages (in /usr/lib/rust-1.85/bin) and
# clang-19 are preferred when present. Measured on Mint in P2-T06c.
COMMANDS = ("git", "cmake", "make", "pkg-config")
CLANGS = (("clang-19", "clang++-19"), ("clang", "clang++"))
RUST_MIN = (1, 78)
RUST_LABEL = "Rust 1.78 or newer (rustc and cargo)"
HEADERS = {  # apt package -> a header it installs under /usr/include
    "mesa-common-dev": "GL/gl.h",
    "libglfw3-dev": "GLFW/glfw3.h",
    "libassimp-dev": "assimp/scene.h",
    "libfreetype-dev": "freetype2/ft2build.h",
    "libbz2-dev": "bzlib.h",
    "libssl-dev": "openssl/ssl.h",
}
BUILD_PACKAGES = (
    "build-essential",
    "git",
    "cmake",
    "pkg-config",
    "clang-19",
    "rustc-1.85",
    "cargo-1.85",
    *HEADERS,
    "libstdc++-14-dev",  # provides libstdc++exp, which the final link needs (S3a)
)
BUILD_ESTIMATE = "about 1 hour"
BUILD_DISK_BYTES = 4 * GB
WITHOUT_RSZST = (
    "Without it, models are imported with ABMatt instead: slower, and no material preset "
    "capture or BRRES JSON round-trip."
)


@dataclass(frozen=True)
class SetupRecord:
    route: Route
    version: str
    executable: str  # relative to the managed folder, POSIX separators


def managed_root(data_dir: Path) -> Path:
    return data_dir / "tools" / f"riistudio-{PIN.version}"


def managed_executable(root: Path, platform: Literal["windows", "linux"]) -> Path:
    return root / ("rszst.exe" if platform == "windows" else "build/source/cli/rszst")


def write_record(root: Path, record: SetupRecord) -> None:
    data = {"format": RECORD_FORMAT, **record.__dict__}
    atomic_write_text(root / RECORD, json.dumps(data, indent=1) + "\n")


def read_record(root: Path) -> SetupRecord | None:
    """The completed setup in ``root``, or None if unfinished, foreign or damaged."""
    try:
        data = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    fields = cast("dict[str, object]", data)
    route, executable = fields.get("route"), fields.get("executable")
    if fields.get("format") != RECORD_FORMAT or fields.get("version") != PIN.version:
        return None
    if route not in ("download", "build") or not isinstance(executable, str):
        return None
    record = SetupRecord(route, PIN.version, executable)
    return record if _inside(root, executable) else None


def _inside(root: Path, executable: str) -> bool:
    relative = PurePosixPath(executable)
    if relative.is_absolute() or ".." in relative.parts:
        return False
    return (root / relative).is_file()


# --- Linux build -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    timeout: float
    env: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class Toolchain:
    cc: str
    cxx: str
    rust_bin: Path | None  # a versioned Rust folder; None = rustc/cargo from PATH
    rust_version: tuple[int, int] | None


def build_steps(
    root: Path, *, jobs: int, toolchain: Toolchain, path: str | None = None
) -> tuple[Step, ...]:
    """The S3a recipe, pinned, building into ``root``; run in order."""
    if jobs < 1:
        raise ValueError("jobs must be at least 1")
    src, corrosion, build = root / "source", root / "corrosion", root / "build"
    memory = "-include memory"  # bundled code uses std::unique_ptr without <memory>
    rust_flags: tuple[str, ...] = ()
    rust_env: dict[str, str] = {}
    if toolchain.rust_bin is not None:
        rust_flags = (
            f"-DRust_COMPILER={toolchain.rust_bin / 'rustc'}",
            f"-DRust_CARGO={toolchain.rust_bin / 'cargo'}",
        )
        inherited = path if path is not None else os.environ.get("PATH", "")
        rust_env = {"PATH": os.pathsep.join([str(toolchain.rust_bin), inherited])}
    configure = (
        *("cmake", "-S", str(src), "-B", str(build)),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_C_COMPILER={toolchain.cc}",
        f"-DCMAKE_CXX_COMPILER={toolchain.cxx}",
        f"-DCMAKE_CXX_FLAGS={memory}",
        "-DCMAKE_CXX_STANDARD_LIBRARIES=-lstdc++exp",
        f"-DCPM_corrosion_SOURCE={corrosion}",
        *rust_flags,
    )
    compile_argv = ("cmake", "--build", str(build), "--target", "cli", "--parallel", str(jobs))
    compile_env = {"CXXFLAGS": memory, **rust_env}
    return (
        Step("Download RiiStudio source", _clone(PIN.source_tag, PIN.source_url, src), root, 1800),
        Step("Check out the pinned commit", _checkout(src, PIN.source_commit), root, 120),
        Step(
            "Download Corrosion", _clone(PIN.corrosion_tag, PIN.corrosion_url, corrosion), root, 600
        ),
        Step(
            "Check out the pinned Corrosion commit",
            _checkout(corrosion, PIN.corrosion_commit),
            root,
            120,
        ),
        Step("Configure", configure, root, 1800, rust_env),
        Step("Compile (the long part)", compile_argv, root, 4 * 3600, compile_env),
    )


def _clone(tag: str, url: str, into: Path) -> tuple[str, ...]:
    return ("git", "clone", "--branch", tag, "--depth", "1", url, str(into))


def _checkout(repo: Path, commit: str) -> tuple[str, ...]:
    return ("git", "-C", str(repo), "checkout", "--detach", commit)


# What the apt command in BUILD_PACKAGES installs on Ubuntu 24.04 / Mint 22; shown by dry runs.
EXPECTED_TOOLCHAIN = Toolchain("clang-19", "clang++-19", Path("/usr/lib/rust-1.85/bin"), (1, 85))


@dataclass(frozen=True)
class Preflight:
    missing_commands: tuple[str, ...]
    missing_headers: tuple[str, ...]
    free_bytes: int
    toolchain: Toolchain | None = None
    need_bytes: int = BUILD_DISK_BYTES
    estimate: str = f"{BUILD_ESTIMATE} on a 4-core machine"

    @property
    def ok(self) -> bool:
        return not self.missing_commands and not self.missing_headers and self._room

    @property
    def _room(self) -> bool:
        return self.free_bytes >= self.need_bytes

    @property
    def install_command(self) -> str | None:
        if not self.missing_commands and not self.missing_headers:
            return None
        return "sudo apt install -y " + " ".join(BUILD_PACKAGES)

    def lines(self) -> list[str]:
        out: list[str] = []
        if self.missing_commands:
            out.append("Missing programs: " + ", ".join(self.missing_commands))
        if self.missing_headers:
            names = ", ".join(self.missing_headers)
            out.append(f"Missing libraries (development files): {names}")
        if not self._room:
            free, need = self.free_bytes / GB, self.need_bytes / GB
            out.append(
                f"Not enough free disk space: {free:.1f} GB free, about {need:.1f} GB needed."
            )
        if self.toolchain is not None and self.toolchain.rust_version is None:
            out.append(f"Rust version not checked: the build needs {RUST_LABEL}.")
        if self.install_command:
            out.extend(["Install them with:", f"  {self.install_command}"])
        return out


def disk_free(path: Path) -> int:
    return shutil.disk_usage(path).free


def preflight(
    target: Path,
    *,
    root: Path = Path("/"),
    path: str | None = None,
    free_space: FreeSpace = disk_free,
) -> Preflight:
    """What the Linux build still needs on this machine, checked without running anything."""
    entries = (path if path is not None else os.environ.get("PATH", "")).split(os.pathsep)
    search = [*(Path(e) for e in entries if e), root / "usr/local/bin", root / "usr/bin"]
    missing = [name for name in COMMANDS if not _on(search, name)]
    toolchain, absent = _toolchain(root, search)
    include = root / "usr/include"
    headers = tuple(pkg for pkg, header in HEADERS.items() if not (include / header).is_file())
    free = free_space(_nearest_existing(target))
    return Preflight((*missing, *absent), headers, free, toolchain)


def _toolchain(root: Path, search: list[Path]) -> tuple[Toolchain | None, list[str]]:
    clang = next(((cc, cxx) for cc, cxx in CLANGS if _on(search, cc) and _on(search, cxx)), None)
    rust = _versioned_rust(root) or _path_rust(search)
    absent = ([] if clang else ["clang"]) + ([] if rust else [RUST_LABEL])
    if clang is None or rust is None:
        return None, absent
    return Toolchain(clang[0], clang[1], rust[0], rust[1]), absent


def _versioned_rust(root: Path) -> tuple[Path, tuple[int, int]] | None:
    """The newest ``/usr/lib/rust-X.Y/bin`` with rustc and cargo, if new enough."""
    found: list[tuple[tuple[int, int], Path]] = []
    for folder in (root / "usr/lib").glob("rust-*/bin"):
        match = re.fullmatch(r"rust-(\d+)\.(\d+)", folder.parent.name)
        if match and _runnable(folder / "rustc") and _runnable(folder / "cargo"):
            found.append(((int(match.group(1)), int(match.group(2))), folder))
    usable = [item for item in found if item[0] >= RUST_MIN]
    if not usable:
        return None
    version, folder = max(usable)
    return folder, version


def _path_rust(search: list[Path]) -> tuple[None, None] | None:
    return (None, None) if _on(search, "rustc") and _on(search, "cargo") else None


def _on(folders: list[Path], name: str) -> bool:
    return any(_runnable(folder / name) for folder in folders)


def _nearest_existing(target: Path) -> Path:
    while not target.exists() and target.parent != target:
        target = target.parent
    return target


def _runnable(candidate: Path) -> bool:
    return candidate.is_file() and os.access(candidate, os.X_OK)


# --- doctor wording ------------------------------------------------------------------------------


def missing_fix(platform: str) -> str:
    if platform == "windows":
        size = round(PIN.windows_zip_bytes / 1_000_000)
        return (
            f"Run `ctstudio setup rszst` to download RiiStudio {PIN.version} ({size} MB) from "
            f"{RELEASES_PAGE}, or install it yourself and add the folder to PATH."
        )
    return (
        "RiiStudio has no Linux download. Run `ctstudio setup rszst` to build it from source "
        f"({BUILD_ESTIMATE}, about {BUILD_DISK_BYTES // GB} GB of disk), or put an rszst you "
        "built yourself on PATH."
    )
