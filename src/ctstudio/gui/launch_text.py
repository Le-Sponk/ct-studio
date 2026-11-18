"""Plain launch-only presentation; process dispatch does not prove a file opened."""

from __future__ import annotations

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import CTStudioError
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
        return _started("Blender", receipt)
    if isinstance(receipt, corefolders.OpenedFolder):
        return (
            f"Asked the system to open {receipt.folder}. "
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
        return _started(label, receipt)
    subject = "prepare editor choices" if result.editor_action == "prepare" else f"open {label}"
    return _failure(subject, result.error)


def _started(label: str, receipt: editors.Launched) -> str:
    lines = [
        f"{label} was started (process {receipt.pid}) with {receipt.document}.",
        f"CT Studio cannot tell whether {label} finished opening the file.",
        *receipt.warnings,
    ]
    return "\n".join(lines)


def _failure(subject: str, error: BaseException | None) -> str:
    if isinstance(error, CTStudioError):
        return str(error)  # already an explanation and a next step
    if error is not None and not isinstance(error, Exception):
        return f"The request to {subject} was interrupted. Try again."
    reason = str(error) or type(error).__name__
    return f"Could not {subject}: {reason}. Try again; if it keeps failing, restart CT Studio."
