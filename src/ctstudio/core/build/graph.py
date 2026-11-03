"""The build steps of a project, in an order they can run (ARCHITECTURE §7).

Steps are linked through files: a step waits for every step that writes a file it reads,
including a file inside an output folder and an input folder that holds an output. The order
puts each step after the steps it waits for and otherwise keeps the order given, so a project
always builds the same way. Steps that wait for each other are reported as a cycle naming
each step; ``subgraph`` gives the steps needed to rebuild just some of them.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from ctstudio.core.build.node import Node
from ctstudio.core.components.registry import COMPONENTS, ComponentSpec
from ctstudio.core.errors import BuildGraphError
from ctstudio.core.project.manifest import Manifest

MakePart = Callable[[ComponentSpec, str], Iterable[Node] | None]
_CYCLE_HINT = (
    "Choose your own files from outside the build/ and .ctstudio/ folders, then build again."
)


class BuildGraph:
    def __init__(self, root: Path, nodes: Iterable[Node]) -> None:
        self.root = root
        given = _unique(nodes)
        _check_outputs(root.resolve(), given)
        _check_components(given)
        needs = _links(given)
        self.nodes: tuple[Node, ...] = _ordered(given, needs)
        position = {node.id: i for i, node in enumerate(self.nodes)}
        self._needs = {
            node.id: tuple(sorted(needs[node.id], key=position.__getitem__)) for node in self.nodes
        }

    def needs(self, node_id: str) -> tuple[str, ...]:
        """The steps ``node_id`` waits for, in build order (``KeyError`` when unknown)."""
        return self._needs[node_id]

    def subgraph(self, targets: Iterable[str]) -> BuildGraph:
        """Just ``targets`` and every step they wait for, directly or not."""
        wanted: set[str] = set()
        pending = [self._known(target) for target in targets]
        while pending:
            node_id = pending.pop()
            if node_id not in wanted:
                wanted.add(node_id)
                pending.extend(self._needs[node_id])
        return BuildGraph(self.root, [node for node in self.nodes if node.id in wanted])

    def _known(self, node_id: str) -> str:
        if node_id in self._needs:
            return node_id
        message = f"There is no build step {node_id!r}."
        close = difflib.get_close_matches(node_id, list(self._needs), n=3)
        if close:
            message += f" Did you mean {' or '.join(close)}?"
        steps = ", ".join(node.id for node in self.nodes)
        raise BuildGraphError(message, hint=f"The steps are: {steps}.")


def from_manifest(
    root: Path, manifest: Manifest, make_part: MakePart, finish: Iterable[Node] = ()
) -> BuildGraph:
    """Every part that puts a file into the track, made the way its mode says, then ``finish``.

    ``make_part(spec, mode)`` returns the part's steps, or None when CT Studio cannot make it
    that way yet. A step several parts share (one Blender export) is given by each and kept once.
    """
    nodes: list[Node] = []
    for spec in COMPONENTS:
        if not spec.outputs:
            continue
        mode = str(getattr(manifest.components, spec.id).mode)
        made = make_part(spec, mode)
        if made is None:
            raise _cannot_make(spec, mode)
        nodes.extend(made)
    return BuildGraph(root, [*nodes, *finish])


def _cannot_make(spec: ComponentSpec, mode: str) -> BuildGraphError:
    others = [other for other in spec.modes if other != mode]
    hint = (
        f"Set its mode to {' or '.join(others)} in ctstudio.toml."
        if others
        else "A newer CT Studio may be able to; check for an update."
    )
    return BuildGraphError(f"CT Studio cannot make the {spec.name} in {mode} mode yet.", hint=hint)


def _unique(nodes: Iterable[Node]) -> list[Node]:
    kept: dict[str, Node] = {}
    for node in nodes:
        first = kept.setdefault(node.id, node)
        if first != node:
            raise ValueError(f"two different build steps are called {node.id!r}")
    return list(kept.values())


def _overlap(a: Path, b: Path) -> bool:
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _resolved(paths: Iterable[Path]) -> list[Path]:
    return [path.resolve() for path in paths]


def _check_outputs(root: Path, nodes: Sequence[Node]) -> None:
    written: list[tuple[Path, str]] = []
    for node in nodes:
        for path in _resolved(node.outputs):
            if not path.is_relative_to(root):
                raise ValueError(f"{node.id!r} writes {path}, outside the project")
            for other, writer in written:
                if _overlap(path, other):
                    deeper = max(path, other, key=lambda p: len(p.parts))
                    raise ValueError(f"{writer!r} and {node.id!r} both write {deeper}")
            written.append((path, node.id))


def _check_components(nodes: Sequence[Node]) -> None:
    makers: dict[str, str] = {}
    for node in nodes:
        if node.component is None:
            continue
        first = makers.setdefault(node.component, node.id)
        if first != node.id:
            raise ValueError(f"{first!r} and {node.id!r} both make the {node.component} part")


def _links(nodes: Sequence[Node]) -> dict[str, set[str]]:
    """For each step, the steps that write something it reads (itself included)."""
    outputs = {node.id: _resolved(node.outputs) for node in nodes}
    needs: dict[str, set[str]] = {}
    for node in nodes:
        reads = _resolved(node.inputs)
        needs[node.id] = {
            writer
            for writer, made in outputs.items()
            if any(_overlap(r, m) for r in reads for m in made)
        }
    return needs


def _ordered(nodes: Sequence[Node], needs: dict[str, set[str]]) -> tuple[Node, ...]:
    """Dependencies first; among the steps that are ready, the earliest given goes first."""
    done: set[str] = set()
    order: list[Node] = []
    while len(order) < len(nodes):
        ready = next((n for n in nodes if n.id not in done and needs[n.id] <= done), None)
        if ready is None:
            raise _cycle([n.id for n in nodes if n.id not in done], needs)
        done.add(ready.id)
        order.append(ready)
    return tuple(order)


def _cycle(stuck: list[str], needs: dict[str, set[str]]) -> BuildGraphError:
    """Walk from the first stuck step through stuck steps it waits for until one repeats."""
    rank = {node_id: i for i, node_id in enumerate(stuck)}
    path = [stuck[0]]
    while path.count(path[-1]) == 1:
        path.append(min(needs[path[-1]] & rank.keys(), key=rank.__getitem__))
    loop = path[path.index(path[-1]) : -1]
    start = loop.index(min(loop, key=rank.__getitem__))
    loop = loop[start:] + loop[:start]
    steps = " → ".join([*loop, loop[0]])
    return BuildGraphError(
        "These build steps wait for each other's files, so none can go first:"
        f" {steps} (each waits for the next).",
        hint=_CYCLE_HINT,
    )
