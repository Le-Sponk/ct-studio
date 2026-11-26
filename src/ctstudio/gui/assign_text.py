"""Plain words for a finished file assignment (P5-T04b), shown on its component card."""

from __future__ import annotations

from pathlib import Path

from ctstudio.core.components.assign import Assigned
from ctstudio.core.errors import CTStudioError
from ctstudio.gui.launch_controller import LaunchResult

STALE_ASSIGNMENT = (
    "The project changed while the file was being assigned, so this card was not updated. "
    "Close and reopen the project to see the result."
)


def describe_assignment(result: LaunchResult) -> str:
    """What a finished file assignment did, shown on its card.

    Only what is new: the card's status already says which file the part uses ("using …"),
    so the note never repeats it (P5-T10e, owner decision D3).
    """
    receipt, error, source = result.receipt, result.error, result.source
    if isinstance(receipt, Assigned) and source is not None:
        if result.reference:
            if Path(receipt.file).is_absolute():  # full path in the tooltip (assignment_detail)
                return "Kept where it is, outside the project (not copied)."
            return "Kept where it is (not copied)."
        text = f"Copied from {source.name or source}."
        if receipt.backup is not None:  # always .ctstudio/backups/<time> (full path: tooltip)
            text += f" The previous copy is backed up in .ctstudio/backups/{receipt.backup.name}."
        return text
    return _failure_text(error)


def assignment_detail(result: LaunchResult) -> str:
    """The full path the card's note shortens (its tooltip), or empty."""
    receipt = result.receipt
    if not isinstance(receipt, Assigned):
        return ""
    if receipt.backup is not None:
        return str(receipt.backup)
    return receipt.file if result.reference and Path(receipt.file).is_absolute() else ""


def _failure_text(error: BaseException | None) -> str:
    if isinstance(error, CTStudioError):
        return str(error)
    if error is not None and not isinstance(error, Exception):
        return "Assigning the file was interrupted. Check this card, then try again."
    if isinstance(error, OSError):  # never the raw "[Errno n] 'C:\\\\…'" text
        reason = error.strerror or ("" if error.errno else str(error)) or "a system error"
    else:
        reason = str(error) or type(error).__name__
    return (
        f"Could not assign the file: {reason}. Try again; if it keeps failing, restart CT Studio."
    )
