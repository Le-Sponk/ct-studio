"""One build step (ARCHITECTURE §4 "Node", §7).

A ``Node`` declares the files it reads (``inputs``; a folder means every file in it) and
writes (``outputs``), its settings (``params``: plain JSON, so they can go into a cache key),
the tools it starts, the shared ``resources`` it must hold alone (``blender``,
``stage:<file>``) and an ``impl_version`` that is raised whenever its code changes what it
makes. ``run`` does the work. Two nodes are equal when everything but ``run`` is equal.

A badly made node is a programming error, so the checks raise ``ValueError`` naming it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.validation.issues import Issue

Profile = Literal["test", "release"]
_ID = re.compile(r"[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)?")
_MADE_PARTS = frozenset(spec.id for spec in COMPONENTS if spec.outputs)


@dataclass(frozen=True)
class BuildContext:
    """What a running step may use: the project, its manifest, the found tools, a log and the
    build's cancel request (pass it to every tool run so Cancel stops the tool)."""

    root: Path
    manifest: Manifest
    profile: Profile
    tools: Mapping[str, ToolLocation]
    log: Callable[[str], None]
    cancel: CancelToken = field(default_factory=CancelToken)


class StepFailed(CTStudioError):
    """A step stopped on a problem the user can fix, described by one ``Issue``."""

    def __init__(self, issue: Issue) -> None:
        self.issue = issue
        super().__init__(issue.message, hint=issue.hint)


@dataclass(frozen=True)
class NodeResult:
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True)
class Node:
    id: str
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    params: Mapping[str, object]
    tools: tuple[str, ...]
    resources: frozenset[str]
    impl_version: int
    run: Callable[[BuildContext], NodeResult] = field(compare=False, repr=False)
    component: str | None = None  # the track part this step makes, for state.json

    def __post_init__(self) -> None:
        node_id = _field(self, "id")
        if not isinstance(node_id, str) or not _ID.fullmatch(node_id):
            raise ValueError(f"{node_id!r} is not a valid build step id (like 'stage:kmp')")
        object.__setattr__(self, "inputs", self._paths(self.inputs))
        object.__setattr__(self, "outputs", self._paths(self.outputs))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "resources", frozenset(self.resources))
        object.__setattr__(self, "params", MappingProxyType(self._params()))
        self._check()

    def _check_names(self) -> None:
        for tool in self.tools:
            if tool not in TOOL_BY_ID:
                raise self._fail(f"unknown tool {tool!r}")
        if "" in self.resources:
            raise self._fail("a resource name cannot be empty")
        if self.component is not None and self.component not in _MADE_PARTS:
            raise self._fail(f"{self.component!r} is not a track part CT Studio makes")

    def _fail(self, problem: str) -> ValueError:
        return ValueError(f"{self.id}: {problem}")

    def _paths(self, given: Iterable[Path]) -> tuple[Path, ...]:
        paths = tuple(given)
        for path in paths:
            if not path.is_absolute():
                raise self._fail(f"{path} is not absolute")
            if paths.count(path) > 1:
                raise self._fail(f"{path} is listed twice")
        return paths

    def _params(self) -> dict[str, object]:
        try:
            return _plain_table(dict(self.params))
        except TypeError as exc:
            raise self._fail(f"params must be plain JSON ({exc})") from None

    def _check(self) -> None:
        if not self.outputs:
            raise self._fail("a build step must write at least one file")
        for path in set(self.inputs) & set(self.outputs):
            raise self._fail(f"reads and writes {path}")
        self._check_names()
        version = _field(self, "impl_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise self._fail("impl_version must be a whole number >= 1")


def _field(node: Node, name: str) -> object:
    """A field as passed in, which at run time may not be the declared type."""
    value: object = vars(node)[name]
    return value


def _plain_table(table: Mapping[object, object] | dict[str, object]) -> dict[str, object]:
    copy: dict[str, object] = {}
    for key, value in table.items():
        if not isinstance(key, str):
            raise TypeError(f"key {key!r} is not text")
        copy[key] = _plain(value)
    return copy


def _plain(value: object) -> object:
    """A copy of ``value`` when it is JSON: text, numbers, true/false, null, lists, tables."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list | tuple):
        return [_plain(item) for item in cast("Sequence[object]", value)]
    if isinstance(value, Mapping):
        return _plain_table(cast("Mapping[object, object]", value))
    raise TypeError(f"{value!r} is not JSON")
