"""``ctstudio doctor``: print the tool report as a table or JSON (P2-T06).

Exit status: 0 when every required tool is found, 1 otherwise. Optional tools never fail
the command; their rows say what is missing and how to fix it.
"""

from __future__ import annotations

import argparse
import json

from ctstudio.core.tools.doctor import Report, ToolCheck, diagnose

_LABELS = {
    "found": "found",
    "missing": "missing",
    "too_old": "too old",
    "not_working": "not working",
    "needs_wine": "needs Wine",
    "sandboxed": "sandboxed",
    "not_needed": "not needed",
}
_SOURCES = {
    "path": "from PATH",
    "standard": "standard location",
    "setting": "your setting",
    "dev": "developer copy in .tools",
    "flatpak": "Flatpak",
}
_HEADERS = ("Tool", "Status", "Version", "Used for")


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="check which external tools are installed",
        description="List every external tool CT Studio uses, whether it was found, and how "
        "to fix what is missing. Exits 1 only when a tool required to build tracks is not ready.",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--recheck", action="store_true", help="probe tool versions again instead of the cache"
    )


def run(args: argparse.Namespace) -> int:
    report = diagnose(force=args.recheck)
    if args.json:
        print(json.dumps(report.to_json(), indent=1, ensure_ascii=False))
    else:
        print(render(report), end="")
    return 0 if report.ok else 1


def _row(check: ToolCheck) -> tuple[str, str, str, str]:
    return (check.name, _LABELS[check.status], check.version or "-", check.used_for)


def _details(check: ToolCheck) -> list[str]:
    lines = []
    if check.path is not None:
        where = _SOURCES.get(check.source or "", check.source or "unknown")
        lines.append(f"    path: {check.path.as_posix()} ({check.launcher}, {where})")
    if check.fix:
        lines.append(f"    fix: {check.fix}")
    if check.note:
        lines.append(f"    note: {check.note}")
    return lines


def render(report: Report) -> str:
    """The human-readable table, one detail line per path, fix and note."""
    rows = [_row(check) for check in report.tools]
    widths = [max(len(cells[i]) for cells in (_HEADERS, *rows)) for i in range(4)]

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(
            cell.ljust(width) for cell, width in zip(cells, widths, strict=True)
        ).rstrip()

    out = [f"CT Studio doctor ({report.platform})", "", line(_HEADERS)]
    out.append(line(tuple("-" * width for width in widths)))
    for check, cells in zip(report.tools, rows, strict=True):
        out.append(line(cells))
        out.extend(_details(check))
    out.append("")
    out.append(_verdict(report))
    return "\n".join(out) + "\n"


def _verdict(report: Report) -> str:
    required = [check for check in report.tools if check.required]
    names = ", ".join(check.name for check in required)
    if report.ok:
        return f"All required tools are ready (required: {names})."
    broken = ", ".join(check.name for check in required if check.status != "found")
    return f"CT Studio cannot build tracks until these are fixed: {broken}."
