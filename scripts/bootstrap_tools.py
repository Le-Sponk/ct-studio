#!/usr/bin/env python3
"""Download the external tools CT Studio needs into .tools/ (gitignored).

Idempotent: a second run re-verifies what is installed and downloads nothing.
Versions, URLs and checksums live in scripts/tool_catalogue.py, which is filled in
from publisher evidence recorded in docs/reference/TOOLS.md (AGENTS.md rule 4).

    uv run python scripts/bootstrap_tools.py              # install the default set
    uv run python scripts/bootstrap_tools.py --only blender
    uv run python scripts/bootstrap_tools.py --list       # print the version table
    uv run python scripts/bootstrap_tools.py --force      # re-download and re-unpack

This is a standalone dev script, so it may spawn processes directly (AGENTS.md rule 3):
argv lists only, explicit timeouts, explicit exit-code handling, never shell=True.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tool_catalogue import (  # sys.path is extended just above; E402 is off in pyproject.toml
    ALL_TOOLS,
    SEVEN_ZIP,
    SEVEN_ZIP_REDUCED,
    TOOLS,
    WINDOWS_ONLY,
    Download,
    Tool,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / ".tools"
STATE_PATH = TOOLS_DIR / "installed.json"
DOWNLOAD_TIMEOUT_S = 600
VERIFY_TIMEOUT_S = 120
CHUNK = 1 << 20


class BootstrapError(RuntimeError):
    """A step failed in a way the user must act on."""


def current_platform() -> str:
    system = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}.get(platform.system())
    machine = {
        "x86_64": "x86_64",
        "AMD64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(platform.machine())
    if system is None or machine is None:
        raise BootstrapError(
            f"Unsupported platform {platform.system()}/{platform.machine()}. "
            "Install the tools manually and record their paths in user settings."
        )
    return f"{system}-{machine}"


def load_state() -> dict[str, dict[str, str]]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, dict[str, str]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    """Fetch url to dest, writing to a temp file first so partials never look complete."""
    if not url.startswith("https://"):
        raise BootstrapError(f"Refusing to download over a non-HTTPS URL: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "ct-studio-bootstrap"})  # noqa: S310
    started = time.monotonic()
    try:
        # S310: the https scheme is enforced above, so file:/custom schemes cannot reach here.
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as response:  # noqa: S310
            if response.status != 200:
                raise BootstrapError(f"{url} returned HTTP {response.status}")
            with tmp.open("wb") as handle:
                shutil.copyfileobj(response, handle, CHUNK)
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise BootstrapError(f"Could not download {url}: {exc.reason}") from exc
    tmp.replace(dest)
    size_mb = dest.stat().st_size / 1e6
    print(f"    downloaded {size_mb:.1f} MB in {time.monotonic() - started:.1f}s")


def unpack(archive: Path, dest: Path, strip_prefix: str | None) -> None:
    """Unpack archive into dest, optionally removing one leading directory."""
    staging = dest.parent / f"{dest.name}.unpack"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    if archive.name.endswith((".tar.gz", ".tar.xz")):
        with tarfile.open(archive) as tar:
            # filter="data" refuses absolute paths, .. traversal and special files.
            tar.extractall(staging, filter="data")
    elif archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                target = (staging / member).resolve()
                if not target.is_relative_to(staging.resolve()):
                    raise BootstrapError(f"{archive.name} contains unsafe path {member!r}")
            # S202: every member was checked against the staging root just above.
            zf.extractall(staging)  # noqa: S202
    else:
        raise BootstrapError(f"Don't know how to unpack {archive.name}")

    root = staging / strip_prefix if strip_prefix else staging
    if not root.is_dir():
        # Publishers rename top-level dirs between builds; fall back to a lone dir.
        entries = [p for p in staging.iterdir()]
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        else:
            raise BootstrapError(
                f"{archive.name}: expected directory {strip_prefix!r} inside the archive"
            )

    if dest.exists():
        shutil.rmtree(dest)
    root.replace(dest)
    shutil.rmtree(staging, ignore_errors=True)


def executable_path(tool_dir: Path, name: str) -> Path:
    """Find an executable that may sit at the tool root or in bin/."""
    candidates = [tool_dir / name, tool_dir / "bin" / name]
    if platform.system() == "Windows":
        # Append rather than with_suffix(), which would truncate a dotted name.
        candidates = [c.with_name(c.name + ".exe") for c in candidates] + candidates
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BootstrapError(f"{name} not found in {tool_dir}")


def run_checked(
    argv: list[str], what: str, timeout: float = VERIFY_TIMEOUT_S, expect_exit: int = 0
) -> str:
    """Run argv (no shell) and return stdout+stderr; any failure raises BootstrapError."""
    try:
        proc = subprocess.run(  # noqa: S603  (argv list, no shell)
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        name = Path(argv[0]).name
        raise BootstrapError(f"{what}: {name} timed out after {exc.timeout}s") from exc
    except OSError as exc:
        raise BootstrapError(f"{what}: could not run {argv[0]}: {exc}") from exc
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != expect_exit:
        tail = "\n".join(output.splitlines()[-5:])
        raise BootstrapError(f"{what}: {' '.join(argv)} exited {proc.returncode}.\n{tail}")
    return output


def run_verify(tool: Tool, tool_dir: Path) -> str:
    """Run the tool's verify command and return its first output line."""
    if tool.verify is None:
        return "(no verify command)"
    argv_names, expected = tool.verify
    argv = [str(executable_path(tool_dir, argv_names[0])), *argv_names[1:]]
    output = run_checked(argv, tool.name, expect_exit=tool.verify_exit)
    if expected.lower() not in output.lower():
        tail = "\n".join(output.splitlines()[:5])
        raise BootstrapError(
            f"{tool.name}: expected {expected!r} in the output of "
            f"{' '.join(argv_names)}, got:\n{tail}"
        )
    # Report the line that proved it: rszst prints its parser version before the app's,
    # and ABMatt opens with a rule of "=".
    lines = [ln.strip() for ln in output.splitlines() if ln.strip().strip("=")]
    proof = [ln for ln in lines if expected.lower() in ln.lower()]
    return (proof or lines or ["(no output)"])[0]


def pick_download(tool: Tool, plat: str) -> Download:
    if plat in tool.downloads:
        return tool.downloads[plat]
    raise BootstrapError(
        f"{tool.name} has no {plat} build. Supported: {', '.join(sorted(tool.downloads))}. "
        "See docs/reference/TOOLS.md for the alternative (Wine or manual install)."
    )


def fetch_verified(spec: Download, tool_name: str, *, force: bool) -> tuple[Path, str]:
    """Download spec (or reuse the cache) and check its checksum; returns (path, sha256)."""
    archive = TOOLS_DIR / "_downloads" / spec.archive
    if force or not archive.exists():
        print(f"    fetching {spec.url}")
        download(spec.url, archive)
    else:
        print(f"    reusing cached {archive.name}")

    digest = sha256_file(archive)
    if spec.sha256 and digest != spec.sha256:
        archive.unlink(missing_ok=True)
        raise BootstrapError(
            f"{tool_name}: checksum mismatch for {spec.archive}.\n"
            f"  expected {spec.sha256}\n  got      {digest}\n"
            "The download was deleted. If the publisher re-released this version, update "
            "scripts/tool_catalogue.py and docs/reference/TOOLS.md with the new checksum."
        )
    if spec.sha256:
        print("    sha256 matches the pinned checksum")
    else:
        print(f"    sha256 (unpublished upstream, recorded): {digest}")
    return archive, digest


def ensure_seven_zip(plat: str, *, force: bool) -> Path:
    """Install 7-Zip into .tools/7zip on demand and return its 7z executable.

    The full console 7z ships inside a 7z self-extractor. Running that would install
    7-Zip system-wide, so the standalone 7zr.exe unpacks it instead.
    """
    tool_dir = TOOLS_DIR / SEVEN_ZIP.name
    spec = pick_download(SEVEN_ZIP, plat)
    print(f"  {SEVEN_ZIP.name} {SEVEN_ZIP.version} (needed to expand an NSIS installer)")
    state = load_state()
    if tool_dir.exists() and state.get(SEVEN_ZIP.name, {}).get("url") == spec.url and not force:
        run_verify(SEVEN_ZIP, tool_dir)
        return executable_path(tool_dir, "7z")

    reduced, _ = fetch_verified(SEVEN_ZIP_REDUCED, SEVEN_ZIP.name, force=force)
    sfx, digest = fetch_verified(spec, SEVEN_ZIP.name, force=force)
    staging = tool_dir.parent / f"{tool_dir.name}.unpack"
    shutil.rmtree(staging, ignore_errors=True)
    run_checked([str(reduced), "x", "-y", f"-o{staging}", str(sfx)], SEVEN_ZIP.name)
    shutil.rmtree(tool_dir, ignore_errors=True)
    staging.replace(tool_dir)
    banner = run_verify(SEVEN_ZIP, tool_dir)
    print(f"    installed: {banner}")
    state[SEVEN_ZIP.name] = {
        "version": SEVEN_ZIP.version,
        "platform": plat,
        "verify": banner,
        "url": spec.url,
        "sha256": digest,
    }
    save_state(state)
    return executable_path(tool_dir, "7z")


def expand_nsis(seven_zip: Path, tool_dir: Path, installer: str) -> None:
    """Replace tool_dir with the payload of the NSIS installer it contains.

    The installer is never executed: it would edit PATH and the registry, and ABMatt's
    upstream README warns that it can hang. NSIS's own runtime plugins are dropped.
    """
    source = tool_dir / installer
    if not source.is_file():
        raise BootstrapError(f"expected NSIS installer {installer!r} in {tool_dir}")
    staging = tool_dir.parent / f"{tool_dir.name}.nsis"
    shutil.rmtree(staging, ignore_errors=True)
    run_checked([str(seven_zip), "x", "-y", f"-o{staging}", str(source)], tool_dir.name)
    shutil.rmtree(staging / "$PLUGINSDIR", ignore_errors=True)
    (staging / "uninstall.exe").unlink(missing_ok=True)
    shutil.rmtree(tool_dir)
    staging.replace(tool_dir)


def install(tool: Tool, plat: str, *, force: bool) -> dict[str, str]:
    """Install one tool; returns its state record. Idempotent unless force."""
    tool_dir = TOOLS_DIR / tool.name
    spec = pick_download(tool, plat)
    print(f"  {tool.name} {tool.version}")

    # Reuse an existing install only when the state file agrees with the catalogue.
    # Otherwise a re-pinned version or checksum would be silently ignored.
    record = load_state().get(tool.name, {})
    unchanged = (
        record.get("version") == tool.version
        and record.get("url") == spec.url
        and (spec.sha256 is None or record.get("sha256") == spec.sha256)
    )
    if tool_dir.exists() and unchanged and not force:
        banner = run_verify(tool, tool_dir)
        print(f"    already installed: {banner}")
        return {**record, "version": tool.version, "platform": plat, "verify": banner}
    if tool_dir.exists() and not unchanged:
        print("    catalogue changed since install; re-fetching")

    archive, digest = fetch_verified(spec, tool.name, force=force)
    unpack(archive, tool_dir, spec.strip_prefix)
    if spec.nsis_installer:
        expand_nsis(ensure_seven_zip(plat, force=force), tool_dir, spec.nsis_installer)
    banner = run_verify(tool, tool_dir)
    print(f"    installed: {banner}")
    return {
        "version": tool.version,
        "platform": plat,
        "verify": banner,
        "url": spec.url,
        "sha256": digest,
    }


def print_table(state: dict[str, dict[str, str]]) -> None:
    if not state:
        print("Nothing installed yet. Run scripts/bootstrap_tools.py.")
        return
    width = max(len(n) for n in state)
    print(f"\n{'TOOL'.ljust(width)}  VERSION   VERIFIED WITH")
    for name in sorted(state):
        record = state[name]
        print(f"{name.ljust(width)}  {record['version']:<9} {record.get('verify', '')}")
    print(f"\nInstalled under {TOOLS_DIR} (gitignored).")
    for name, info in WINDOWS_ONLY.items():
        print(f"Not auto-installed: {name} {info['version']} - {info['note']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only",
        action="append",
        metavar="TOOL",
        choices=sorted(ALL_TOOLS),
        help="install just this tool (repeatable)",
    )
    parser.add_argument("--force", action="store_true", help="re-download and re-unpack")
    parser.add_argument("--list", action="store_true", help="print installed versions and exit")
    args = parser.parse_args(argv)

    state = load_state()
    if args.list:
        print_table(state)
        return 0

    plat = current_platform()
    selected = [ALL_TOOLS[name] for name in args.only] if args.only else list(TOOLS)
    print(f"Bootstrapping {len(selected)} tool(s) for {plat} into {TOOLS_DIR}")

    failures: list[str] = []
    for tool in selected:
        try:
            record = install(tool, plat, force=args.force)
            # Reload: install() may have recorded a helper (7-Zip) in the meantime.
            state = load_state()
            state[tool.name] = record
            save_state(state)
        except BootstrapError as exc:
            failures.append(f"{tool.name}: {exc}")
            print(f"    FAILED: {exc}", file=sys.stderr)

    print_table(state)
    if failures:
        print(f"\n{len(failures)} tool(s) failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
