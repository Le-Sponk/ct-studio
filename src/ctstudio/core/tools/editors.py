"""Launch one document in an external editor (native launchers only).

Measured contracts (docs/reference/TOOLS.md "Launch contracts"; S7, P0-T13, P2-T05g):

* Every editor reads one document from argv and has no single-instance forwarding, so
  each call starts its own window. Options go **after** the path: Lorenzi opens
  ``argv[1]`` unconditionally, so a flag first is opened as the "file".
* No editor registers a file association, so launching is by argv, never ShellExecute.
* A running editor is not a loaded document: RiiStudio stays up, empty, after a failed
  load, and RiiStudio and KMP Cloud never name the file in their titles. The result is
  therefore ``Launched``, never "opened".
* RiiStudio silently fails to load non-ASCII paths on native Windows; the launch still
  happens, with a warning the caller must show. Under Wine it started on one normally.
* The cwd (document folder or editor folder) made no difference on Windows; the
  document's folder is used. A detached editor outlives CT Studio.
* On Linux a Windows editor (discovered as ``launcher="wine"``, or a configured ``.exe``)
  runs through ``wine.launch`` in the caller's prefix (P2-T05g2). Flatpak stays refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ctstudio.core.errors import CTStudioError, ToolNotFound
from ctstudio.core.platform import current_os
from ctstudio.core.tools import wine
from ctstudio.core.tools.discovery import Launcher, discover
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
# Measured prefix per Windows editor (S7, P2-T05g2): PE32 .NET editors need win32 + .NET 4.8.
PREFIX_RECIPES: MappingProxyType[str, str] = MappingProxyType(
    {
        "brawlcrate": "WINEARCH=win32 WINEPREFIX=<folder> wineboot -u, then "
        "WINEPREFIX=<folder> winetricks -q dotnet48 win10",
        "kmp_cloud": "WINEARCH=win32 WINEPREFIX=<folder> wineboot -u, then "
        "WINEPREFIX=<folder> winetricks -q dotnet48 win10",
        "riistudio": "WINEARCH=win64 WINEPREFIX=<folder> wineboot -u",
        "kmp_editor_lorenzi": "WINEARCH=win64 WINEPREFIX=<folder> wineboot -u",
    }
)
_FLATPAK = "Flatpak editors cannot be launched yet; configure a directly installed one."
_NO_WINE_BLENDER = "Use the Linux build of Blender; CT Studio does not run Blender in Wine."
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


def _executable(tool_id: str, configured: Path | None) -> tuple[Path, Launcher]:
    spec = TOOL_BY_ID[tool_id]
    if configured is not None:
        if not configured.is_file():
            raise ToolNotFound(f"Configured {spec.name}", hint="Choose an existing executable.")
        windows_exe = current_os() == "linux" and configured.suffix.lower() == ".exe"
        return configured.resolve(), "wine" if windows_exe else "direct"
    location = discover(spec, include_dev=True)
    if location is None:
        raise ToolNotFound(spec.name, hint=f"Install {spec.name} from {spec.download_page}.")
    if location.launcher == "flatpak":
        raise ToolNotFound(spec.name, hint=_FLATPAK)
    return location.path, location.launcher


def _wine_executable(configured: Path | None) -> Path:
    if configured is not None:
        if not configured.is_file():
            raise ToolNotFound("Configured Wine", hint="Choose an existing wine executable.")
        return configured.resolve()
    spec = TOOL_BY_ID["wine"]
    location = discover(spec)
    if location is None:
        raise ToolNotFound(spec.name, hint=f"Install Wine from {spec.homepage}.")
    return location.path


def _through_wine(
    tool_id: str, exe: Path, document: Path, prefix: Path | None, wine_exe: Path | None
) -> int:
    if tool_id == "blender":
        raise ToolNotFound(TOOL_BY_ID[tool_id].name, hint=_NO_WINE_BLENDER)
    if prefix is None:
        raise wine.WineError(
            f"{TOOL_BY_ID[tool_id].name} needs a Wine prefix on Linux.",
            hint=f"Choose a Wine prefix folder. To create one: {PREFIX_RECIPES[tool_id]}",
        )
    options = _OPTIONS.get(tool_id, ())
    return wine.launch(exe, document, options, wine=_wine_executable(wine_exe), prefix=prefix)


def _warnings(tool_id: str, document: Path, launcher: Launcher) -> tuple[str, ...]:
    if tool_id == "riistudio" and launcher == "direct" and not str(document).isascii():
        return (_RIISTUDIO_NON_ASCII,)
    return ()


def open_in(
    tool_id: str,
    document: Path,
    *,
    executable: Path | None = None,
    wine_prefix: Path | None = None,
    wine_executable: Path | None = None,
) -> Launched:
    """Start ``tool_id`` on ``document`` as a detached process and return without waiting.

    Windows editors on Linux need ``wine_prefix`` (see ``PREFIX_RECIPES``); Wine is
    discovered unless ``wine_executable`` is given.
    """
    document = Path(document).resolve()
    _check_document(tool_id, document)
    exe, launcher = _executable(tool_id, executable)
    if launcher == "wine":
        pid = _through_wine(tool_id, exe, document, wine_prefix, wine_executable)
    else:
        pid = launch_detached([exe, document, *_OPTIONS.get(tool_id, ())], cwd=document.parent)
    return Launched(tool_id, pid, document, _warnings(tool_id, document, launcher))
