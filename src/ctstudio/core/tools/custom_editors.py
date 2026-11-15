"""Explicit custom argv through the native/Wine owners; no discovery or settings."""

from __future__ import annotations

import stat
from pathlib import Path
from string import Formatter

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.platform import current_os
from ctstudio.core.tools import wine
from ctstudio.core.tools.editors import EditorError, Launched
from ctstudio.core.tools.process import launch_detached
from ctstudio.core.tools.spec import CustomTool


def _safe_text(text: str) -> None:
    if "\0" in text:
        raise ValueError("text contains NUL")
    text.encode("utf-8")


def _checked_path(tool_id: str, document: Path, path: Path, role: str) -> Path:
    try:
        _safe_text(str(path))
        resolved = path.resolve(strict=True)
        _safe_text(str(resolved))
        mode = resolved.stat().st_mode
        valid = stat.S_ISDIR(mode) if role == "project" else stat.S_ISREG(mode)
        if not valid:
            raise ValueError("not a directory" if role == "project" else "not a regular file")
        return resolved
    except (OSError, ValueError, RuntimeError) as exc:
        kind = "directory" if role == "project" else "regular file"
        hint = f"Choose an existing {kind} for the {role} and check permissions."
        if role == "executable":
            raise ToolNotFound(
                "Custom executable", hint=hint, problem=f"cannot be used: {exc}"
            ) from exc
        raise EditorError(tool_id, document, f"{role} cannot be used: {exc}", hint=hint) from exc


def _arguments(
    tool_id: str, tool: CustomTool, document: Path, values: dict[str, str | Path]
) -> tuple[str, ...]:
    try:
        _safe_text(tool.name)
        argv = tool.argv(file=values["file"], dir=values["dir"], project=values["project"])
        for token in argv:
            _safe_text(token)
        return argv
    except (OSError, ValueError, RuntimeError) as exc:
        raise EditorError(
            tool_id,
            document,
            f"custom arguments cannot be used: {exc}",
            hint="Correct the custom editor name and argv tokens; remove unsafe text.",
        ) from exc


def _convert_values(
    tool: CustomTool, values: dict[str, str | Path], *, launcher: Path, prefix: Path
) -> None:
    referenced = dict.fromkeys(
        field
        for token in tool.args_template
        for _, field, _, _ in Formatter().parse(token)
        if field is not None
    )
    converted: dict[Path, str] = {}
    for field in referenced:
        path = Path(values[field])
        if path not in converted:
            converted[path] = wine.windows_path(path, wine=launcher, prefix=prefix)
        values[field] = converted[path]


def open_custom(
    tool_id: str,
    tool: CustomTool,
    document: Path,
    *,
    project: Path,
    wine_prefix: Path | None = None,
    wine_executable: Path | None = None,
) -> Launched:
    """Start explicit native/Wine custom argv; this does not establish document loading."""
    document = _checked_path(tool_id, document, document, "document")
    executable = _checked_path(tool_id, document, tool.exe, "executable")
    project = _checked_path(tool_id, document, project, "project")
    values: dict[str, str | Path] = {"file": document, "dir": document.parent, "project": project}
    argv = _arguments(tool_id, tool, document, values)
    if current_os() == "linux" and executable.suffix.lower() == ".exe":
        if wine_executable is None or wine_prefix is None:
            raise ToolNotFound(
                tool.name,
                hint="Choose both a Wine executable and prefix, or choose a native program here.",
            )
        executable, launcher, prefix = wine.validate_runtime(
            executable, wine=wine_executable, prefix=wine_prefix
        )
        _convert_values(tool, values, launcher=launcher, prefix=prefix)
        argv = _arguments(tool_id, tool, document, values)
        document = _checked_path(tool_id, document, document, "document")
        _checked_path(tool_id, document, project, "project")
        pid = wine.launch_argv(
            executable, argv[1:], cwd=document.parent, wine=launcher, prefix=prefix
        )
    else:
        pid = launch_detached([str(executable), *argv[1:]], cwd=document.parent)
    return Launched(tool_id, pid, document, ())
