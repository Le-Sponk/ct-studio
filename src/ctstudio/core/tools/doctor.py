"""``ctstudio doctor``: which external tools are usable here, and what to do about the rest.

Discovery is the same the adapters use (configured settings are a P2-T07 concern, so none
here; ``.tools/`` developer copies count, labelled ``source="dev"``). Versions come from the
P2-T02b prober and its cache; only directly launched tools are probed, so no GUI, Wine or
Flatpak process is ever started for a version (ADR-023). Statuses:

* ``found`` — usable; ``version`` is None when the tool has no verified version command.
* ``missing`` — not found; the fix names the official download page.
* ``too_old`` — the probed version is below the registry's ``min_version``.
* ``not_working`` — found, but the version probe failed or timed out.
* ``needs_wine`` — a Windows editor on Linux while Wine itself is missing.
* ``sandboxed`` — only a Flatpak install was found, which the adapters refuse (P2-T05f/g).
* ``not_needed`` — the tool has no role on this operating system (Wine on Windows).

Only ``REQUIRED`` tools decide ``Report.ok``: CT Studio cannot build a track without them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ctstudio.core.tools.discovery import DiscoveryEnvironment, ToolLocation, discover
from ctstudio.core.tools.editors import PREFIX_RECIPES
from ctstudio.core.tools.registry import TOOL_BY_ID, TOOL_SPECS
from ctstudio.core.tools.spec import ToolSpec
from ctstudio.core.tools.versions import VersionCache, VersionResult, probe_versions

Status = Literal[
    "found", "missing", "too_old", "not_working", "needs_wine", "sandboxed", "not_needed"
]
REQUIRED = frozenset({"wszst"})
JSON_FORMAT = 1
_COMPONENT = re.compile(r"(\d+)([a-z]*)")


@dataclass(frozen=True)
class ToolCheck:
    tool_id: str
    name: str
    status: Status
    required: bool
    used_for: str
    version: str | None = None
    path: Path | None = None
    launcher: str | None = None
    source: str | None = None
    fix: str | None = None  # what the user should do; None when nothing is needed
    note: str | None = None  # extra facts that need no action


@dataclass(frozen=True)
class Report:
    platform: str
    tools: tuple[ToolCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status == "found" for check in self.tools if check.required)

    def to_json(self) -> dict[str, object]:
        return {
            "format": JSON_FORMAT,
            "platform": self.platform,
            "ok": self.ok,
            "tools": [_check_json(check) for check in self.tools],
        }


def _check_json(check: ToolCheck) -> dict[str, object]:
    return {
        "id": check.tool_id,
        "name": check.name,
        "status": check.status,
        "required": check.required,
        "version": check.version,
        "path": None if check.path is None else str(check.path),
        "launcher": check.launcher,
        "source": check.source,
        "used_for": check.used_for,
        "fix": check.fix,
        "note": check.note,
    }


def version_key(version: str) -> tuple[tuple[int, str], ...]:
    """Order Wiimm-style versions: ``2.42 < 2.42a < 2.42b < 2.43``, numbers numerically."""
    parts: list[tuple[int, str]] = []
    for component in version.split("."):
        match = _COMPONENT.fullmatch(component)
        parts.append((int(match.group(1)), match.group(2)) if match else (0, component))
    return tuple(parts)


def _platforms_using(spec: ToolSpec) -> str:
    return " and ".join(name.capitalize() for name, exes in spec.exe_names.items() if exes)


def _base(spec: ToolSpec, status: Status, required: frozenset[str], **fields: object) -> ToolCheck:
    return ToolCheck(spec.id, spec.name, status, spec.id in required, spec.used_for, **fields)  # type: ignore[arg-type]


def _located(spec: ToolSpec, location: ToolLocation) -> dict[str, object]:
    return {"path": location.path, "launcher": location.launcher, "source": location.source}


def _from_probe(spec: ToolSpec, result: VersionResult, required: frozenset[str]) -> ToolCheck:
    where = _located(spec, result.location)
    if result.outcome in ("failed", "timeout"):
        fix = (
            f"Reinstall {spec.name} from {spec.download_page}, "
            "or choose a working executable in CT Studio settings."
        )
        return _base(spec, "not_working", required, fix=fix, note=result.detail, **where)
    if result.outcome == "unrecognised":
        note = "Version output not recognised; CT Studio was tested with the pinned version."
        return _base(spec, "found", required, note=note, **where)
    version = result.location.version
    if _too_old(version, spec.min_version):
        fix = f"Update {spec.name} to {spec.min_version} or newer from {spec.download_page}."
        return _base(spec, "too_old", required, version=version, fix=fix, **where)
    return _base(spec, "found", required, version=version, **where)


def _too_old(version: str | None, minimum: str | None) -> bool:
    if version is None or minimum is None:
        return False
    return version_key(version) < version_key(minimum)


def _unprobed(
    spec: ToolSpec, location: ToolLocation, wine: ToolLocation | None, required: frozenset[str]
) -> ToolCheck:
    where = _located(spec, location)
    if location.launcher == "flatpak":
        fix = (
            f"Flatpak {spec.name} cannot be used yet. Install it from {spec.download_page} "
            "or choose a directly installed executable in CT Studio settings."
        )
        return _base(spec, "sandboxed", required, fix=fix, **where)
    if wine is None:
        fix = f"Install Wine from {TOOL_BY_ID['wine'].homepage} to run this Windows editor."
        return _base(spec, "needs_wine", required, fix=fix, **where)
    recipe = PREFIX_RECIPES.get(spec.id)
    note = f"Runs through Wine; it needs a prefix: {recipe}" if recipe else "Runs through Wine."
    return _base(spec, "found", required, note=note, **where)


def diagnose(
    *,
    environment: DiscoveryEnvironment | None = None,
    dev_root: Path | None = None,
    cache: VersionCache | None = None,
    force: bool = False,
    specs: Sequence[ToolSpec] = TOOL_SPECS,
    required: frozenset[str] = REQUIRED,
) -> Report:
    """Check every tool; ``force`` re-runs cached version probes (the "Re-check" action)."""
    env = environment if environment is not None else DiscoveryEnvironment.from_system()
    found = _discover_all(specs, env, dev_root)
    direct = [(spec, where) for spec, where in found.values() if where.launcher == "direct"]
    probed = probe_versions(direct, cache=cache, force=force) if direct else []
    results = {result.tool_id: result for result in probed}
    wine = discover(TOOL_BY_ID["wine"], environment=env) if env.platform == "linux" else None
    checks = [
        _classify(spec, env.platform, found.get(spec.id), results, wine, required) for spec in specs
    ]
    return Report(env.platform, tuple(checks))


def _discover_all(
    specs: Sequence[ToolSpec], env: DiscoveryEnvironment, dev_root: Path | None
) -> dict[str, tuple[ToolSpec, ToolLocation]]:
    found: dict[str, tuple[ToolSpec, ToolLocation]] = {}
    for spec in specs:
        if not spec.exe_names.get(env.platform):
            continue
        location = discover(spec, environment=env, include_dev=True, dev_root=dev_root)
        if location is not None:
            found[spec.id] = (spec, location)
    return found


def _classify(
    spec: ToolSpec,
    platform: str,
    entry: tuple[ToolSpec, ToolLocation] | None,
    results: dict[str, VersionResult],
    wine: ToolLocation | None,
    required: frozenset[str],
) -> ToolCheck:
    if not spec.exe_names.get(platform):
        note = f"Only used on {_platforms_using(spec)}."
        return _base(spec, "not_needed", required, note=note)
    if entry is None:
        fix = f"Install {spec.name} from {spec.download_page}."
        return _base(spec, "missing", required, fix=fix)
    if spec.id in results:
        return _from_probe(spec, results[spec.id], required)
    return _unprobed(spec, entry[1], wine, required)
