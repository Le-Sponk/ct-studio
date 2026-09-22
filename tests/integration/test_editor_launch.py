"""S7 contract tests: external editor launch contracts.

Pins the behaviour P2's `editors` adapter and P5-T07's "Open in..." depend on,
measured in P0-T10. Findings: docs/dev/SPIKES.md S7, table in
docs/reference/TOOLS.md.

Every assertion here comes from a real GUI launch on a private Xvfb display.
"the process stayed alive" is not evidence that the file opened: each test looks
for the path in the window title, or in the editor's own stdout, or in pixels.

The Windows-only editors need hand-built Wine prefixes (ENVIRONMENT.md) and skip
when those, or the editors, are absent.
"""

from __future__ import annotations

import contextlib
import os
import pty
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / ".tools"
SPIKE = REPO / "spikes" / "s7_editor_launch.py"
FIXTURES = REPO / "tests" / "fixtures" / "generated"

BLENDER = TOOLS / "blender" / "blender"
LORENZI = TOOLS / "s7-lorenzi-src" / "dist" / "linux-unpacked" / "hlorenzi-kmp-editor"
BRAWLCRATE = TOOLS / "s7-brawlcrate-bin" / "BrawlCrate.exe"
RIISTUDIO = TOOLS / "s7-riistudio-win" / "RiiStudio.exe"
KMP_CLOUD = TOOLS / "s7-kmp-cloud" / "KMP Cloud.exe"
S3B = REPO / "spikes" / "out" / "s3b" / "work"
RSZST_BRRES = S3B / "stage_rszst" / "course_model.brres"
ABMATT_BRRES = S3B / "stage_abmatt" / "course_model.brres"

XVFB = shutil.which("Xvfb")
XDOTOOL = shutil.which("xdotool")
IMPORT = shutil.which("import")
WINE = shutil.which("wine")
WINEPATH = shutil.which("winepath") or "winepath"

WINE32 = Path(os.environ.get("S7_WINE32", "/root/s7-wine32"))
WINE64 = Path(os.environ.get("S7_WINE64", "/root/s7-wine64"))

DISPLAY = ":78"
SETTLE = 14.0
SHOW_PATH = "import bpy; print('S7_FILE=' + bpy.data.filepath)"

pytestmark = [pytest.mark.integration, pytest.mark.timeout(900)]

needs_x = pytest.mark.skipif(XVFB is None or XDOTOOL is None, reason="Xvfb/xdotool not installed")
needs_wine = pytest.mark.skipif(WINE is None, reason="wine not installed")
needs_shots = pytest.mark.skipif(IMPORT is None, reason="ImageMagick import not installed")

# RiiStudio's update endpoint. It checks this before loading anything; the
# network-marked test below recognizes its own failure output and skips with the
# exact endpoint rather than treating an offline machine as a product failure.
RIISTUDIO_UPDATE_URL = "https://api.github.com/repos/riidefi/RiiStudio/releases/latest"


@pytest.fixture
def display():
    """A private X display; every GUI probe needs one and must not share it."""
    server = subprocess.Popen(  # noqa: S603 - resolved argv
        [XVFB, DISPLAY, "-screen", "0", "1280x800x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    env = dict(os.environ, DISPLAY=DISPLAY, LIBGL_ALWAYS_SOFTWARE="1", WINEDEBUG="-all")
    for _ in range(50):
        if run([XDOTOOL, "search", "--name", "."], env).returncode in (0, 1):
            break
        time.sleep(0.2)
    try:
        yield env
    finally:
        server.terminate()
        server.wait(timeout=15)


def run(argv: list[str], env: dict[str, str] | None = None):
    return subprocess.run(  # noqa: S603 - resolved argv
        argv, capture_output=True, text=True, timeout=300, check=False, env=env
    )


def titles(env: dict[str, str], match: str = ".") -> list[str]:
    found = run([XDOTOOL, "search", "--onlyvisible", "--name", match, "getwindowname", "%@"], env)
    return [line for line in found.stdout.splitlines() if line.strip()]


def start(argv: list[str], env: dict[str, str], pty_out: bool = False):
    """Start a GUI process; on a pty when the editor only talks to a terminal."""
    if not pty_out:
        process = subprocess.Popen(  # noqa: S603 - local tools, argv only
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
        )
        return process, None
    controller, follower = pty.openpty()
    process = subprocess.Popen(  # noqa: S603 - local tools, argv only
        argv, stdout=follower, stderr=follower, stdin=follower, env=env
    )
    os.close(follower)
    return process, controller


def halt(*processes) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def drain(controller: int, seconds: float) -> str:
    """Read a pty for a fixed window; an empty read means "not yet", not EOF."""
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
    # The pty hard-wraps at the terminal width, so drop the newlines too.
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text).replace("\r", "").replace("\n", "")


def launched(argv: list[str], env: dict[str, str], match: str) -> tuple[list[str], bool]:
    """Start a GUI, wait for it, return window titles and liveness, always clean up."""
    process, _ = start(argv, env)
    try:
        time.sleep(SETTLE)
        return titles(env, match), process.poll() is None
    finally:
        halt(process)


def screenshot(argv: list[str], env: dict[str, str], shot: Path) -> list[str]:
    """Some editors only reveal the opened file in pixels. Returns window titles."""
    process, _ = start(argv, env)
    try:
        time.sleep(SETTLE)
        run([IMPORT, "-window", "root", str(shot)], env)
        return titles(env, ".")
    finally:
        halt(process)


def changed_fraction(first: Path, second: Path) -> float:
    numpy = pytest.importorskip("numpy", reason="numpy not installed")
    image = pytest.importorskip("PIL.Image", reason="pillow not installed")
    frames = [numpy.asarray(image.open(s).convert("RGB")).astype("int16") for s in (first, second)]
    return float((numpy.abs(frames[0] - frames[1]).sum(axis=2) > 12).mean())


def win_path(env: dict[str, str], path: Path) -> str:
    return run([WINEPATH, "-w", str(path)], env).stdout.strip()


def spaced(tmp_path: Path, source: Path, name: str) -> Path:
    """Rule 11: every probe path contains a space."""
    target = tmp_path / "path with spaces" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


def blender_opened(*blends: Path) -> tuple[list[str], int]:
    result = run([str(BLENDER), *[str(b) for b in blends], "-b", "--python-expr", SHOW_PATH])
    opened = [
        line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("S7_FILE=")
    ]
    return opened, result.returncode


def test_blender_opens_a_positional_blend_file() -> None:
    """The simplest contract in the table, and the only one assertable headlessly."""
    if not BLENDER.is_file():
        pytest.skip("blender not installed")
    blend = FIXTURES / "fixture_track_good.blend"
    if not blend.is_file():
        pytest.skip("fixture blend not generated")

    opened, code = blender_opened(blend)

    assert code == 0
    assert opened == [str(blend)]


def test_blender_second_positional_replaces_the_first() -> None:
    """Two paths are not two documents: only the last one ends up loaded."""
    if not BLENDER.is_file():
        pytest.skip("blender not installed")
    good = FIXTURES / "fixture_track_good.blend"
    bad = FIXTURES / "fixture_track_bad.blend"
    if not (good.is_file() and bad.is_file()):
        pytest.skip("fixture blends not generated")

    opened, _ = blender_opened(good, bad)

    assert opened == [str(bad)], "one path per launch; a second is not a second document"


@needs_x
@pytest.mark.slow
def test_lorenzi_opens_a_kmp_and_names_it_in_the_title(display, tmp_path: Path) -> None:
    if not LORENZI.is_file():
        pytest.skip("Lorenzi KMP Editor not built")
    kmp = spaced(tmp_path, FIXTURES / "course.kmp", "course.kmp")
    env = dict(display, ELECTRON_DISABLE_SANDBOX="1")

    names, alive = launched([str(LORENZI), str(kmp)], env, "KMP Editor")

    assert alive
    assert any(str(kmp) in name for name in names), names


@needs_x
@pytest.mark.slow
def test_lorenzi_reads_argv_one_so_a_flag_before_the_path_loses_the_file(
    display, tmp_path: Path
) -> None:
    """The trap for the adapter: options must come after the path, not before.

    The editor opens `process.argv[1]` unconditionally. Put `--no-sandbox` first
    and it opens the flag, fails, and silently shows an empty document.
    """
    if not LORENZI.is_file():
        pytest.skip("Lorenzi KMP Editor not built")
    kmp = spaced(tmp_path, FIXTURES / "course.kmp", "course.kmp")
    env = dict(display, ELECTRON_DISABLE_SANDBOX="1")

    names, _ = launched([str(LORENZI), "--no-sandbox", str(kmp)], env, "KMP Editor")

    assert names, "no window appeared at all"
    assert all("New File" in name for name in names), names
    assert not any(str(kmp) in name for name in names)


@needs_x
@needs_shots
@pytest.mark.slow
def test_lorenzi_autoloads_course_kcl_from_the_kmp_folder(display, tmp_path: Path) -> None:
    """Documented on the wiki; confirmed here by what the viewport draws.

    The window title is identical either way, so the evidence is pixels: with a
    `course.kcl` beside the KMP the viewport shows coloured collision, without
    it the editor falls back to a plain default box.
    """
    if not LORENZI.is_file():
        pytest.skip("Lorenzi KMP Editor not built")

    with_kcl = spaced(tmp_path, FIXTURES / "course.kmp", "course.kmp")
    (with_kcl.parent / "course.kcl").write_bytes((FIXTURES / "course.kcl").read_bytes())
    alone = tmp_path / "no kcl" / "course.kmp"
    alone.parent.mkdir(parents=True, exist_ok=True)
    alone.write_bytes((FIXTURES / "course.kmp").read_bytes())
    env = dict(display, ELECTRON_DISABLE_SANDBOX="1")

    shots = []
    for index, kmp in enumerate((with_kcl, alone)):
        shot = tmp_path / f"shot{index}.png"
        screenshot([str(LORENZI), str(kmp)], env, shot)
        shots.append(shot)

    differing = changed_fraction(*shots)
    assert differing > 0.2, f"only {differing:.1%} of pixels differ; the KCL was not loaded"


@needs_x
@needs_wine
@pytest.mark.slow
def test_brawlcrate_opens_a_brres_and_starts_a_second_process(display, tmp_path: Path) -> None:
    """No single-instance forwarding: two launches mean two windows."""
    if not (BRAWLCRATE.is_file() and WINE32.is_dir()):
        pytest.skip("BrawlCrate or its win32 prefix is missing")
    if not RSZST_BRRES.is_file():
        pytest.skip("S3b BRRES not generated")
    first = spaced(tmp_path, RSZST_BRRES, "course model.brres")
    second = spaced(tmp_path, RSZST_BRRES, "second model.brres")
    env = dict(display, WINEPREFIX=str(WINE32))

    processes = [
        start([WINE, str(BRAWLCRATE), win_path(env, path), "/audio:none"], env)[0]
        for path in (first, second)
    ]
    try:
        time.sleep(SETTLE * 2)
        names = titles(env, "BrawlCrate")
    finally:
        halt(*processes)

    assert any("course model.brres" in name for name in names), names
    assert any("second model.brres" in name for name in names), names
    assert len(names) >= 2, "a second launch must not be folded into the first window"


@needs_x
@needs_wine
@pytest.mark.network
@pytest.mark.slow
def test_riistudio_reports_the_file_it_opened_only_on_a_tty(display, tmp_path: Path) -> None:
    """RiiStudio's title never names the file; its `File:` line does, on a tty.

    Also pins the S3b wall from the GUI's side: ABMatt output fails to load with
    the same U16 normal-quantisation error the CLI gives, and the window stays
    up regardless -- so "the process is alive" proves nothing.

    Network precondition (measured in S8): RiiStudio contacts GitHub for an
    update before it loads the file, and when that check fails the `File:` line
    never appears at all. So this test needs that endpoint — hence the
    `network` marker and the precise runtime skip. P5-T07's adapter must not
    depend on this output for the same reason (TD-001 in STATUS).
    """
    if not (RIISTUDIO.is_file() and WINE64.is_dir()):
        pytest.skip("RiiStudio or its win64 prefix is missing")
    if not (RSZST_BRRES.is_file() and ABMATT_BRRES.is_file()):
        pytest.skip("S3b BRRES output not generated")
    env = dict(display, WINEPREFIX=str(WINE64))

    results = {}
    for label, source in (("rszst", RSZST_BRRES), ("abmatt", ABMATT_BRRES)):
        staged = spaced(tmp_path, source, f"{label} model.brres")
        process, controller = start([WINE, str(RIISTUDIO), win_path(env, staged)], env, True)
        try:
            # The load only happens after a GitHub update check. Give that
            # request enough time to succeed or emit its failure; the failure
            # is the explicit network precondition handled below.
            output = drain(controller, SETTLE + 75)
            if "Cannot connect to Github to check for updates:" in output:
                pytest.skip(
                    f"RiiStudio reported its update endpoint ({RIISTUDIO_UPDATE_URL}) unreachable; "
                    "it emits the 'File:' line only after that check completes, so this test "
                    "cannot observe a load without it"
                )
            results[label] = {"alive": process.poll() is None, "output": output}
            results[label]["titles"] = titles(env, "RiiStudio")
        finally:
            halt(process)
            with contextlib.suppress(OSError):
                os.close(controller)

    assert "File: " in results["rszst"]["output"], results["rszst"]["output"][:400]
    assert "rszst model.brres" in results["rszst"]["output"]
    assert "Invalid quantization for normal data: U16" not in results["rszst"]["output"]

    assert "Invalid quantization for normal data: U16" in results["abmatt"]["output"]
    assert results["abmatt"]["alive"], "a failed load must not be visible as a crash"
    assert all("model.brres" not in name for name in results["abmatt"]["titles"])


@needs_x
@needs_wine
@needs_shots
@pytest.mark.slow
def test_kmp_cloud_opens_the_file_but_only_says_so_in_its_tree(display, tmp_path: Path) -> None:
    """The window title is the fixed product name whether or not a file loaded."""
    if not (KMP_CLOUD.is_file() and WINE32.is_dir()):
        pytest.skip("KMP Cloud or its win32 prefix is missing")
    kmp = spaced(tmp_path, FIXTURES / "course.kmp", "course.kmp")
    env = dict(display, WINEPREFIX=str(WINE32))

    with_file = tmp_path / "cloud-file.png"
    without = tmp_path / "cloud-bare.png"
    names = screenshot([WINE, str(KMP_CLOUD), win_path(env, kmp)], env, with_file)
    screenshot([WINE, str(KMP_CLOUD)], env, without)

    assert names, "no KMP Cloud window appeared"
    assert all("course.kmp" not in name for name in names), names
    assert changed_fraction(with_file, without) > 0.0002, "the tree must name the opened file"


def test_the_spike_script_is_runnable_and_self_describing() -> None:
    """The spike must stay reproducible; the findings reference it by name."""
    source = SPIKE.read_text(encoding="utf-8")
    assert "def riistudio_open(" in source
    assert "lorenzi_findings" in source
    assert "windows_path" in source, "Wine needs a converted path, not a POSIX one"
