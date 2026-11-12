"""UI-thread publication of already-joined outside-edit results; no disk work here."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ctstudio.core.components.assign import Assigned
from ctstudio.core.errors import CTStudioError
from ctstudio.gui.launch_controller import LaunchResult

if TYPE_CHECKING:
    from ctstudio.gui.views.dashboard import Dashboard

REOPEN = "Close CT Studio and reopen this project before editing."


def present_reconcile(page: Dashboard, result: LaunchResult) -> None:
    """Called only for this dashboard's current project/root after the owner joins."""
    project = result.project
    if project.read_only:
        page.show_launch_note(f"This project is read-only. {REOPEN}")
        return
    if result.saved is None and result.recovery_error is None:
        # No recovery payload means the action never ran (e.g. thread creation failed).
        page.show_launch_note(_problem(result.error) if result.error else "No request ran.")
        return
    problem = _publish(result)
    if problem:
        # Retain the lock, but every writer must respect the unsafe-state read-only reason.
        project.read_only_reason = f"{problem} {REOPEN}"
        text = f"{problem} {REOPEN}"
        for error in (result.error, result.recovery_error):
            if error is not None:
                text += f"\n{_problem(error)}"
    else:
        text = _outcome(result)
    page.services.status.clear()  # a watcher check may predate the saved manifest
    page.set_project(project, changed=True)
    page.show_launch_note(text)


def _publish(result: LaunchResult) -> str:
    saved = result.saved
    if result.manifest is not result.project.manifest:
        return "The project changed while the outside-edit request was finishing."
    if saved is None or result.recovery_error is not None:
        return "The saved project could not be read."
    if saved.root != result.recovery_root:
        return "The saved project belongs to a different folder."
    result.project.manifest = saved.manifest
    return ""


def _outcome(result: LaunchResult) -> str:
    if result.error is not None:
        return (
            f"{_problem(result.error)}\nSaved project reloaded; changes may have finished. "
            "Check this card before trying again."
        )
    receipt = result.receipt
    if isinstance(receipt, Assigned):
        text = f"Locked as manual. Now using {receipt.file}."
        if receipt.backup is not None:
            text += f" The previous copy was backed up in {receipt.backup}."
        return text
    if isinstance(receipt, Path):
        return f"The outside edit was backed up in {receipt}. The next build will remake it."
    return "Saved project reloaded. Check this card before trying again."


def _problem(error: BaseException) -> str:
    if isinstance(error, CTStudioError):
        return str(error)
    if not isinstance(error, Exception):
        return f"The request was interrupted ({type(error).__name__})."
    if isinstance(error, OSError):
        reason = error.strerror or (str(error) if error.errno is None else "a system error")
    else:
        reason = str(error)
    return f"The request reported a problem: {reason or type(error).__name__}."
