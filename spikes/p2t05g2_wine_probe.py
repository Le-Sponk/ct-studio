#!/usr/bin/env python3
"""P2-T05g2 Linux Wine probe: measures what the Wine adapter will depend on.

Run on a Linux desktop session (not over SSH), from the repository root:

    python3 spikes/p2t05g2_wine_probe.py

Standard library only, Python 3.10+, so no project install is needed. Everything it downloads
or creates lives in ~/ct-studio-wine-probe (outside the repository; delete it afterwards).
It downloads three pinned, checksummed editor releases (RiiStudio, BrawlCrate, Lorenzi's
KMP Editor), builds Wine prefixes, converts paths with winepath, launches each editor on a
self-made document in a "dossier é 日本" folder, reads the windows with wmctrl, and closes
everything it started with `wineserver -k`. No game files are used.

The result, with your home folder and user name replaced, is written to
~/ct-studio-wine-probe/summary.json; paste that file back.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2t05g2_wine_lib as lib

SETTLE_S = 25.0
PREFIXES = {"win64": "prefix64", "win32": "prefix32", "odd": "préfixe 64 é"}
Windows = dict[str, tuple[int, str]]


def _watch(
    proc: subprocess.Popen[bytes], before: Windows
) -> tuple[float | None, float | None, Windows]:
    """Poll for SETTLE_S: when the launcher exits and when the first new window appears."""
    started = time.monotonic()
    marks: dict[str, float] = {}
    new: Windows = {}
    while (elapsed := round(time.monotonic() - started, 1)) < SETTLE_S:
        if proc.poll() is not None:
            marks.setdefault("exit", elapsed)
        new = {k: v for k, v in lib.windows().items() if k not in before}
        if new:
            marks.setdefault("window", elapsed)
        if "exit" in marks and not new and elapsed > 8:
            break  # the launcher died without ever showing a window
        time.sleep(0.5)
    return marks.get("exit"), marks.get("window"), new


def _stop(proc: subprocess.Popen[bytes], prefix: Path, new: Windows, term: bool) -> dict[str, int]:
    out = {}
    if term and new:
        os.kill(proc.pid, signal.SIGTERM)
        time.sleep(5)
        out["windows_after_launcher_sigterm"] = len([k for k in lib.windows() if k in new])
    lib.stop_prefix(prefix)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    out["windows_after_wineserver_k"] = len([k for k in lib.windows() if k in new])
    return out


def launch(
    label: str, exe: Path, prefix: Path, arg: str, options: tuple[str, ...] = (), term: bool = False
) -> dict[str, object]:
    """Start like CT Studio's launch_detached (own session), keeping the log for diagnostics."""
    print(f"  launching {label} (do not touch the windows) …", flush=True)
    before = lib.windows()
    log = lib.WORK / "logs" / f"{label}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cwd = Path(arg).parent if Path(arg).parent.is_dir() else exe.parent
    with log.open("wb") as sink:
        proc = subprocess.Popen(  # noqa: S603 - fixed local argv
            [shutil.which("wine") or "wine", str(exe), arg, *options],
            cwd=cwd,
            env=lib.wine_env(prefix),
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    exit_at, first_window, new = _watch(proc, before)
    name = Path(arg.replace("\\", "/")).name
    result: dict[str, object] = {
        "argv_tail": [exe.name, arg, *options],
        "exited_rc": proc.poll(),
        "exited_at_s": exit_at,
        "first_window_s": first_window,
        "titles": sorted({title for _pid, title in new.values()}),
        "doc_in_title": any(name in t.replace("\\", "/") for _p, t in new.values()),
        "launcher_owns_a_window": proc.pid in {pid for pid, _t in new.values()},
        "session_processes": lib.session_members(proc.pid),
    }
    result.update(_stop(proc, prefix, new, term))
    result["log"] = lib.tail(log.read_text(encoding="utf-8", errors="replace"), 900)
    return result


def winepath_of(prefix: Path, path: Path) -> str:
    run = lib.sh(["wine", "winepath.exe", "-w", str(path)], env=lib.wine_env(prefix))
    return str(run.get("stdout", "")).strip()


def setup(
    summary: dict[str, object], fresh: bool
) -> tuple[dict[str, Path], dict[str, Path], dict[str, Path]]:
    print("Step 1/5: downloads (checksummed)", flush=True)
    exes = lib.unpack()
    summary["executables"] = {
        k: lib.pe_kind(v.read_bytes()[:65536]) if v.is_file() else "missing after unpack"
        for k, v in exes.items()
    }
    if not all(v.is_file() for v in exes.values()):
        raise RuntimeError(f"unpack failed: {summary['executables']}")
    summary["file_command"] = {
        k: str(lib.sh(["file", "-b", str(v)]).get("stdout", "")).strip() for k, v in exes.items()
    }
    docs = lib.documents()
    print("Step 2/5: Wine prefixes", flush=True)
    prefixes = {k: lib.WORK / v for k, v in PREFIXES.items()}
    summary["prefixes"] = {
        k: lib.make_prefix(v, "win32" if k == "win32" else "win64", fresh)
        for k, v in prefixes.items()
    }
    print("Step 3/5: winepath", flush=True)
    summary["winepath"] = {
        "win64": lib.winepaths(prefixes["win64"], docs),
        "odd prefix": lib.winepaths(prefixes["odd"], docs),
    }
    return exes, docs, prefixes


def launches(
    exes: dict[str, Path], docs: dict[str, Path], pre: dict[str, Path]
) -> dict[str, object]:
    print("Step 4/5: editor launches", flush=True)
    rii, lz, bc = exes["riistudio"], exes["lorenzi"], exes["brawlcrate"]
    p64, p32, odd = pre["win64"], pre["win32"], pre["odd"]
    brres32 = winepath_of(p32, docs["brres"])
    return {
        "riistudio win64 winpath": launch("rii-64", rii, p64, winepath_of(p64, docs["brres"])),
        "riistudio win64 posix path": launch("rii-64-posix", rii, p64, str(docs["brres"])),
        "riistudio win32 (wrong arch)": launch("rii-32", rii, p32, brres32),
        "lorenzi win64 winpath": launch("lz-64", lz, p64, winepath_of(p64, docs["kmp"]), term=True),
        "lorenzi win32 (wrong arch)": launch("lz-32", lz, p32, winepath_of(p32, docs["kmp"])),
        "riistudio in odd prefix": launch(
            "rii-odd", rii, odd, winepath_of(odd, docs["brres_ascii"])
        ),
        "brawlcrate win32 no dotnet": launch("bc-32-nodotnet", bc, p32, brres32, ("/audio:none",)),
    }


def dotnet(exes: dict[str, Path], docs: dict[str, Path], p32: Path) -> dict[str, object]:
    print("Step 5/5: .NET 4.8 in the win32 prefix (about 10 minutes, windows may flash) …")
    env = lib.wine_env(p32)
    steps = {
        "dotnet48": lib.sh(["winetricks", "-q", "dotnet48"], env=env, timeout=2400),
        "win10": lib.sh(["winetricks", "-q", "win10"], env=env, timeout=600),
    }
    lib.stop_prefix(p32)
    result: dict[str, object] = {
        k: {f: v for f, v in step.items() if f != "stdout"} for k, step in steps.items()
    }
    path = winepath_of(p32, docs["brres"])
    result["brawlcrate win32 dotnet48"] = launch(
        "bc-32", exes["brawlcrate"], p32, path, ("/audio:none",)
    )
    return result


def run(args: argparse.Namespace, summary: dict[str, object]) -> None:
    summary["environment"] = lib.environment()
    if not shutil.which("wine"):
        summary["stopped"] = "wine is not installed"
        return
    exes, docs, prefixes = setup(summary, args.fresh)
    if not (os.environ.get("DISPLAY") and shutil.which("wmctrl")):
        summary["stopped"] = "no desktop display or wmctrl; launches skipped"
        return
    summary["launches"] = launches(exes, docs, prefixes)
    summary["dotnet"] = "skipped" if args.skip_dotnet else dotnet(exes, docs, prefixes["win32"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--skip-dotnet", action="store_true", help="skip the slow .NET 4.8 step")
    parser.add_argument("--fresh", action="store_true", help="rebuild the Wine prefixes")
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        print("This probe only runs on Linux.")
        return 2
    lib.WORK.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"probe": "P2-T05g2 wine probe v1"}
    try:
        run(args, summary)
    except Exception:  # a crash is a finding too: keep everything measured so far
        summary["crash"] = traceback.format_exc()[-3000:]
    finally:
        for name in PREFIXES.values():
            if (lib.WORK / name).exists():
                lib.stop_prefix(lib.WORK / name)
    out = lib.WORK / "summary.json"
    out.write_text(json.dumps(lib.redact(summary), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. Send back the contents of: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
