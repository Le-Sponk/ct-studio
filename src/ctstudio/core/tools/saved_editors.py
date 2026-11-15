"""Fresh machine settings for an explicit editor choice; dispatch receipts only."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ctstudio.core.project import settings
from ctstudio.core.tools import custom_editors, editors


@dataclass(frozen=True)
class EditorChoice:
    """An exact namespace and id, not a preference or an inferred default."""

    namespace: Literal["builtin", "custom"]
    tool_id: str


def _check_text(tool_id: str, document: Path, path: Path | None) -> None:
    if path is None:
        return
    try:
        text = str(path)
        if "\0" in text:
            raise ValueError("configured executable contains NUL")
        text.encode("utf-8")
    except ValueError as exc:
        raise editors.EditorError(
            tool_id,
            document,
            "configured executable contains unsafe text",
            hint="Choose an executable path without NUL or invalid Unicode text.",
        ) from exc


def open_saved(
    choice: EditorChoice, document: Path, *, project: Path, settings_path: Path | None = None
) -> editors.Launched:
    """Read settings for this request and preserve the selected owner's result."""
    if choice.namespace not in ("builtin", "custom"):
        raise editors.EditorError(
            choice.tool_id,
            document,
            "unknown editor namespace",
            hint="Explicitly choose the builtin or custom editor namespace.",
        )
    loaded = settings.load(settings_path)
    configured = loaded.configured()
    if choice.namespace == "custom":
        tool = loaded.custom_tools().get(choice.tool_id)
        if tool is None:
            raise editors.EditorError(
                choice.tool_id,
                document,
                "saved custom editor is missing",
                hint="Configure this custom editor again or explicitly choose another editor.",
            )
        return custom_editors.open_custom(
            choice.tool_id,
            tool,
            document,
            project=project,
            wine_prefix=loaded.wine_prefixes().get(choice.tool_id),
            wine_executable=configured.get("wine"),
        )
    _check_text(choice.tool_id, document, configured.get(choice.tool_id))
    return editors.open_in(
        choice.tool_id,
        document,
        executable=configured.get(choice.tool_id),
        wine_prefix=loaded.wine_prefixes().get(choice.tool_id),
        wine_executable=configured.get("wine"),
    )
