"""P2-T06c Linux probe: does rszst behave like the Windows recordings under Wine / when built?

Run on Linux from the repository root, inside the project environment:

    uv run python spikes/p2t06c_rszst_probe.py                       # Wine + rszst.exe
    uv run python spikes/p2t06c_rszst_probe.py --native PATH/rszst   # also a built rszst

Wine route: downloads the pinned official RiiStudio 5.11.5 Windows release (44 MB, size and
SHA-256 checked) into ~/ct-studio-rszst-probe, makes a fresh 64-bit Wine prefix there, and
runs ``rszst.exe`` through Wine. Native route (``--native``): runs a Linux-built rszst.
Each route replays all 49 recorded operation cases (tests/fakes/recordings/rszst/5.11.5/
windows-ops.json) on the self-made fixture course in a folder whose name has an "é", and
compares exit code, stdout, stderr and the files written with the Windows recording.
No game files are used. Results (home folder and user name replaced) go to
~/ct-studio-rszst-probe/summary.json; paste that file back.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "scripts"), str(REPO / "tests" / "fakes")]

import record_tool_outputs as rto
from ops_cases import Case
from ops_replay import canonical_stdout

from ctstudio.core.tools.rszst_install import download_windows, read_banner
from ctstudio.core.tools.rszst_setup import PIN

RECORDINGS = REPO / "tests" / "fakes" / "recordings" / "rszst" / PIN.version
DEFAULT_OUT = Path.home() / "ct-studio-rszst-probe"
QUIET_WINE = {"WINEDEBUG": "-all", "WINEDLLOVERRIDES": "mscoree,mshtml="}  # no Mono/Gecko prompts
SNIPPET = 400
_STAMP = re.compile(r"\(Built [^)]*\)")


def main() -> int:
    parser = argparse.ArgumentParser(description="P2-T06c Linux rszst probe")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--native", type=Path, help="a Linux-built rszst to replay as well")
    parser.add_argument("--skip-wine", action="store_true", help="only the --native replay")
    args = parser.parse_args()
    out: Path = args.out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"probe": "p2t06c", "environment": environment()}
    if not args.skip_wine:
        summary["wine"] = _guarded(lambda: wine_route(out))
    if args.native is not None:
        summary["native"] = _guarded(lambda: native_route(args.native.expanduser().resolve(), out))
    write_summary(out, summary)
    crashed = any(isinstance(v, dict) and "crash" in v for v in summary.values())
    return 1 if crashed else 0


def _guarded(route: Callable[[], dict[str, object]]) -> dict[str, object]:
    """One route's result; a crash is recorded so the other route still runs."""
    try:
        return route()
    except Exception:  # report what broke
        return {"crash": traceback.format_exc()}


def environment() -> dict[str, object]:
    release = Path("/etc/os-release")
    os_name = ""
    if release.is_file():
        found = re.search(r'^PRETTY_NAME="?([^"\n]*)', release.read_text(encoding="utf-8"), re.M)
        os_name = found.group(1) if found else ""
    return {
        "os": os_name,
        "kernel": platform.release(),
        "python": platform.python_version(),
        "locale": os.environ.get("LANG", ""),
        "wine": _version(["wine", "--version"]),
        "cpus": os.cpu_count(),
    }


def _version(argv: list[str]) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    done = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    return (done.stdout or done.stderr).strip()


def wine_route(out: Path) -> dict[str, object]:
    if shutil.which("wine") is None:
        return {"skipped": "wine is not installed"}
    started = time.monotonic()
    exe = download_windows(out / "rszst-windows")
    timings: dict[str, float] = {"download_s": round(time.monotonic() - started, 1)}
    prefix = out / "prefix64"
    started = time.monotonic()
    if not (prefix / "system.reg").is_file():
        env = {**os.environ, **QUIET_WINE, "WINEPREFIX": str(prefix), "WINEARCH": "win64"}
        subprocess.run(["wineboot", "-i"], env=env, capture_output=True, timeout=600, check=False)  # noqa: S607
        subprocess.run(["wineserver", "-w"], env=env, capture_output=True, timeout=600, check=False)  # noqa: S607
    timings["prefix_s"] = round(time.monotonic() - started, 1)
    wrapper = out / "rszst-wine"
    lines = [f"export {name}={shlex.quote(value)}" for name, value in QUIET_WINE.items()]
    wrapper.write_text(
        "#!/bin/sh\n" + "\n".join(lines) + f"\nexport WINEPREFIX={shlex.quote(str(prefix))}\n"
        f'exec wine {shlex.quote(str(exe))} "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    started = time.monotonic()
    banner = read_banner(wrapper)
    timings["first_banner_s"] = round(time.monotonic() - started, 1)
    result = replay(wrapper, out / "wine-ops.json")
    return {
        "banner_ok": PIN.banner in banner,
        "banner": banner.strip()[:SNIPPET],
        **timings,
        **result,
    }


def native_route(exe: Path, out: Path) -> dict[str, object]:
    if not exe.is_file():
        return {"skipped": f"no file at {exe}"}
    banner = read_banner(exe)
    return {
        "banner_ok": PIN.banner in banner,
        "banner": banner.strip()[:SNIPPET],
        **replay(exe, out / "native-ops.json"),
    }


def replay(exe: Path, raw_path: Path) -> dict[str, object]:
    """Run every recorded case with ``exe``; compare each with the Windows recording."""
    _tools, cases = rto.TOOLSETS["riistudio"]
    recorded = {str(r["case"]): r for r in rto.load("rszst", PIN.version, "windows")}
    fixture = _fixture()
    records: list[dict[str, object]] = []
    seconds: list[float] = []
    with tempfile.TemporaryDirectory(prefix="ct ops é ") as root:
        for case in cases:
            started = time.monotonic()
            records.append(_run(case, exe, Path(root), fixture))
            seconds.append(time.monotonic() - started)
    raw_path.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    differences = {
        case.name: {**diff, "native_only": case.native_only}
        for case, record in zip(cases, records, strict=True)
        if (diff := compare(record, recorded[case.name]))
    }
    return {
        "cases": len(cases),
        "same_as_windows": len(cases) - len(differences),
        "different": sorted(differences),
        "different_excluding_native_only": sorted(
            name for name, diff in differences.items() if not diff["native_only"]
        ),
        "seconds_total": round(sum(seconds), 1),
        "seconds_slowest": round(max(seconds, default=0.0), 1),
        "details": differences,
    }


def _run(case: Case, exe: Path, root: Path, fixture: Callable[[str], bytes]) -> dict[str, object]:
    try:
        return rto.run_case(case, lambda _tool: exe, root, fixture)
    except Exception as exc:  # a failed setup step is a finding
        return {"case": case.name, "error": f"{type(exc).__name__}: {exc}"[:SNIPPET]}


def _fixture() -> Callable[[str], bytes]:
    def read(name: str) -> bytes:
        return (RECORDINGS / "inputs" / name).read_bytes()

    return read


def compare(got: Mapping[str, object], want: Mapping[str, object]) -> dict[str, object]:
    """The fields that differ, with short snippets; ``{}`` when the run matches."""
    if "error" in got:
        return {"error": got["error"]}
    diff: dict[str, object] = {}
    got_exit, want_exit = int(str(got["exit_code"])) & 0xFF, int(str(want["exit_code"])) & 0xFF
    if got_exit != want_exit:
        diff["exit_code"] = {"got": got["exit_code"], "windows": want["exit_code"]}
    for stream in ("stdout", "stderr"):
        mine, theirs = _text(got[stream]), _text(want[stream])
        if mine != theirs:
            diff[stream] = _first_difference(mine, theirs)
    if got["files"] != want["files"]:
        diff["files"] = {"got": got["files"], "windows": want["files"]}
    return diff


def _text(value: object) -> str:
    """Stdout/stderr without what legitimately differs: build stamp, line ends, thread order."""
    text = str(value).replace("\r\n", "\n")
    return canonical_stdout(_STAMP.sub("(Built <stamp>)", text))


def _first_difference(got: str, want: str) -> dict[str, str]:
    at = next((i for i, (a, b) in enumerate(zip(got, want, strict=False)) if a != b), None)
    at = min(len(got), len(want)) if at is None else at
    start = max(0, at - 60)
    return {"got": got[start : start + SNIPPET], "windows": want[start : start + SNIPPET]}


def write_summary(out: Path, summary: Mapping[str, object]) -> None:
    text = json.dumps(summary, indent=1, ensure_ascii=False)
    text = text.replace(str(Path.home()), "~").replace(getpass.getuser(), "<user>")
    (out / "summary.json").write_text(text + "\n", encoding="utf-8")
    for route in ("wine", "native"):
        part = summary.get(route)
        if isinstance(part, dict) and "cases" in part:
            print(f"{route}: {part['same_as_windows']} of {part['cases']} cases match Windows")
        elif isinstance(part, dict):
            print(
                f"{route}: {'crashed; the error is in summary.json' if 'crash' in part else part}"
            )
    print(f"Wrote {out / 'summary.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
