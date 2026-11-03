"""After a build: record each track part a step made in ``.ctstudio/state.json`` (P4-T03b).

The record is what status (``components.status``) compares against: the part's settings key,
the files the step wrote, and the user's files the part was made from. Those are the
inputs of the step and of every step it waits for, directly or not, minus files some step
writes: the KCL step reads the Blender export, but the user's file behind it is the
``.blend``. A skipped step is recorded only when state.json has no record of its part yet
(it was deleted), so a record always describes files that are really there.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ctstudio.core.build.graph import BuildGraph
from ctstudio.core.build.node import Node
from ctstudio.core.components import state
from ctstudio.core.components.status import settings_key
from ctstudio.core.project.manifest import Manifest


class PartRecorder:
    def __init__(self, graph: BuildGraph, manifest: Manifest) -> None:
        self.graph = graph
        self.manifest = manifest
        self._known = state.load_state(graph.root)
        self._made: dict[str, state.ComponentRecord] = {}

    def wants(self, node: Node, *, ran: bool) -> bool:
        part = node.component
        return part is not None and (ran or part not in self._known.components)

    def record(self, node: Node) -> None:
        """Called by the build's own thread after ``node`` ran (or was skipped)."""
        part = node.component
        if part is None:
            raise ValueError(f"{node.id} makes no track part")
        root = self.graph.root
        outputs = _files(node.outputs)
        settings = settings_key(self.manifest, part)
        self._made[part] = state.record(root, settings, outputs, self._sources(node))

    def save(self) -> None:
        if not self._made:
            return
        latest = state.load_state(self.graph.root).components  # another build may have saved
        merged = {**latest, **self._made}
        state.save_state(self.graph.root, state.ProjectState(merged))

    def _sources(self, node: Node) -> list[Path]:
        steps = self.graph.subgraph([node.id]).nodes
        written = [path.resolve() for step in self.graph.nodes for path in step.outputs]
        paths = (path for step in steps for path in step.inputs)
        users = [path for path in paths if not _inside_any(path.resolve(), written)]
        return _files(users)


def _inside_any(path: Path, folders: list[Path]) -> bool:
    return any(path == folder or path.is_relative_to(folder) for folder in folders)


def _files(paths: Iterable[Path]) -> list[Path]:
    """Files as themselves, folders as every file in them; missing paths are left out."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        elif path.is_file():
            found.append(path)
    return found
