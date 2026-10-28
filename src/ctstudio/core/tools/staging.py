"""Shared plumbing for adapters that run a tool on staged copies (rszst, ABMatt).

Inputs are copied into a private temp folder, the tool runs there, and checked outputs
are copied to their destination: a user file is replaced only after the tool succeeded,
and only with a timestamped backup (``fsutil.replace_with_backup``).
"""

from __future__ import annotations

import re
import tempfile
from collections import deque
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.fsutil import replace_with_backup
from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.process import CancelToken, Stream, run
from ctstudio.core.tools.registry import TOOL_BY_ID

# Only <image> sources name files; <surface><init_from> names an image id.
_IMAGE_FILE = re.compile(rb"<image\b[^>]*>\s*<init_from>\s*([^<]*?)\s*</init_from>")
_KEPT_LINES = 2000


@dataclass(frozen=True)
class ToolRun:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def details(self) -> str:
        """Both streams, for a typed error's private diagnostics."""
        return "\n".join(part for part in (self.stderr, self.stdout) if part)


def executable_for(tool: str, configured: Path | None, hint: str) -> Path:
    """The configured executable, else the discovered (including dev) one."""
    if configured is not None:
        return configured.resolve()
    location = discover(TOOL_BY_ID[tool], include_dev=True)
    if location is None:
        raise ToolNotFound(tool, hint=hint)
    return location.path


@contextmanager
def stage(tool: str) -> Generator[Path]:
    with tempfile.TemporaryDirectory(prefix=f"ctstudio-{tool}-") as folder:
        yield Path(folder)


def run_collecting(
    cmd: Sequence[str | Path],
    cwd: Path,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float,
    cancel: CancelToken | None,
) -> ToolRun:
    """Run to completion, keeping the last ``_KEPT_LINES`` lines of each stream."""
    lines: dict[Stream, deque[str]] = {
        "stdout": deque(maxlen=_KEPT_LINES),
        "stderr": deque(maxlen=_KEPT_LINES),
    }

    def collect(stream: Stream, line: str) -> None:
        lines[stream].append(line)

    result = run(
        cmd, cwd=cwd, env=env, timeout=timeout, cancel=cancel, on_line=collect, check=False
    )
    return ToolRun(result.exit_code, "\n".join(lines["stdout"]), "\n".join(lines["stderr"]))


def occupied(destinations: Sequence[Path], *, overwrite: bool) -> Path | None:
    """The first destination that exists when overwriting was not chosen."""
    if overwrite:
        return None
    return next((path for path in destinations if path.exists()), None)


def deliver(destination: Path, data: bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    replace_with_backup(destination, data)
    return destination


def collada_images(data: bytes) -> list[str] | None:
    """Texture file references of a COLLADA document, or None if it is not COLLADA."""
    if b"<COLLADA" not in data[:4096]:
        return None
    return sorted({match.decode("utf-8", "replace") for match in _IMAGE_FILE.findall(data)})
