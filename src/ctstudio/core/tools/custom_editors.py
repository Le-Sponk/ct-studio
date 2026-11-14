"""Explicit custom argv, native dispatch only; no discovery or settings ownership."""

from __future__ import annotations

import stat
from pathlib import Path

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.platform import current_os
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


def open_custom(tool_id: str, tool: CustomTool, document: Path, *, project: Path) -> Launched:
    """Start the configured process; this does not establish document loading."""
    document = _checked_path(tool_id, document, document, "document")
    executable = _checked_path(tool_id, document, tool.exe, "executable")
    project = _checked_path(tool_id, document, project, "project")
    if current_os() == "linux" and executable.suffix.lower() == ".exe":
        raise ToolNotFound(
            tool.name, hint="This Windows executable requires Wine; choose a native program here."
        )
    try:
        _safe_text(tool.name)
        argv = tool.argv(file=document, dir=document.parent, project=project)
        for token in argv:
            _safe_text(token)
    except (OSError, ValueError, RuntimeError) as exc:
        raise EditorError(
            tool_id,
            document,
            f"custom arguments cannot be used: {exc}",
            hint="Correct the custom editor name and argv tokens; remove unsafe text.",
        ) from exc
    pid = launch_detached([str(executable), *argv[1:]], cwd=document.parent)
    return Launched(tool_id, pid, document, ())
