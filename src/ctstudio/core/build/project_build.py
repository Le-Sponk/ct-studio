"""Build a whole project: the steps, the tools they use, then the run (P4-T07a).

Shared by ``ctstudio build`` and the Build page. ``plan_build`` turns the manifest into the
build's steps (a stage step per part in manual mode, then assemble and validate) and finds
every tool those steps use the way doctor does: a path set in CT Studio wins and is never
silently replaced, then PATH, the usual folders and a checkout's ``.tools/``. A missing or
unusable tool stops the build before anything runs, naming it. ``only`` keeps one part's
steps (the other parts need not be buildable) and does not pack the track.
``build_project`` runs a plan; ``force`` forgets what was built before, for the steps in the
plan only.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ctstudio.core.build.assemble import assemble_step
from ctstudio.core.build.cache import BuildCache
from ctstudio.core.build.events import BuildEvent, BuildSummary
from ctstudio.core.build.graph import BuildGraph, MakePart, from_manifest
from ctstudio.core.build.node import Node, Profile
from ctstudio.core.build.runner import BuildRequest, run_build
from ctstudio.core.build.stage import manual_parts
from ctstudio.core.build.validate import validate_step
from ctstudio.core.components.registry import COMPONENT_BY_ID, COMPONENTS, ComponentSpec
from ctstudio.core.errors import BuildGraphError, ProjectError, ToolNotFound
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.project.project import Project
from ctstudio.core.tools.discovery import ToolLocation, default_dev_root, discover
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.versions import probe_versions

_TOOL_HINT = (
    "Install {product}, or set its path on the Tools page; `ctstudio doctor` shows what is missing."
)
_PRODUCT = {"wszst": "Wiimms SZS Tools", "wkmpt": "Wiimms SZS Tools"}


@dataclass(frozen=True)
class BuildPlan:
    graph: BuildGraph
    request: BuildRequest


def check_buildable(project: Project) -> None:
    """ProjectError when ``project`` is open read-only: someone else may be building it."""
    if project.read_only:
        raise ProjectError(
            "This project is in use by CT Studio or another build, so it was not built.",
            hint=f"{project.read_only_reason}. Wait for that build to finish or close "
            "the project there, then build again.",
        )


def plan_build(
    root: Path,
    manifest: Manifest,
    profile: Profile,
    *,
    only: str | None = None,
    configured: Mapping[str, Path] | None = None,
    library: Path | None = None,
) -> BuildPlan:
    """The steps and tools of one build; BuildGraphError / ToolNotFound when it cannot run."""
    finish = (
        assemble_step(root, manifest, profile, library),
        validate_step(root, manifest, profile),
    )
    if only is None:
        graph = from_manifest(root, manifest, manual_parts(root, manifest), finish)
    else:  # just that part: the others need not be buildable (an auto course model, say)
        part = _part(only)
        graph = from_manifest(root, manifest, _just(part, manual_parts(root, manifest)))
        graph = graph.subgraph([f"stage:{part}"])
    needed = list(dict.fromkeys(tool for node in graph.nodes for tool in node.tools))
    tools = _tools(needed, configured or {})
    return BuildPlan(graph, BuildRequest(manifest, profile, tools, _versions(tools)))


def build_project(
    plan: BuildPlan,
    on_event: Callable[[BuildEvent], None],
    *,
    cancel: CancelToken,
    force: bool = False,
) -> BuildSummary:
    cache = BuildCache.load(plan.graph.root)
    if force:
        for node in plan.graph.nodes:
            cache.invalidate(node.id)
    return run_build(plan.graph, cache, plan.request, on_event, cancel=cancel)


def _just(part: str, make: MakePart) -> MakePart:
    """``make`` for ``part``, and no steps for every other part."""

    def just(spec: ComponentSpec, mode: str) -> Iterable[Node] | None:
        return make(spec, mode) if spec.id == part else []

    return just


def _part(only: str) -> str:
    """The part id ``only`` names when that part has a stage step, else BuildGraphError."""
    built = [spec.id for spec in COMPONENTS if spec.outputs]
    if only in built:
        return only
    if only in COMPONENT_BY_ID:
        message = f"{COMPONENT_BY_ID[only].name} is not built on its own."
    else:
        message = f"There is no part called {only!r}."
        close = difflib.get_close_matches(only, built, n=3)
        if close:
            message += f" Did you mean {' or '.join(close)}?"
    raise BuildGraphError(message, hint=f"Choose one of: {', '.join(built)}.")


def _tools(needed: list[str], configured: Mapping[str, Path]) -> dict[str, ToolLocation]:
    found: dict[str, ToolLocation] = {}
    for tool in needed:
        spec = TOOL_BY_ID[tool]
        where = discover(
            spec, configured=configured.get(tool), include_dev=True, dev_root=default_dev_root()
        )
        hint = _TOOL_HINT.format(product=_PRODUCT.get(tool, spec.name))
        if where is None:
            raise ToolNotFound(spec.name, hint=hint)
        if where.launcher != "direct":
            problem = "was found, but only runs through Wine, which builds cannot use yet"
            raise ToolNotFound(spec.name, hint=hint, problem=problem)
        found[tool] = where
    return found


def _versions(tools: Mapping[str, ToolLocation]) -> dict[str, str | None]:
    """Each tool's version for the cache key (a cached probe is reused); None when unknown."""
    items = [(TOOL_BY_ID[tool], where) for tool, where in tools.items()]
    results = probe_versions(items) if items else []
    return {result.tool_id: result.location.version for result in results}
