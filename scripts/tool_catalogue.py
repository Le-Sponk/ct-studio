"""Tool catalogue for scripts/bootstrap_tools.py.

Every URL, version and checksum here was verified against the publisher on the date in
``VERIFIED_ON``; see docs/reference/TOOLS.md for the evidence. Update this table (and
TOOLS.md) when pinning a new version -- never let the bootstrap script guess a URL.
"""

from __future__ import annotations

from dataclasses import dataclass

VERIFIED_ON = "2026-09-17"

# Platform keys used throughout: "linux-x86_64", "windows-x86_64", "macos-x86_64".


@dataclass(frozen=True)
class Download:
    """One archive to fetch and unpack."""

    url: str
    archive: str
    # SHA-256 of the archive, or None when the publisher does not provide one and we
    # have not pinned our own. Recorded on first download so drift is detectable.
    sha256: str | None = None
    # Directory created inside the archive, stripped so every tool lands in a flat dir.
    strip_prefix: str | None = None
    # An NSIS installer inside the unpacked archive that holds the real tool. It is
    # expanded with 7-Zip, never executed: running it edits the user's PATH/registry.
    nsis_installer: str | None = None


@dataclass(frozen=True)
class Tool:
    """A tool the dev environment needs."""

    name: str
    version: str
    licence: str
    homepage: str
    # Downloads per platform key. A platform absent here is unsupported upstream.
    downloads: dict[str, Download]
    # Executables to expose, relative to the unpacked tool directory (POSIX style).
    # Windows names get ".exe" appended by the installer when missing.
    executables: tuple[str, ...] = ()
    # argv (relative to the tool dir) proving the install works, plus a string the
    # output must contain. Run after unpacking; a failure fails the bootstrap.
    verify: tuple[tuple[str, ...], str] | None = None
    # Exit status the verify command must return. rszst exits -1 even for --version.
    verify_exit: int = 0
    notes: str = ""


WIIMMS = Tool(
    name="wiimms-szs-tools",
    version="2.42a",
    licence="GPL-2.0-or-later",
    homepage="https://szs.wiimm.de/",
    downloads={
        "linux-x86_64": Download(
            url="https://szs.wiimm.de/download/szs-v2.42a-r8989-x86_64.tar.gz",
            archive="szs-v2.42a-r8989-x86_64.tar.gz",
            strip_prefix="szs-v2.42a-r8989-x86_64",
        ),
        "windows-x86_64": Download(
            url="https://szs.wiimm.de/download/szs-v2.42a-r8989-cygwin64.zip",
            archive="szs-v2.42a-r8989-cygwin64.zip",
            strip_prefix="szs-v2.42a-r8989-cygwin64",
        ),
        "macos-x86_64": Download(
            url="https://szs.wiimm.de/download/szs-v2.42a-r8989-mac64.tar.gz",
            archive="szs-v2.42a-r8989-mac64.tar.gz",
            strip_prefix="szs-v2.42a-r8989-mac64",
        ),
    },
    executables=("wszst", "wkclt", "wkmpt", "wimgt", "wbmgt", "wstrt"),
    verify=(("wszst", "version"), "wszst"),
    notes="szs.wiimm.de publishes no checksums; ours are recorded on first download.",
)

BLENDER = Tool(
    name="blender",
    version="5.2.2",
    licence="GPL-2.0-or-later",
    homepage="https://www.blender.org/",
    downloads={
        "linux-x86_64": Download(
            url="https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz",
            archive="blender-5.2.2-linux-x64.tar.xz",
            sha256="84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168",
            strip_prefix="blender-5.2.2-linux-x64",
        ),
        "windows-x86_64": Download(
            url="https://download.blender.org/release/Blender5.2/blender-5.2.2-windows-x64.zip",
            archive="blender-5.2.2-windows-x64.zip",
            sha256="3849d17a682cba006075aaa3f3597ecb5c9c30ec31035b2e092c53e40679b535",
            strip_prefix="blender-5.2.2-windows-x64",
        ),
    },
    executables=("blender",),
    verify=(("blender", "--version"), "Blender 5.2"),
    notes="5.2 LTS. Use --blender 4.5 for the compatibility run (P0-T02 acceptance).",
)

BLENDER_LTS_4_5 = Tool(
    name="blender-4.5",
    version="4.5.14",
    licence="GPL-2.0-or-later",
    homepage="https://www.blender.org/",
    downloads={
        "linux-x86_64": Download(
            url="https://download.blender.org/release/Blender4.5/blender-4.5.14-linux-x64.tar.xz",
            archive="blender-4.5.14-linux-x64.tar.xz",
            sha256="9ba871ff2ecd36526b77432745980b7e6664ecd0c7ca11c48849073dcfe06da3",
            strip_prefix="blender-4.5.14-linux-x64",
        ),
    },
    executables=("blender",),
    verify=(("blender", "--version"), "Blender 4.5"),
    notes="Optional compatibility target; only installed with --only blender-4.5.",
)

BLENDER_LTS_4_2 = Tool(
    name="blender-4.2",
    version="4.2.23",
    licence="GPL-2.0-or-later",
    homepage="https://www.blender.org/",
    downloads={
        "linux-x86_64": Download(
            url="https://download.blender.org/release/Blender4.2/blender-4.2.23-linux-x64.tar.xz",
            archive="blender-4.2.23-linux-x64.tar.xz",
            sha256="bea0eb3146be13eae6225409a117b215184f41b7f79e799f97cb3abb8f6dc404",
            strip_prefix="blender-4.2.23-linux-x64",
        ),
    },
    executables=("blender",),
    verify=(("blender", "--version"), "Blender 4.2"),
    notes=(
        "The add-on's declared floor (blender_manifest.toml blender_version_min). "
        "Only installed with --only blender-4.2; used for add-on compatibility runs."
    ),
)

ABMATT = Tool(
    name="abmatt",
    version="1.3.2",
    licence="GPL-3.0",
    homepage="https://github.com/Robert-N7/abmatt",
    downloads={
        "linux-x86_64": Download(
            url=(
                "https://github.com/Robert-N7/abmatt/releases/download/v1.3.2/"
                "abmatt_linux-5.13.0-44-generic_x64-1.3.2.tar.gz"
            ),
            archive="abmatt_linux-5.13.0-44-generic_x64-1.3.2.tar.gz",
            strip_prefix="abmatt",
        ),
        "windows-x86_64": Download(
            url=(
                "https://github.com/Robert-N7/abmatt/releases/download/v1.3.2/"
                "abmatt_windows-10_x64-1.3.2.zip"
            ),
            archive="abmatt_windows-10_x64-1.3.2.zip",
            strip_prefix="abmatt_windows-10_x64-1.3.2",
            nsis_installer="install.exe",
        ),
    },
    executables=("abmatt",),
    verify=(("abmatt", "--help"), "ANOOB'S BRRES MATERIAL TOOL"),
    notes=(
        "PyInstaller bundle, executable in bin/; needs wimgt on PATH for texture "
        "conversion. The Linux v1.3.2 binary reports 'Version 1.3.1' in its banner "
        "(the Windows one says v1.3.2), so trust the release tag, not the banner. The "
        "Windows zip holds only an NSIS install.exe, which bootstrap expands with 7-Zip."
    ),
)

RIISTUDIO = Tool(
    name="riistudio",
    version="5.11.5",
    licence="unconfirmed overall; never redistribute (ADR-004)",
    homepage="https://github.com/riidefi/RiiStudio",
    downloads={
        "windows-x86_64": Download(
            url=(
                "https://github.com/snailspeed3/RiiStudio/releases/download/Alpha-5.11.5/"
                "RiiStudio_Windows.zip"
            ),
            archive="RiiStudio_Windows.zip",
            sha256="79f4f76158d21b90a401c64d38f5e577138889f15ccc4ea8af8ddb15775c8a38",
        ),
    },
    executables=("rszst", "RiiStudio"),
    verify=(("rszst", "--version"), "RiiStudio CLI Alpha 5.11.5"),
    # exit(-1): 0xFFFFFFFF on Windows (Linux truncates the same call to 255).
    verify_exit=0xFFFFFFFF,
    notes=(
        "Windows/macOS release assets only; Linux builds from source (SPIKES.md S3a). "
        "Asset name is unversioned, so the sha256 (ours, recorded P0-T13; GitHub "
        "publishes no digest for it) is what pins it. Optional: --only riistudio."
    ),
)

# 7-Zip, Windows only: the one extractor here that reads NSIS installers. Fetched on
# demand when a download names an nsis_installer. The full console build ships inside a
# 7z self-extractor, which the standalone 7zr.exe unpacks. Both checksums are GitHub's
# published asset digests for release 26.03 (github.com/ip7z/7zip).
SEVEN_ZIP_REDUCED = Download(
    url="https://github.com/ip7z/7zip/releases/download/26.03/7zr.exe",
    archive="7zr.exe",
    sha256="ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d",
)

SEVEN_ZIP = Tool(
    name="7zip",
    version="26.03",
    licence="LGPL-2.1-or-later (with BSD-3-Clause and unRAR-restricted parts)",
    homepage="https://www.7-zip.org/",
    downloads={
        "windows-x86_64": Download(
            url="https://github.com/ip7z/7zip/releases/download/26.03/7z2603-x64.exe",
            archive="7z2603-x64.exe",
            sha256="0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd",
        ),
    },
    executables=("7z",),
    verify=(("7z",), "7-Zip"),
    notes="Dev-only extractor for NSIS installers; never shipped with CT Studio.",
)

# Windows-only tools. Recorded so `doctor` and the launch-contract spike know what to
# look for, but never auto-downloaded on Linux: they need Wine and a human decision.
WINDOWS_ONLY: dict[str, dict[str, str]] = {
    "lorenzi-kmp-editor": {
        "version": "0.7.7",
        "homepage": "https://github.com/hlorenzi/kmp-editor",
        "asset": (
            "https://github.com/hlorenzi/kmp-editor/releases/download/v0.7.7/"
            "Lorenzi.s.KMP.Editor.0.7.7.exe"
        ),
        "note": "Windows .exe and macOS arm64 only; no Linux build. Linux needs Wine.",
    },
}

TOOLS: tuple[Tool, ...] = (WIIMMS, BLENDER, ABMATT)
OPTIONAL_TOOLS: tuple[Tool, ...] = (BLENDER_LTS_4_5, BLENDER_LTS_4_2, RIISTUDIO)
ALL_TOOLS: dict[str, Tool] = {t.name: t for t in TOOLS + OPTIONAL_TOOLS}

__all__ = [
    "ALL_TOOLS",
    "OPTIONAL_TOOLS",
    "RIISTUDIO",
    "SEVEN_ZIP",
    "SEVEN_ZIP_REDUCED",
    "TOOLS",
    "VERIFIED_ON",
    "WINDOWS_ONLY",
    "Download",
    "Tool",
]
