"""Plain launch-only presentation; process dispatch does not prove a file opened."""

from __future__ import annotations

from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.errors import CTStudioError
from ctstudio.core.tools import editors
from ctstudio.core.tools import folders as corefolders
from ctstudio.gui.launch_controller import LaunchResult


def component_name(component_id: str | None) -> str:
    spec = COMPONENT_BY_ID.get(component_id or "")
    return spec.name if spec is not None else "this part"


def describe_launch(result: LaunchResult) -> str:
    """Plain words for a finished launch: dispatch only, never a claim that a file loaded."""
    receipt, error = result.receipt, result.error
    if isinstance(receipt, editors.Launched):
        lines = [
            f"Blender was started (process {receipt.pid}) with {receipt.document}.",
            "CT Studio cannot tell whether Blender finished opening the file.",
            *receipt.warnings,
        ]
        return "\n".join(lines)
    if isinstance(receipt, corefolders.OpenedFolder):
        return (
            f"Asked the system to open {receipt.folder}. "
            "If no window appears, open that folder in your file manager."
        )
    if isinstance(error, CTStudioError):
        return str(error)  # already an explanation and a next step
    subject = "open Blender" if result.component_id is None else "open the folder"
    if error is not None and not isinstance(error, Exception):
        return f"The request to {subject} was interrupted. Try again."
    reason = str(error) or type(error).__name__
    return f"Could not {subject}: {reason}. Try again; if it keeps failing, restart CT Studio."
