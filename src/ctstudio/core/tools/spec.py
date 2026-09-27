"""Static tool metadata and user-defined argv templates; no discovery or spawning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from types import MappingProxyType
from typing import Literal

from ctstudio.core.errors import ProjectError


@dataclass(frozen=True)
class ToolSpec:
    """A tool's documented identity; installed location and actual version come later."""

    id: str
    name: str
    kind: Literal["cli", "gui"]
    exe_names: Mapping[str, tuple[str, ...]]
    version_args: tuple[str, ...]
    version_regex: str | None  # None: no verified output parser, not "any version".
    min_version: str | None  # None: compatibility floor not established.
    homepage: str
    download_page: str
    licence: str
    used_for: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "exe_names", MappingProxyType(dict(self.exe_names)))


@dataclass(frozen=True)
class CustomTool:
    """A user-supplied executable and argv tokens, with three path placeholders."""

    name: str
    exe: Path
    args_template: Sequence[str]

    def __post_init__(self) -> None:
        if not self.name.strip() or self.exe == Path("."):
            raise ProjectError(
                "Invalid custom tool.", hint="Provide a name and an executable path."
            )
        if isinstance(self.args_template, str):
            raise ProjectError(
                "Invalid custom tool argument.", hint="Provide a list of argv tokens."
            )
        object.__setattr__(self, "args_template", tuple(self.args_template))
        for argument in self.args_template:
            try:
                fields = Formatter().parse(argument)
                if any(
                    field not in (None, "file", "dir", "project") or conversion or format_spec
                    for _, field, format_spec, conversion in fields
                ):
                    raise ValueError("use only {file}, {dir} or {project}")
            except ValueError as exc:
                raise ProjectError(
                    "Invalid custom tool argument.",
                    hint="Use only {file}, {dir} or {project} in argv tokens.",
                    details=f"argument={argument!r}; error={exc}",
                ) from exc

    def argv(self, *, file: Path, dir: Path, project: Path) -> tuple[str, ...]:
        """Substitute paths without shell parsing or splitting a token at spaces."""
        values = {"file": str(file), "dir": str(dir), "project": str(project)}
        return (str(self.exe), *(argument.format_map(values) for argument in self.args_template))
