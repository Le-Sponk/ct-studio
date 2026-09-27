"""Spike S7, native Windows half (P0-T13): the launch contracts Wine could only suggest.

Throwaway evidence-gathering; findings go to docs/dev/SPIKES.md S7 ("Native Windows").
Windows only. Launches each Windows editor directly (no Wine) with a file whose path
contains spaces *and* non-ASCII characters, then reads what Windows itself reports:
top-level window titles (EnumWindows) and which processes are still alive.

    uv run python spikes/s7_native_windows.py

Editors come from .tools/ (riistudio via bootstrap, s7-lorenzi-win, s7-kmp-cloud, see
ENVIRONMENT.md). BrawlCrate is a user install, so pass it with BRAWLCRATE_EXE.

Deliberately not done here: screenshots (pixels are the only evidence for KMP Cloud's
tree pane), file-association launches (would need registry edits on the user's
machine) and save behaviour (needs a human driving the editor). Those stay HC1 items.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / ".tools"
OUT = REPO / "spikes" / "out" / "s7"
FIXTURES = REPO / "tests" / "fixtures" / "generated"
S3B = REPO / "spikes" / "out" / "s3b" / "work"

BRAWLCRATE = Path(os.environ.get("BRAWLCRATE_EXE", TOOLS / "s7-brawlcrate-bin" / "BrawlCrate.exe"))
RIISTUDIO = TOOLS / "riistudio" / "RiiStudio.exe"
LORENZI = TOOLS / "s7-lorenzi-win" / "Lorenzi's KMP Editor.exe"
KMP_CLOUD = TOOLS / "s7-kmp-cloud" / "KMP Cloud.exe"

SETTLE_S = 12.0
# Spaces, a Latin-1 accent and CJK: exercises the ANSI code page, not just quoting.
PROBE_DIR_NAME = "path with spaces é 日本"


def visible_windows() -> dict[int, tuple[int, str]]:
    """hwnd -> (pid, title) for every visible, titled top-level window."""
    user32 = ctypes.windll.user32
    found: dict[int, tuple[int, str]] = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                found[int(hwnd)] = (pid.value, buffer.value)
        return True

    user32.EnumWindows(callback, 0)
    return found


def image_pids(image: str) -> set[int]:
    """PIDs of every running process with this image name.

    Lists everything and filters here: tasklist's /FI rejects an image name containing
    an apostrophe ("Lorenzi's KMP Editor.exe") as an invalid query.
    """
    proc = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],  # noqa: S607
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
        check=False,
    )
    pids = set()
    for line in proc.stdout.splitlines():
        cells = [c.strip('"') for c in line.split('","')]
        if len(cells) > 1 and cells[0].lower() == image.lower() and cells[1].isdigit():
            pids.add(int(cells[1]))
    return pids


def console_text(pid: int) -> str:
    """Read the visible screen buffer of the console that process pid owns.

    RiiStudio prints `File: <path>` only when stdout is a tty, so the probe gives it a
    console of its own and reads that console back instead of a pipe.
    """
    kernel32 = ctypes.windll.kernel32
    kernel32.FreeConsole()
    if not kernel32.AttachConsole(pid):
        return f"<AttachConsole failed: {ctypes.GetLastError()}>"
    try:
        handle = kernel32.CreateFileW("CONOUT$", 0xC0000000, 3, None, 3, 0, None)
        info = ctypes.create_string_buffer(22)
        kernel32.GetConsoleScreenBufferInfo(handle, info)
        width = int.from_bytes(info.raw[0:2], "little")
        height = int.from_bytes(info.raw[2:4], "little")
        cells = width * height
        buffer = ctypes.create_unicode_buffer(cells)
        read = wintypes.DWORD()
        kernel32.ReadConsoleOutputCharacterW(handle, buffer, cells, 0, ctypes.byref(read))
        kernel32.CloseHandle(handle)
        rows = [buffer.value[i : i + width].rstrip() for i in range(0, read.value, width)]
        return "\n".join(r for r in rows if r)
    finally:
        kernel32.FreeConsole()
        kernel32.AttachConsole(-1)  # back to our parent's console, if any


def riistudio_console_probe(exe: Path, files: list[Path]) -> dict[str, object]:
    """One RiiStudio per file, each in its own console; returns the File:/error lines."""
    if not exe.is_file():
        return {"skipped": f"{exe} not present"}
    preexisting = image_pids(exe.name)
    results = {}
    for path in files:
        process = subprocess.Popen(  # noqa: S603 - local tool, argv only
            [str(exe), str(path)], creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        time.sleep(SETTLE_S)
        text = console_text(process.pid)
        wanted = [
            ln
            for ln in text.splitlines()
            if ln.startswith("File:") or "Failed" in ln or "Cannot connect" in ln
        ]
        results[path.name] = {"alive": process.poll() is None, "lines": wanted}
        kill_pids((image_pids(exe.name) - preexisting) | {process.pid})
    return results


def kill_pids(pids: set[int]) -> None:
    """Kill only processes this probe started: the user may have the same editor open."""
    for pid in sorted(pids):
        subprocess.run(  # noqa: S603 - fixed argv
            ["taskkill", "/F", "/T", "/PID", str(pid)],  # noqa: S607
            capture_output=True,
            timeout=30,
            check=False,
        )


def launch(argv: list[str], log: Path) -> subprocess.Popen[bytes]:
    with log.open("wb") as sink:
        return subprocess.Popen(argv, stdout=sink, stderr=subprocess.STDOUT)  # noqa: S603


def observe(pids: set[int], before: dict[int, tuple[int, str]]) -> dict[str, object]:
    """New windows owned by the probe's processes, and how many of them are alive."""
    now = visible_windows()
    titles = sorted(t for h, (pid, t) in now.items() if h not in before and pid in pids)
    return {"live_processes": len(pids), "new_window_titles": titles}


def probe(name: str, exe: Path, files: list[Path], extra: list[str]) -> dict[str, object]:
    """Launch exe once per file (one file per launch), then observe; always clean up."""
    if not exe.is_file():
        return {"skipped": f"{exe} not present"}
    image = exe.name
    preexisting = image_pids(image)
    before = visible_windows()
    started = time.monotonic()
    processes = []
    for index, path in enumerate(files):
        log = OUT / f"native-{name}-{index}.log"
        processes.append(launch([str(exe), str(path), *extra], log))
        time.sleep(SETTLE_S)
    result: dict[str, object] = {"argv_files": [str(f) for f in files], "extra_args": extra}
    ours = image_pids(image) - preexisting
    result.update(observe(ours, before))
    result["preexisting_instances"] = len(preexisting)
    result["launcher_alive"] = [p.poll() is None for p in processes]
    result["launcher_exit"] = [p.poll() for p in processes]
    result["seconds"] = round(time.monotonic() - started, 1)
    kill_pids(ours | {p.pid for p in processes if p.poll() is None})
    for p in processes:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
    logs = []
    for index in range(len(files)):
        raw = (OUT / f"native-{name}-{index}.log").read_bytes()
        logs.append(raw.decode("utf-8", errors="replace")[-1500:])
    result["captured_output"] = logs
    result["path_in_a_title"] = [
        any(str(f) in t for t in result["new_window_titles"]) for f in files
    ]
    return result


def stage(root: Path, source: Path, name: str) -> Path:
    target = root / PROBE_DIR_NAME / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def main() -> int:
    if os.name != "nt":
        print("Windows only; the Linux contracts are s7_editor_launch.py (Wine).", file=sys.stderr)
        return 2
    brres = S3B / "stage_rszst" / "course_model.brres"
    kmp, kcl = FIXTURES / "course.kmp", FIXTURES / "course.kcl"
    for needed, hint in ((brres, "spikes/s3_backend_bakeoff.py"), (kmp, "make_fixtures.py")):
        if not needed.is_file():
            print(f"missing {needed}; run {hint}", file=sys.stderr)
            return 1
    OUT.mkdir(parents=True, exist_ok=True)
    findings: dict[str, object] = {"probe_dir": PROBE_DIR_NAME, "settle_seconds": SETTLE_S}
    with tempfile.TemporaryDirectory(prefix="s7 native ") as tmp:
        root = Path(tmp)
        first = stage(root, brres, "course model.brres")
        second = stage(root, brres, "second modèle.brres")
        kmp_path = stage(root, kmp, "course.kmp")
        stage(root, kcl, "course.kcl")
        kmp_other = stage(root / "b", kmp, "other é.kmp")
        findings["brawlcrate"] = probe("brawlcrate", BRAWLCRATE, [first, second], ["/audio:none"])
        findings["riistudio"] = probe("riistudio", RIISTUDIO, [first, second], [])
        abmatt = S3B / "stage_abmatt" / "course_model.brres"
        loads = [first, second] + (
            [stage(root, abmatt, "abmatt modèle.brres")] if abmatt.is_file() else []
        )
        findings["riistudio_console"] = riistudio_console_probe(RIISTUDIO, loads)
        findings["lorenzi"] = probe("lorenzi", LORENZI, [kmp_path, kmp_other], [])
        findings["kmp_cloud"] = probe("kmp_cloud", KMP_CLOUD, [kmp_path, kmp_other], [])
    dest = OUT / "s7_native_windows.json"
    dest.write_text(json.dumps(findings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(findings, indent=2, ensure_ascii=False))
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
