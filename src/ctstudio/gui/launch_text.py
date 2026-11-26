"""Plain launch-only presentation; process dispatch does not prove a file opened."""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import CTStudioError
from ctstudio.core.project.project import Project
from ctstudio.core.tools import editors
from ctstudio.core.tools import folders as corefolders
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import PreparedEditors
from ctstudio.gui.launch_controller import LaunchResult


def component_name(component_id: str | None) -> str:
    spec = COMPONENT_BY_ID.get(component_id or "")
    return spec.name if spec is not None else "this part"


def editor_name(choice: EditorChoice | None) -> str:
    """A fallback when the offered label is unknown: the built-in name or the custom id."""
    if choice is None:
        return "the editor"
    spec = TOOL_BY_ID.get(choice.tool_id) if choice.namespace == "builtin" else None
    return spec.name if spec is not None else choice.tool_id


def describe_launch(result: LaunchResult) -> str:
    """Plain words for a finished launch: dispatch only, never a claim that a file loaded."""
    if result.editor_action is not None:  # first: editor results carry no component either
        return describe_editor(result, editor_name(result.choice))
    receipt = result.receipt
    if isinstance(receipt, editors.Launched):
        return _started("Blender", receipt, result.root)
    if isinstance(receipt, corefolders.OpenedFolder):
        place = _in_project(receipt.folder, result.root)
        named = "the project folder" if place == Path() else f'the folder "{place}"'
        return (
            f"Asked the system to open {named}. "
            "If no window appears, open that folder in your file manager."
        )
    subject = "open Blender" if result.component_id is None else "open the folder"
    return _failure(subject, result.error)


def describe_editor(result: LaunchResult, label: str) -> str:
    """An editor preparation or open, named by the label the user was offered."""
    receipt = result.receipt
    if isinstance(receipt, PreparedEditors):
        found = sum(option.state == "available" for option in receipt.options)
        name = receipt.document.name
        return f"Editor choices for {name} are ready ({found} of {len(receipt.options)} found)."
    if isinstance(receipt, editors.Launched):
        return _started(label, receipt, result.root)
    subject = "prepare editor choices" if result.editor_action == "prepare" else f"open {label}"
    return _failure(subject, result.error)


def _started(label: str, receipt: editors.Launched, root: Path) -> str:
    lines = [
        f"{label} was started (process {receipt.pid}) with {_in_project(receipt.document, root)}.",
        f"CT Studio cannot tell whether {label} finished opening the file.",
        *receipt.warnings,
    ]
    return "\n".join(lines)


def _in_project(document: Path, root: Path) -> Path:
    """A file in the project by its place in it ("files\\course.kcl", P5-T10c); any other
    file by its whole path."""
    try:
        return document.relative_to(root)
    except ValueError:
        return document


def _failure(subject: str, error: BaseException | None) -> str:
    if isinstance(error, CTStudioError):
        return str(error)  # already an explanation and a next step
    if error is not None and not isinstance(error, Exception):
        return f"The request to {subject} was interrupted. Try again."
    reason = str(error) or type(error).__name__
    return f"Could not {subject}: {reason}. Try again; if it keeps failing, restart CT Studio."


def blender_tip(project: Project | None, has_source: bool) -> str:
    """What Open in Blender does, or why it is off."""
    if project is not None and project.read_only:
        return f"Not available: this project is read-only ({project.read_only_reason})."
    if not has_source:
        return "No Blender file chosen yet: choose one in Project details…"
    return "Start Blender with this project's source file."
