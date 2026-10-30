"""Carry out an ``rszst`` setup route into CT Studio's own folder (P2-T06b).

``download_windows`` fetches the pinned official release (user-initiated only, ADR-004),
checks its size and SHA-256 while streaming, refuses archive members that would land outside
the folder, and confirms ``rszst --version`` prints the pinned banner. ``build_linux`` runs
the pinned S3a recipe through ``process.run`` (cancellable, every line in ``build.log``).
Both write ``setup.json`` last; any failure leaves no record, so discovery never picks up a
half-finished copy. A failed build keeps its folder for the log; a failed download keeps
nothing.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import IO, Protocol

from ctstudio.core.errors import Cancelled, CTStudioError, ToolFailed, ToolTimedOut
from ctstudio.core.tools import process
from ctstudio.core.tools.process import CancelToken, LineCallback, RunResult
from ctstudio.core.tools.rszst_setup import (
    BUILD_PACKAGES,
    EXPECTED_TOOLCHAIN,
    PIN,
    RELEASES_PAGE,
    Preflight,
    SetupRecord,
    Step,
    build_steps,
    managed_executable,
    read_record,
    write_record,
)

CHUNK = 256 * 1024
BANNER_TIMEOUT = 30.0
Opener = Callable[[str], IO[bytes]]
Progress = Callable[[int, int], None]
StepCallback = Callable[[int, int, Step], None]


Which = Callable[..., str | None]  # ``shutil.which``: called as which(name, path=PATH)


class Runner(Protocol):
    def __call__(
        self,
        cmd: Sequence[str | Path],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        on_line: LineCallback | None = None,
        cancel: CancelToken | None = None,
        log_path: Path | None = None,
        check: bool = True,
    ) -> RunResult: ...


class SetupFailed(CTStudioError):
    """Getting rszst did not finish; nothing half-done is used."""


def _open_url(url: str) -> IO[bytes]:
    return urllib.request.urlopen(url, timeout=60)  # noqa: S310 - fixed https release URL


def read_banner(exe: Path, args: tuple[str, ...] = ("--version",)) -> str:
    """``rszst --version`` output; rszst exits -1 even on success, so the code is ignored."""
    result = process.run([exe, *args], cwd=exe.parent, timeout=BANNER_TIMEOUT, check=False)
    return f"{result.stdout_tail}\n{result.stderr_tail}"


def _check_banner(exe: Path, banner: Callable[[Path], str]) -> None:
    text = banner(exe)
    if PIN.banner not in text:
        raise SetupFailed(
            f"The installed rszst is not RiiStudio {PIN.version}.",
            hint="Nothing was installed. Try again, or install RiiStudio yourself.",
            details=text[-2000:],
        )


# --- Windows -------------------------------------------------------------------------------------


def download_windows(
    root: Path,
    *,
    opener: Opener = _open_url,
    banner: Callable[[Path], str] = read_banner,
    cancel: CancelToken | None = None,
    on_progress: Progress | None = None,
) -> Path:
    """Fetch, check and unpack the pinned Windows release into ``root``; return ``rszst.exe``."""
    exe = managed_executable(root, "windows")
    if read_record(root) is not None:
        return exe
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root.parent, prefix=f".{root.name}-") as work:
        stage = Path(work)
        archive = stage / "release.zip"
        _fetch(archive, opener, cancel, on_progress)
        unpacked = stage / "unpacked"
        _unpack(archive, unpacked)
        _check_banner(managed_executable(unpacked, "windows"), banner)
        write_record(unpacked, SetupRecord("download", PIN.version, "rszst.exe"))
        if root.exists():
            shutil.rmtree(root)
        unpacked.replace(root)
    return exe


def _fetch(
    target: Path, opener: Opener, cancel: CancelToken | None, progress: Progress | None
) -> None:
    digest, done, total = hashlib.sha256(), 0, PIN.windows_zip_bytes
    try:
        with opener(PIN.windows_zip_url) as response, target.open("wb") as sink:
            while chunk := response.read(CHUNK):
                if cancel is not None and cancel.cancelled:
                    raise Cancelled("Downloading RiiStudio")
                done += len(chunk)
                if done > total:
                    raise _bad_download(f"The download is larger than the pinned {total} bytes.")
                digest.update(chunk)
                sink.write(chunk)
                if progress is not None:
                    progress(done, total)
    except OSError as exc:
        raise SetupFailed(
            "RiiStudio could not be downloaded.",
            hint=f"Check the internet connection, or download it yourself from {RELEASES_PAGE}.",
            details=str(exc),
        ) from exc
    if done != total or digest.hexdigest() != PIN.windows_zip_sha256:
        raise _bad_download(f"got {done} bytes, SHA-256 {digest.hexdigest()}")


def _bad_download(details: str) -> SetupFailed:
    return SetupFailed(
        "The RiiStudio download did not match the pinned release.",
        hint=f"Nothing was installed. Try again later, or download it from {RELEASES_PAGE}.",
        details=details,
    )


def _unsafe(name: str) -> bool:
    posix, windows = PurePosixPath(name), PureWindowsPath(name)
    return posix.is_absolute() or bool(windows.drive) or ".." in windows.parts


def _unpack(archive: Path, into: Path) -> None:
    with zipfile.ZipFile(archive) as release:
        names = release.namelist()
        bad = [name for name in names if _unsafe(name)]
        if bad:
            raise SetupFailed(
                "The RiiStudio archive contains unsafe file names.",
                hint="Nothing was installed.",
                details=", ".join(bad[:5]),
            )
        if "rszst.exe" not in names:
            raise SetupFailed(
                "The RiiStudio archive has no rszst.exe.", hint="Nothing was installed."
            )
        into.mkdir()
        release.extractall(into)  # every member name was checked above


# --- Linux ---------------------------------------------------------------------------------------


def build_linux(
    root: Path,
    *,
    jobs: int,
    preflight_result: Preflight,
    runner: Runner = process.run,
    banner: Callable[[Path], str] = read_banner,
    cancel: CancelToken | None = None,
    on_step: StepCallback | None = None,
    on_line: LineCallback | None = None,
    which: Which = shutil.which,
) -> Path:
    """Build the pinned source into ``root`` (about an hour); return the ``rszst`` path."""
    exe = managed_executable(root, "linux")
    if read_record(root) is not None:
        return exe
    if not preflight_result.ok:
        lines = preflight_result.lines()
        raise SetupFailed(
            "This machine is not ready to build RiiStudio: " + "; ".join(lines[:3]),
            hint="\n".join(lines[3:]) or "Free some disk space, then try again.",
        )
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    toolchain = preflight_result.toolchain or EXPECTED_TOOLCHAIN
    steps = build_steps(root, jobs=jobs, toolchain=toolchain)
    for number, step in enumerate(steps, start=1):
        if on_step is not None:
            on_step(number, len(steps), step)
        _run_step(_resolved(step, which), root, runner, cancel, on_line)
    if not exe.is_file():
        raise SetupFailed("The build finished but produced no rszst.", hint=_log_hint(root))
    _check_banner(exe, banner)
    write_record(root, SetupRecord("build", PIN.version, "build/source/cli/rszst"))
    return exe


def _resolved(step: Step, which: Which) -> Step:
    """The step with its program as an absolute path (the runner refuses bare names).

    Searched on the step's own PATH when it sets one (the versioned Rust folder first).
    """
    program = which(step.argv[0], path=step.env.get("PATH", os.environ.get("PATH", "")))
    if program is None or not Path(program).is_absolute():
        raise SetupFailed(
            f"Building RiiStudio needs “{step.argv[0]}”, which was not found.",
            hint=f"Install it with:\n  sudo apt install -y {' '.join(BUILD_PACKAGES)}",
        )
    return replace(step, argv=(program, *step.argv[1:]))


def _run_step(
    step: Step, root: Path, runner: Runner, cancel: CancelToken | None, on_line: LineCallback | None
) -> None:
    try:
        runner(
            step.argv,
            cwd=step.cwd,
            env=step.env,
            timeout=step.timeout,
            cancel=cancel,
            on_line=on_line if on_line is not None else _ignore,
            log_path=root / "build.log",
            check=True,
        )
    except (ToolFailed, ToolTimedOut) as exc:
        found = _error_lines(root / "build.log")
        shown = (
            "\n".join(["What went wrong:", *(f"  {line}" for line in found), ""]) if found else ""
        )
        raise SetupFailed(
            f"Building RiiStudio failed at step “{step.name}”.",
            hint=shown + _log_hint(root),
            details=exc.details,
        ) from exc


# Lines that say why a build failed: compiler/linker/CMake errors and cargo's "Caused by"
# chain, e.g. "invalid version 0 on git_proxy_options". Parallel jobs bury them mid-log.
_ERROR = re.compile(
    r"error(\[E\d+\])?:|fatal error|undefined reference|ld returned|CMake Error|"
    r"git_proxy_options|not found$|No such file"
)
_SHOWN_ERRORS = 12


def _error_lines(log: Path) -> list[str]:
    """The first few error lines of this run's log (without the [out]/[err] tags)."""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    run = text[text.rfind("# run ") :] if "# run " in text else text
    lines = (re.sub(r"^\[(out|err)\] ", "", line).strip() for line in run.splitlines())
    hits = [line for line in lines if _ERROR.search(line) and not line.startswith("warning")]
    return list(dict.fromkeys(hits))[:_SHOWN_ERRORS]


def _ignore(_stream: str, _line: str) -> None:
    return None


def _log_hint(root: Path) -> str:
    return f"The full output is in {root / 'build.log'}."
