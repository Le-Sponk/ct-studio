"""Helpers for spikes/p2t05g2_wine_probe.py (standard library only, Python 3.10+)."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import struct
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INPUTS = REPO / "tests" / "fakes" / "recordings"
WORK = Path.home() / "ct-studio-wine-probe"
DOWNLOADS = {
    "riistudio": (
        "https://github.com/snailspeed3/RiiStudio/releases/download/Alpha-5.11.5/RiiStudio_Windows.zip",
        "79f4f76158d21b90a401c64d38f5e577138889f15ccc4ea8af8ddb15775c8a38",
    ),
    "brawlcrate": (
        "https://github.com/soopercool101/BrawlCrate/releases/download/v0.42h1/BrawlCrate.v0.42h1.x86.exe",
        "49196339e461a87008cdf10ff55b264e98980cf2736b41bacf7c154a07d594d5",
    ),
    "lorenzi": (
        "https://github.com/hlorenzi/kmp-editor/releases/download/v0.7.7/Lorenzi.s.KMP.Editor.0.7.7.exe",
        "b6028b1ae6f8bca3bf6b6ff2b07e648ffdd731a1a979d3a9e2f4a6510f6140ef",
    ),
}
MACHINES = {0x14C: "i386", 0x8664: "x86-64", 0xAA64: "arm64"}
SETTLE_S = 25.0
QUIET_BOOT = {"WINEDLLOVERRIDES": "mscoree,mshtml=", "WINEDEBUG": "-all"}


def _scrub(text: str) -> str:
    home, user = str(Path.home()), Path.home().name
    for old in (home, home.replace("/", "\\")):
        text = text.replace(old, "~")
    for sep in ("/", "\\"):  # Wine's C:\\users\\<name>\\ and similar
        text = text.replace(f"{sep}{user}{sep}", f"{sep}<user>{sep}")
    return text


def redact(value: object) -> object:
    """Replace the home folder and user name in every string of a JSON-like value."""
    if isinstance(value, str):
        return _scrub(value)
    if isinstance(value, dict):
        return {redact(k): redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def pe_kind(data: bytes) -> str:
    """'PE32 i386' / 'PE32+ x86-64' from an executable's first bytes, or 'not PE: …'."""
    if data[:2] != b"MZ" or len(data) < 0x40:
        return "not PE: no MZ header"
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if len(data) < offset + 26 or data[offset : offset + 4] != b"PE\0\0":
        return "not PE: no PE signature"
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    magic = struct.unpack_from("<H", data, offset + 24)[0]
    kind = {0x10B: "PE32", 0x20B: "PE32+"}.get(magic, f"magic {magic:#x}")
    return f"{kind} {MACHINES.get(machine, f'machine {machine:#x}')}"


def tail(text: str, limit: int = 600) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip() and "fixme:" not in ln]
    joined = "\n".join(lines)
    return joined[-limit:]


def sh(
    argv: list[str],
    env: dict[str, str] | None = None,
    timeout: float = 120,
    cwd: Path | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - fixed local argv, no shell
            argv, env=env, cwd=cwd, capture_output=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return {"argv": argv, "error": "not installed"}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "error": f"timed out after {timeout:.0f}s"}
    return {
        "argv": argv,
        "rc": proc.returncode,
        "seconds": round(time.monotonic() - started, 1),
        "stdout": proc.stdout.decode("utf-8", "replace"),
        "stderr": tail(proc.stderr.decode("utf-8", "replace")),
    }


def wine_env(prefix: Path, **extra: str) -> dict[str, str]:
    return {**os.environ, "WINEPREFIX": str(prefix), "WINEDEBUG": "fixme-all", **extra}


def wineserver() -> str | None:
    for candidate in (
        shutil.which("wineserver"),
        "/usr/lib/wine/wineserver64",
        "/usr/lib/wine/wineserver32",
        "/usr/lib/wine/wineserver",
        "/opt/wine-stable/bin/wineserver",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def stop_prefix(prefix: Path) -> None:
    server = wineserver()
    if server:
        sh([server, "-k"], env=wine_env(prefix), timeout=30)
        time.sleep(2)


def environment() -> dict[str, object]:
    release = {}
    if Path("/etc/os-release").is_file():
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            release[key] = value.strip('"')
    tools = {
        name: shutil.which(name)
        for name in ("wine", "wine64", "winepath", "winetricks", "7z", "wmctrl", "xdotool", "file")
    }
    packages = sh(
        ["dpkg-query", "-W", "-f", "${Package} ${Version}\n", "wine*", "winetricks", "p7zip-full"]
    )
    return {
        "os": release.get("PRETTY_NAME"),
        "base": release.get("UBUNTU_CODENAME") or release.get("VERSION_CODENAME"),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "session": os.environ.get("XDG_SESSION_TYPE"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        "display": bool(os.environ.get("DISPLAY")),
        "lang": os.environ.get("LANG"),
        "tools": tools,
        "wineserver": wineserver(),
        "wine_version": sh(["wine", "--version"]).get("stdout", "").strip(),  # type: ignore[union-attr]
        "winetricks_version": sh(["winetricks", "--version"]).get("stdout", "").strip(),  # type: ignore[union-attr]
        "packages": str(packages.get("stdout", "")).splitlines(),
    }


def fetch(name: str) -> Path:
    url, digest = DOWNLOADS[name]
    target = WORK / "downloads" / url.rsplit("/", 1)[1]
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        print(f"  downloading {target.name} …", flush=True)
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=300) as response, partial.open("wb") as sink:  # noqa: S310 - pinned https
            shutil.copyfileobj(response, sink)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"checksum mismatch for {url}; nothing was run")
        partial.replace(target)
    return target


def unpack() -> dict[str, Path]:
    """Return the editor executables, unpacked under WORK/editors."""
    editors = WORK / "editors"
    rii = editors / "riistudio" / "RiiStudio.exe"
    if not rii.is_file():
        with zipfile.ZipFile(fetch("riistudio")) as archive:
            archive.extractall(rii.parent)
    brawl = editors / "brawlcrate" / "BrawlCrate.exe"
    if not brawl.is_file():
        sh(["7z", "x", "-y", f"-o{brawl.parent}", str(fetch("brawlcrate"))], timeout=300)
    lorenzi = editors / "lorenzi" / "Lorenzi's KMP Editor.exe"
    if not lorenzi.is_file():
        stage = editors / "lorenzi-installer"
        sh(["7z", "x", "-y", f"-o{stage}", str(fetch("lorenzi"))], timeout=300)
        sh(
            ["7z", "x", "-y", f"-o{lorenzi.parent}", str(stage / "$PLUGINSDIR" / "app-64.7z")],
            timeout=600,
        )
    return {"riistudio": rii, "brawlcrate": brawl, "lorenzi": lorenzi}


def documents() -> dict[str, Path]:
    folder = WORK / "docs" / "dossier é 日本"
    folder.mkdir(parents=True, exist_ok=True)
    sources = {
        "brres": INPUTS / "wszst" / "2.42a" / "inputs" / "map_model.brres",
        "kmp": INPUTS / "wkmpt" / "2.42a" / "inputs" / "course.kmp",
    }
    out = {}
    for key, source in sources.items():
        out[key] = folder / f"pièce {source.name}"
        shutil.copyfile(source, out[key])
    ascii_folder = WORK / "docs" / "plain"
    ascii_folder.mkdir(parents=True, exist_ok=True)
    out["brres_ascii"] = ascii_folder / "map_model.brres"
    shutil.copyfile(sources["brres"], out["brres_ascii"])
    return out


def make_prefix(prefix: Path, arch: str, fresh: bool) -> dict[str, object]:
    if fresh and prefix.exists():
        stop_prefix(prefix)
        shutil.rmtree(prefix)
    reused = (prefix / "system.reg").is_file()
    result: dict[str, object] = {"arch_requested": arch, "reused": reused}
    if not reused:
        prefix.parent.mkdir(parents=True, exist_ok=True)
        print(f"  creating {arch} prefix {prefix.name} …", flush=True)
        result["wineboot"] = sh(
            ["wine", "wineboot", "-u"],
            env=wine_env(prefix, WINEARCH=arch, **QUIET_BOOT),
            timeout=900,
        )
        server = wineserver()
        if server:
            sh([server, "-w"], env=wine_env(prefix), timeout=300)
    registry = prefix / "system.reg"
    if registry.is_file():
        head = registry.read_text(encoding="utf-8", errors="replace")[:400]
        result["arch_in_registry"] = next(
            (ln[6:] for ln in head.splitlines() if ln.startswith("#arch=")), None
        )
    result["syswow64"] = (prefix / "drive_c" / "windows" / "syswow64").is_dir()
    result["ok"] = registry.is_file()
    return result


def winepaths(prefix: Path, docs: dict[str, Path]) -> dict[str, object]:
    out: dict[str, object] = {}
    missing = docs["kmp"].parent / "absent é.kmp"
    for label, path in (
        ("unicode", docs["kmp"]),
        ("ascii", docs["brres_ascii"]),
        ("missing", missing),
    ):
        for tool in (["winepath"], ["wine", "winepath.exe"]):
            run = sh([*tool, "-w", str(path)], env=wine_env(prefix), timeout=60)
            converted = str(run.get("stdout", "")).strip()
            back = (
                sh([*tool, "-u", converted], env=wine_env(prefix), timeout=60) if converted else {}
            )
            out[f"{label} via {tool[-1]}"] = {
                "rc": run.get("rc", run.get("error")),
                "windows": converted,
                "stderr": run.get("stderr"),
                "round_trip_ok": str(back.get("stdout", "")).strip() == str(path),
            }
    return out


def windows() -> dict[str, tuple[int, str]]:
    run = sh(["wmctrl", "-lp"], timeout=10)
    found = {}
    for line in str(run.get("stdout", "")).splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4 and parts[2].isdigit():
            found[parts[0]] = (int(parts[2]), parts[4] if len(parts) > 4 else "")
    return found


def session_members(sid: int) -> list[str]:
    names = []
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            text = stat.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fields = text[text.rfind(")") + 2 :].split()
        if len(fields) > 3 and fields[3] == str(sid):
            names.append(text[text.find("(") + 1 : text.rfind(")")])
    return sorted(names)
