"""Launch one document in an external editor (native launchers only).

Measured contracts (docs/reference/TOOLS.md "Launch contracts"; S7, P0-T13, P2-T05g):

* Every editor reads one document from argv and has no single-instance forwarding, so
  each call starts its own window. Options go **after** the path: Lorenzi opens
  ``argv[1]`` unconditionally, so a flag first is opened as the "file".
* No editor registers a file association, so launching is by argv, never ShellExecute.
* A running editor is not a loaded document: RiiStudio stays up, empty, after a failed
  load, and RiiStudio and KMP Cloud never name the file in their titles. The result is
  therefore ``Launched``, never "opened".
* RiiStudio silently fails to load non-ASCII paths on Windows; the launch still happens,
  with a warning the caller must show.
* The cwd (document folder or editor folder) made no difference on Windows; the
  document's folder is used. A detached editor outlives CT Studio.

Wine and Flatpak launchers are refused until P2-T05g2 verifies them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ctstudio.core.errors import CTStudioError, ToolNotFound
from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.process import launch_detached
from ctstudio.core.tools.registry import TOOL_BY_ID

EDITOR_DOCUMENTS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        "brawlcrate": (".brres",),
        "riistudio": (".brres",),
        "kmp_editor_lorenzi": (".kmp",),
        "kmp_cloud": (".kmp",),
        "blender": (".blend",),
    }
)
# Options placed after the document path (BrawlCrate: no audio device needed to edit).
_OPTIONS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {"brawlcrate": ("/audio:none",)}
)
_UNVERIFIED = {
    "wine": "Running Windows editors through Wine is not supported yet (P2-T05g2).",
    "flatpak": "Flatpak editors cannot be launched yet; configure a directly installed one.",
}
_RIISTUDIO_NON_ASCII = (
    "RiiStudio cannot open paths with non-ASCII characters on Windows: it will start "
    "with an empty editor. Move or rename the file to an ASCII-only path."
)


class EditorError(CTStudioError):
    """The document cannot be handed to that editor."""

    def __init__(self, tool_id: str, document: Path, reason: str) -> None:
        self.tool_id = tool_id
        self.document = document
        super().__init__(
            f"Cannot open {document.name} in {tool_id}: {reason}",
            hint="Choose a document of a type this editor opens.",
        )


@dataclass(frozen=True)
class Launched:
    """The editor process was started; whether it loaded the document is unknown."""

    tool_id: str
    pid: int
    document: Path
    warnings: tuple[str, ...]


def _check_document(tool_id: str, document: Path) -> None:
    suffixes = EDITOR_DOCUMENTS.get(tool_id)
    if suffixes is None:
        raise EditorError(tool_id, document, "not an editor CT Studio can launch")
    if document.suffix.lower() not in suffixes:
        raise EditorError(tool_id, document, f"it opens {', '.join(suffixes)} files")
    if not document.exists():
        raise EditorError(tool_id, document, "document not found")
    if not document.is_file():
        raise EditorError(tool_id, document, "not a file")


def _executable(tool_id: str, configured: Path | None) -> Path:
    spec = TOOL_BY_ID[tool_id]
    if configured is not None:
        if not configured.is_file():
            raise ToolNotFound(f"Configured {spec.name}", hint="Choose an existing executable.")
        return configured.resolve()
    location = discover(spec, include_dev=True)
    if location is None:
        raise ToolNotFound(spec.name, hint=f"Install {spec.name} from {spec.download_page}.")
    if location.launcher in _UNVERIFIED:
        raise ToolNotFound(spec.name, hint=_UNVERIFIED[location.launcher])
    return location.path


def _warnings(tool_id: str, document: Path) -> tuple[str, ...]:
    if tool_id == "riistudio" and not str(document).isascii():
        return (_RIISTUDIO_NON_ASCII,)
    return ()


def open_in(tool_id: str, document: Path, *, executable: Path | None = None) -> Launched:
    """Start ``tool_id`` on ``document`` as a detached process and return without waiting."""
    document = Path(document).resolve()
    _check_document(tool_id, document)
    exe = _executable(tool_id, executable)
    pid = launch_detached([exe, document, *_OPTIONS.get(tool_id, ())], cwd=document.parent)
    return Launched(tool_id, pid, document, _warnings(tool_id, document))
