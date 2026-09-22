"""Spike S7: external editor launch contracts (P0-T10).

Throwaway evidence-gathering. Findings go to docs/dev/SPIKES.md S7 and the
launch-contract table in docs/reference/TOOLS.md; the `editors` adapter is
written fresh in P2 (AGENTS.md rule 3).

The question P5-T07 "Open in..." depends on: when CT Studio launches an editor
with a file path, does that editor actually open the file, and does a second
launch reuse the first window or start a new process?

Every probe is a real GUI launch on a private Xvfb display. A launch that
"succeeded" is not evidence: the window title, the editor's own stdout, or the
pixels have to name the file. Windows-only tools run through Wine prefixes built
outside the repo (see docs/dev/ENVIRONMENT.md); each probe skips if absent.

Run:  uv run --with numpy --with pillow python spikes/s7_editor_launch.py
"""

from __future__ import annotations

import json
import os
import pty
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / ".tools"
OUT = REPO / "spikes" / "out" / "s7"
S3B = REPO / "spikes" / "out" / "s3b" / "work"
FIXTURES = REPO / "tests" / "fixtures" / "generated"

BLENDER = TOOLS / "blender" / "blender"
LORENZI_LINUX = TOOLS / "s7-lorenzi-src" / "dist" / "linux-unpacked" / "hlorenzi-kmp-editor"
BRAWLCRATE = TOOLS / "s7-brawlcrate-bin" / "BrawlCrate.exe"
RIISTUDIO = TOOLS / "s7-riistudio-win" / "RiiStudio.exe"
KMP_CLOUD = TOOLS / "s7-kmp-cloud" / "KMP Cloud.exe"

XVFB = shutil.which("Xvfb") or "Xvfb"
XDOTOOL = shutil.which("xdotool") or "xdotool"
IMPORT = shutil.which("import") or "import"
WINE = shutil.which("wine") or "wine"
WINEPATH = shutil.which("winepath") or "winepath"

# Wine prefixes are built by hand (ENVIRONMENT.md) and live outside the repo:
# a win32 prefix with dotnet48 for the two .NET tools, a win64 one for RiiStudio.
WINE32 = Path(os.environ.get("S7_WINE32", "/root/s7-wine32"))
WINE64 = Path(os.environ.get("S7_WINE64", "/root/s7-wine64"))

DISPLAY = ":77"
SETTLE_SECONDS = 14.0
TIMEOUT = 120


@dataclass
class Probe:
    """One launch: what came back, and whether the file was actually opened."""

    alive: bool = False
    windows: list[str] = field(default_factory=list)
    shot: Path | None = None


def sh(argv: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - local tools, argv only
        argv, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=env
    )


def gui_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ, DISPLAY=DISPLAY, LIBGL_ALWAYS_SOFTWARE="1", WINEDEBUG="-all")
    env.update(extra or {})
    return env


def start_xvfb() -> subprocess.Popen[bytes]:
    server = subprocess.Popen(  # noqa: S603 - fixed argv
        [XVFB, DISPLAY, "-screen", "0", "1280x800x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        # xdotool is needed for the probes anyway, so use it as the readiness check.
        if sh([XDOTOOL, "search", "--name", "."], env=gui_env()).returncode in (0, 1):
            return server
        time.sleep(0.2)
    raise RuntimeError("Xvfb did not come up")


def window_titles(match: str = ".") -> list[str]:
    """Visible window names on the probe display, via xdotool."""
    found = sh(
        [XDOTOOL, "search", "--onlyvisible", "--name", match, "getwindowname", "%@"],
        env=gui_env(),
    )
    return [line for line in found.stdout.splitlines() if line.strip()]


def capture(name: str) -> Path:
    """Screenshot the probe display: the only evidence some editors give."""
    OUT.mkdir(parents=True, exist_ok=True)
    shot = OUT / f"{name}.png"
    sh([IMPORT, "-window", "root", str(shot)], env=gui_env())
    return shot


def differing_fraction(first: Path, second: Path) -> float:
    """Fraction of pixels that differ between two screenshots."""
    import numpy as np
    from PIL import Image

    a = np.asarray(Image.open(first).convert("RGB")).astype("int16")
    b = np.asarray(Image.open(second).convert("RGB")).astype("int16")
    if a.shape != b.shape:
        return 1.0
    return round(float((np.abs(a - b).sum(axis=2) > 12).mean()), 4)


def launch(argv: list[str], log: Path, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(  # noqa: S603 - local tools, argv only
        argv, stdout=handle, stderr=subprocess.STDOUT, text=True, env=env or gui_env()
    )


def launch_pty(argv: list[str], env: dict[str, str] | None = None) -> tuple[subprocess.Popen, int]:
    """RiiStudio only prints its `File:` line when stdout is a terminal."""
    controller, follower = pty.openpty()
    process = subprocess.Popen(  # noqa: S603 - local tools, argv only
        argv, stdout=follower, stderr=follower, stdin=follower, env=env or gui_env()
    )
    os.close(follower)
    return process, controller


def drain(controller: int, seconds: float) -> str:
    """Read the pty for a fixed window, stripping escape noise and hard wraps.

    A single read is not enough: the app writes its `File:` line only after a
    GitHub update check, and an empty read means "nothing yet", not EOF.
    """
    chunks: list[bytes] = []
    os.set_blocking(controller, False)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            data = os.read(controller, 65536)
        except (BlockingIOError, OSError):
            data = b""
        if data:
            chunks.append(data)
        else:
            time.sleep(0.05)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text).replace("\r", "")
    return text.replace("\n", "")  # the pty hard-wraps at the terminal width


def stop(*processes: subprocess.Popen[str]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def probe_gui(
    argv: list[str],
    name: str,
    match: str = ".",
    env: dict[str, str] | None = None,
    shot: bool = False,
) -> Probe:
    """Launch once, wait for the UI, record window titles and (optionally) pixels."""
    process = launch(argv, OUT / f"{name}.log", env)
    time.sleep(SETTLE_SECONDS)
    picture = capture(name) if shot else None
    result = Probe(alive=process.poll() is None, windows=window_titles(match), shot=picture)
    stop(process)
    return result


def probe_second_instance(
    argv_a: list[str], argv_b: list[str], name: str, match: str, env: dict[str, str] | None = None
) -> Probe:
    """Two launches, overlapping: does the second reuse the first window?"""
    first = launch(argv_a, OUT / f"{name}-1.log", env)
    time.sleep(SETTLE_SECONDS)
    second = launch(argv_b, OUT / f"{name}-2.log", env)
    time.sleep(SETTLE_SECONDS)
    alive = first.poll() is None and second.poll() is None
    result = Probe(alive=alive, windows=window_titles(match))
    stop(first, second)
    return result


def wine_argv(prefix: Path, exe: Path, *args: str) -> tuple[list[str], dict[str, str]]:
    return [WINE, str(exe), *args], gui_env({"WINEPREFIX": str(prefix)})


def windows_path(prefix: Path, path: Path) -> str:
    """Wine needs a Windows-visible path; POSIX paths are not accepted as-is."""
    env = dict(os.environ, WINEPREFIX=str(prefix))
    return sh([WINEPATH, "-w", str(path)], env=env).stdout.strip()


def spaced_copy(source: Path, filename: str) -> Path:
    """Paths with spaces are rule 11; every probe uses one."""
    target = OUT / "path with spaces" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


def blender_findings() -> dict[str, object]:
    """Blender is the one editor we can drive headlessly and assert exactly."""
    if not BLENDER.is_file():
        return {"skipped": "blender not installed"}
    blend = spaced_copy(FIXTURES / "fixture_track_good.blend", "course track.blend")
    other = spaced_copy(FIXTURES / "fixture_track_bad.blend", "other track.blend")
    show = "import bpy; print('S7_FILE=' + bpy.data.filepath)"

    def opened(result: subprocess.CompletedProcess[str]) -> list[str]:
        prefix = "S7_FILE="
        return [
            line[len(prefix) :] for line in result.stdout.splitlines() if line.startswith(prefix)
        ]

    single = sh([str(BLENDER), str(blend), "-b", "--python-expr", show])
    both = sh([str(BLENDER), str(blend), str(other), "-b", "--python-expr", show])
    return {
        "positional_opens_file": opened(single) == [str(blend)],
        "exit_code": single.returncode,
        "two_positionals_open": opened(both),
        "note": "a second positional replaces the first; it is not a second window",
    }


def lorenzi_findings() -> dict[str, object]:
    """Electron build from source: no Linux release exists (P0-T02)."""
    if not LORENZI_LINUX.is_file():
        return {"skipped": "Lorenzi KMP Editor not built (npm install && npx electron-builder)"}
    kmp = spaced_copy(FIXTURES / "course.kmp", "course.kmp")
    spaced_copy(FIXTURES / "course.kcl", "course.kcl")
    lonely = OUT / "no-kcl"
    lonely.mkdir(parents=True, exist_ok=True)
    (lonely / "course.kmp").write_bytes((FIXTURES / "course.kmp").read_bytes())

    env = gui_env({"ELECTRON_DISABLE_SANDBOX": "1"})
    with_kcl = probe_gui([str(LORENZI_LINUX), str(kmp)], "lorenzi-path", "KMP Editor", env, True)
    no_kcl = probe_gui(
        [str(LORENZI_LINUX), str(lonely / "course.kmp")], "lorenzi-nokcl", "KMP Editor", env, True
    )
    flag_first = probe_gui(
        [str(LORENZI_LINUX), "--no-sandbox", str(kmp)], "lorenzi-flagfirst", "KMP Editor", env
    )
    two = probe_second_instance(
        [str(LORENZI_LINUX), str(kmp)],
        [str(LORENZI_LINUX), str(lonely / "course.kmp")],
        "lorenzi-two",
        "KMP Editor",
        env,
    )
    return {
        "positional_opens_file": any(str(kmp) in title for title in with_kcl.windows),
        "titles": with_kcl.windows,
        "flag_before_path_breaks_it": all("New File" in t for t in flag_first.windows)
        if flag_first.windows
        else None,
        "flag_titles": flag_first.windows,
        "second_instance_windows": two.windows,
        "single_instance": len(two.windows) < 2,
        # course.kcl beside the KMP is auto-loaded, so the viewport differs from
        # the default box it falls back to. Pixels are the only evidence here.
        "kcl_autoload_screen_difference": differing_fraction(with_kcl.shot, no_kcl.shot),
        "kcl_screenshots": [str(s.shot.relative_to(REPO)) for s in (with_kcl, no_kcl)],
    }


def s3b_brres(stage: str) -> Path | None:
    """S3b's staged course models (gitignored): rszst's loads, ABMatt's does not."""
    path = S3B / f"stage_{stage}" / "course_model.brres"
    return path if path.is_file() else None


def brawlcrate_findings(brres: Path | None) -> dict[str, object]:
    if not (BRAWLCRATE.is_file() and WINE32.is_dir() and brres is not None):
        return {"skipped": "BrawlCrate, the win32 prefix or a BRRES is missing"}
    staged = spaced_copy(brres, "course model.brres")
    other = spaced_copy(brres, "second model.brres")
    argv, env = wine_argv(WINE32, BRAWLCRATE, windows_path(WINE32, staged), "/audio:none")
    argv_b, _ = wine_argv(WINE32, BRAWLCRATE, windows_path(WINE32, other), "/audio:none")
    one = probe_gui(argv, "brawlcrate-path", "BrawlCrate", env)
    two = probe_second_instance(argv, argv_b, "brawlcrate-two", "BrawlCrate", env)

    posix, _ = wine_argv(WINE32, BRAWLCRATE, str(staged), "/audio:none")
    unconverted = probe_gui(posix, "brawlcrate-posixpath", "BrawlCrate", env)
    return {
        "titles": one.windows,
        "positional_opens_file": any("course model.brres" in t for t in one.windows),
        "posix_path_titles": unconverted.windows,
        "posix_path_opens_file": any("course model.brres" in t for t in unconverted.windows),
        "second_instance_windows": two.windows,
        "single_instance": len(two.windows) < 2,
    }


def riistudio_open(staged: Path, name: str) -> dict[str, object]:
    """One RiiStudio launch on a pty; returns what it said about the file."""
    argv, env = wine_argv(WINE64, RIISTUDIO, windows_path(WINE64, staged))
    process, controller = launch_pty(argv, env)
    output = drain(controller, SETTLE_SECONDS + 16)  # the load follows an update check
    titles = window_titles("RiiStudio")
    alive = process.poll() is None
    stop(process)
    os.close(controller)
    (OUT / f"{name}.log").write_text(output, encoding="utf-8")

    opened = re.search(r"File: (.{0,140}?)(?:2026-|$)", output)
    failure = re.search(r"Failed to [^:]{0,40}: [^2]{0,80}", output)
    return {
        "titles": titles,
        "title_names_file": any(staged.stem in t for t in titles),
        "alive": alive,
        "stdout_file_line": opened.group(1).strip() if opened else None,
        "stdout_failure": failure.group(0).strip() if failure else None,
    }


def riistudio_findings(brres: Path | None, abmatt: Path | None) -> dict[str, object]:
    """RiiStudio's window title never names the file; its stdout does, on a tty."""
    if not (RIISTUDIO.is_file() and WINE64.is_dir() and brres is not None):
        return {"skipped": "RiiStudio or the win64 prefix is missing"}
    findings: dict[str, object] = {
        "rszst_output": riistudio_open(spaced_copy(brres, "course model.brres"), "riistudio-path"),
        "note": "the `File:` line is only emitted when stdout is a tty",
    }
    if abmatt is not None:
        findings["abmatt_output"] = riistudio_open(
            spaced_copy(abmatt, "abmatt model.brres"), "riistudio-abmatt"
        )
    return findings


def kmp_cloud_findings(kmp: Path) -> dict[str, object]:
    """Same problem as RiiStudio: a fixed window title, so use pixels."""
    if not (KMP_CLOUD.is_file() and WINE32.is_dir()):
        return {"skipped": "KMP Cloud or the win32 prefix is missing"}
    argv, env = wine_argv(WINE32, KMP_CLOUD, windows_path(WINE32, kmp))
    bare, _ = wine_argv(WINE32, KMP_CLOUD)
    with_file = probe_gui(argv, "kmpcloud-path", "KMP Cloud", env, True)
    without = probe_gui(bare, "kmpcloud-nofile", "KMP Cloud", env, True)
    two = probe_second_instance(argv, argv, "kmpcloud-two", "VulcSoft KMP Cloud", env)
    shots = [with_file.shot, without.shot]
    return {
        "titles": with_file.windows,
        "title_names_file": any("course.kmp" in t for t in with_file.windows),
        "alive_with_file": with_file.alive,
        "alive_without_file": without.alive,
        "screenshot_difference": differing_fraction(*shots),
        "screenshots": [str(s.relative_to(REPO)) for s in shots],
        "second_instance_windows": two.windows,
        "single_instance": len(two.windows) < 2,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    server = start_xvfb()
    try:
        brres = s3b_brres("rszst")
        kmp = spaced_copy(FIXTURES / "course.kmp", "course.kmp")
        findings: dict[str, object] = {
            "blender": blender_findings(),
            "lorenzi_kmp_editor": lorenzi_findings(),
            "brawlcrate": brawlcrate_findings(brres),
            "riistudio": riistudio_findings(brres, s3b_brres("abmatt")),
            "kmp_cloud": kmp_cloud_findings(kmp),
        }
    finally:
        server.terminate()
        server.wait(timeout=15)

    destination = OUT / "s7_findings.json"
    destination.write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(findings, indent=2, sort_keys=True))
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
