"""Which tools are there to use, without starting any of them (P3-T07).

A part's status needs only "is this tool there", not its version, so this is discovery
alone. ``doctor`` is the place for versions and fixes.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools.discovery import DiscoveryEnvironment, Launcher, discover
from ctstudio.core.tools.registry import TOOL_SPECS
from ctstudio.core.tools.spec import ToolSpec

_USABLE: frozenset[Launcher] = frozenset({"direct"})  # a Flatpak Blender is not usable yet
_USABLE_WITH_WINE: frozenset[Launcher] = frozenset({"direct", "wine"})


def available_tools(
    *,
    configured: Mapping[str, Path] | None = None,
    environment: DiscoveryEnvironment | None = None,
    dev_root: Path | None = None,
) -> frozenset[str]:
    """Ids of the tools that are there to use.

    A path set in CT Studio (``configured``) that is not a program counts as missing; it is
    never silently replaced by another copy. A Flatpak Blender is not usable yet, and a
    program that runs through Wine needs Wine too.
    """
    env = environment if environment is not None else DiscoveryEnvironment.from_system()
    launchers = _launchers(configured or {}, env, dev_root)
    usable = _USABLE_WITH_WINE if "wine" in launchers else _USABLE
    return frozenset(tool for tool, launcher in launchers.items() if launcher in usable)


def _launchers(
    configured: Mapping[str, Path], env: DiscoveryEnvironment, dev_root: Path | None
) -> dict[str, Launcher]:
    launchers: dict[str, Launcher] = {}
    for spec in TOOL_SPECS:
        launcher = _launcher(spec, configured.get(spec.id), env, dev_root)
        if launcher is not None:
            launchers[spec.id] = launcher
    return launchers


def _launcher(
    spec: ToolSpec, configured: Path | None, env: DiscoveryEnvironment, dev_root: Path | None
) -> Launcher | None:
    """How the tool would be started, or None when this OS has no copy to start."""
    if not spec.exe_names.get(env.platform):
        return None
    try:
        location = discover(
            spec, configured=configured, environment=env, include_dev=True, dev_root=dev_root
        )
    except ToolNotFound:
        return None
    return None if location is None else location.launcher
