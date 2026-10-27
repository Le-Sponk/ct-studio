"""Read installed tool versions with documented commands, cached by executable identity.

Only a spec with both ``version_args`` and ``version_regex`` is probed; GUI editors and
tools without a verified command stay ``None`` and are never started (ADR-023). Probes run
concurrently through ``core/tools/process.py``. Results persist in a small JSON file in the
user config folder, keyed by tool id + resolved path + size + mtime (Flatpak: app id), so a
reinstalled or updated tool is probed again. Failures are reported, never cached.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from ctstudio.core import platform as ct_platform
from ctstudio.core.errors import CTStudioError, ToolTimedOut
from ctstudio.core.fsutil import atomic_write_text
from ctstudio.core.logging import get_logger
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import run
from ctstudio.core.tools.spec import ToolSpec

Outcome = Literal["probed", "cached", "unprobed", "unrecognised", "timeout", "failed"]

PROBE_TIMEOUT_SECONDS = 10.0
MAX_PARALLEL_PROBES = 8
CACHE_FORMAT = 1
_LOG = get_logger(__name__)


@dataclass(frozen=True)
class VersionResult:
    tool_id: str
    location: ToolLocation  # ``version`` is set only for outcome "probed" or "cached"
    outcome: Outcome
    detail: str | None = None  # why there is no version; safe to show the user


def default_cache_path() -> Path:
    return ct_platform.user_directories().config / "tool-versions.json"


def parse_version(spec: ToolSpec, output: str) -> str | None:
    """Return the first capture group of the spec's verified regex, or None."""
    if spec.version_regex is None:
        return None
    match = re.search(spec.version_regex, output)
    return match.group(1) if match else None


def version_argv(spec: ToolSpec, location: ToolLocation) -> list[str] | None:
    """The documented probe command, or None when probing would guess or start a GUI."""
    if not spec.version_args or spec.version_regex is None:
        return None
    if location.launcher == "direct":
        return [str(location.path), *spec.version_args]
    if location.launcher == "flatpak" and location.app_id:
        return [str(location.path), "run", location.app_id, *spec.version_args]
    return None  # Wine: no verified command, and starting Wine is not a version check


class VersionCache:
    """A JSON map of executable identity → version; unreadable files start empty."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_cache_path()
        self.save_error: CTStudioError | None = None
        self._lock = threading.Lock()
        self._entries = self._load()

    def key(self, tool_id: str, location: ToolLocation) -> str | None:
        """Identity of what would answer the probe; None if the file cannot be read."""
        if location.launcher == "flatpak":
            return f"{tool_id}|flatpak|{location.path}|{location.app_id}"
        try:
            stat = location.path.stat()
        except OSError:
            return None
        return f"{tool_id}|{location.path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._entries.get(key)

    def put(self, key: str, version: str) -> None:
        with self._lock:
            self._entries[key] = version

    def save(self) -> None:
        """Persist atomically; a failure is kept in ``save_error`` and logged, not raised."""
        with self._lock:
            entries = {key: {"version": version} for key, version in self._entries.items()}
        text = json.dumps({"format": CACHE_FORMAT, "entries": entries}, indent=1)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.path, text + "\n")
        except OSError as exc:
            self.save_error = CTStudioError(
                "Could not save the tool version cache.",
                hint="Check that the CT Studio settings folder is writable.",
                details=f"path={self.path}; error={exc}",
            )
        except CTStudioError as exc:
            self.save_error = exc
        else:
            self.save_error = None
            return
        _LOG.warning("tool version cache not saved: %s", self.save_error.details)

    def _load(self) -> dict[str, str]:
        try:
            data: object = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        document = cast(dict[str, object], data)
        entries = document.get("entries")
        if document.get("format") != CACHE_FORMAT or not isinstance(entries, dict):
            return {}
        loaded: dict[str, str] = {}
        for key, entry in cast(dict[object, object], entries).items():
            version = (
                cast(dict[str, object], entry).get("version") if isinstance(entry, dict) else None
            )
            if isinstance(key, str) and isinstance(version, str):
                loaded[key] = version
        return loaded


def probe_versions(
    items: Sequence[tuple[ToolSpec, ToolLocation]],
    *,
    cache: VersionCache | None = None,
    force: bool = False,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> list[VersionResult]:
    """Probe each located tool concurrently; results keep the order of ``items``.

    ``force`` ignores cached versions (the "Re-check" action) but still stores new ones.
    """
    store = cache if cache is not None else VersionCache()

    def probe(item: tuple[ToolSpec, ToolLocation]) -> VersionResult:
        return _probe(item[0], item[1], store, force, timeout)

    workers = max(1, min(MAX_PARALLEL_PROBES, len(items)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="version-probe") as pool:
        results = list(pool.map(probe, items))
    if any(result.outcome == "probed" for result in results):
        store.save()
    return results


def _probe(
    spec: ToolSpec, location: ToolLocation, cache: VersionCache, force: bool, timeout: float
) -> VersionResult:
    argv = version_argv(spec, location)
    if argv is None:
        return VersionResult(spec.id, location, "unprobed", "No verified version command.")
    if not location.path.is_file():
        detail = f"{location.path.name} was not found; it may have been moved or uninstalled."
        return VersionResult(spec.id, location, "failed", detail)
    key = cache.key(spec.id, location)
    cached = cache.get(key) if key is not None and not force else None
    if cached is not None:
        return VersionResult(spec.id, replace(location, version=cached), "cached")
    result = _run_probe(spec, location, argv, timeout)
    if result.outcome == "probed" and key is not None and result.location.version:
        cache.put(key, result.location.version)
    return result


def _run_probe(
    spec: ToolSpec, location: ToolLocation, argv: list[str], timeout: float
) -> VersionResult:
    try:
        # Exit status is ignored: rszst prints its banner and exits -1 (TOOLS.md).
        result = run(argv, cwd=location.path.parent, timeout=timeout, check=False)
    except ToolTimedOut as exc:
        return VersionResult(spec.id, location, "timeout", exc.user_message)
    except CTStudioError as exc:  # ToolNotFound, an unusable working folder, ...
        return VersionResult(spec.id, location, "failed", exc.user_message)
    output = "\n".join(text for text in (result.stdout_tail, result.stderr_tail) if text)
    version = parse_version(spec, output)
    if version is None:
        return VersionResult(spec.id, location, "unrecognised", output[-500:] or None)
    return VersionResult(spec.id, replace(location, version=version), "probed")
