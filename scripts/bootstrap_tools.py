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

from tool_catalogue import (  # sys.path is extended just above; E402 is off in ruff.toml
    ALL_TOOLS,
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
        candidates = [c.with_suffix(".exe") for c in candidates] + candidates
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BootstrapError(f"{name} not found in {tool_dir}")


def run_verify(tool: Tool, tool_dir: Path) -> str:
    """Run the tool's verify command and return its first output line."""
    if tool.verify is None:
        return "(no verify command)"
    argv_names, expected = tool.verify
    argv = [str(executable_path(tool_dir, argv_names[0])), *argv_names[1:]]
    try:
        proc = subprocess.run(  # noqa: S603  (argv list, no shell)
            argv,
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(
            f"{tool.name}: {argv_names[0]} timed out after {exc.timeout}s"
        ) from exc
    except OSError as exc:
        raise BootstrapError(f"{tool.name}: could not run {argv[0]}: {exc}") from exc

    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        tail = "\n".join(output.splitlines()[-5:])
        raise BootstrapError(
            f"{tool.name}: {' '.join(argv_names)} exited {proc.returncode}.\n{tail}"
        )
    if expected.lower() not in output.lower():
        tail = "\n".join(output.splitlines()[:5])
        raise BootstrapError(
            f"{tool.name}: expected {expected!r} in the output of "
            f"{' '.join(argv_names)}, got:\n{tail}"
        )
    # Report the first line that carries information: ABMatt opens with a rule of "=".
    lines = [ln.strip() for ln in output.splitlines() if ln.strip().strip("=")]
    return lines[0] if lines else "(no output)"


def pick_download(tool: Tool, plat: str) -> Download:
    if plat in tool.downloads:
        return tool.downloads[plat]
    raise BootstrapError(
        f"{tool.name} has no {plat} build. Supported: {', '.join(sorted(tool.downloads))}. "
        "See docs/reference/TOOLS.md for the alternative (Wine or manual install)."
    )


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
            f"{tool.name}: checksum mismatch for {spec.archive}.\n"
            f"  expected {spec.sha256}\n  got      {digest}\n"
            "The download was deleted. If the publisher re-released this version, update "
            "scripts/tool_catalogue.py and docs/reference/TOOLS.md with the new checksum."
        )
    if spec.sha256:
        print("    sha256 matches the publisher's checksum")
    else:
        print(f"    sha256 (unpublished upstream, recorded): {digest}")

    unpack(archive, tool_dir, spec.strip_prefix)
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
            state[tool.name] = install(tool, plat, force=args.force)
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
