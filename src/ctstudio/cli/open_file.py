"""``ctstudio open``: hand one file to an external editor (P3-T07).

The editor is chosen by file type, in ``EDITOR_DOCUMENTS`` order (BrawlCrate before
RiiStudio, Lorenzi's KMP Editor before KMP Cloud), from the editors that are installed;
``--with`` names one instead. Starting an editor is not the same as the file being loaded
(TOOLS.md "Launch contracts"), and the output says so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ctstudio.cli.status import configured_tools
from ctstudio.core.errors import CTStudioError, ToolNotFound
from ctstudio.core.tools.availability import available_tools
from ctstudio.core.tools.editors import EDITOR_DOCUMENTS, open_in
from ctstudio.core.tools.registry import TOOL_BY_ID

_UNCERTAIN = "CT Studio cannot tell whether the editor loaded the file; check its window."


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "open",
        help="open a file in an external editor",
        description="Start an installed editor on FILE: a .blend in Blender, a .brres in "
        "BrawlCrate or RiiStudio, a .kmp in Lorenzi's KMP Editor or KMP Cloud.",
    )
    parser.add_argument("file", type=Path, help="the file to open")
    parser.add_argument(
        "--with", dest="editor", choices=tuple(EDITOR_DOCUMENTS), help="the editor to use"
    )
    parser.add_argument(
        "--wine-prefix", type=Path, help="Linux: the Wine prefix for a Windows editor"
    )


def run(args: argparse.Namespace) -> int:
    document: Path = args.file
    if not document.is_file():
        raise CTStudioError(f"{document} was not found.", hint="Check the path and try again.")
    configured = configured_tools()
    editor: str = args.editor or _editor_for(document, configured)
    launched = open_in(
        editor, document, executable=configured.get(editor), wine_prefix=args.wine_prefix
    )
    print(f"Started {TOOL_BY_ID[editor].name} for {document.name} (process {launched.pid}).")
    print(_UNCERTAIN)
    for warning in launched.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _editor_for(document: Path, configured: dict[str, Path]) -> str:
    suffix = document.suffix.lower()
    candidates = [tool for tool, suffixes in EDITOR_DOCUMENTS.items() if suffix in suffixes]
    if not candidates:
        known = sorted({s for suffixes in EDITOR_DOCUMENTS.values() for s in suffixes})
        raise CTStudioError(
            f"CT Studio has no editor for {suffix or 'extensionless'} files.",
            hint=f"CT Studio opens {', '.join(known)} files in an editor.",
        )
    found = available_tools(configured=configured)
    for tool in candidates:
        if tool in found:
            return tool
    names = " or ".join(TOOL_BY_ID[tool].name for tool in candidates)
    raise ToolNotFound(
        names, hint="Install one of them; `ctstudio doctor` shows where CT Studio looked."
    )
