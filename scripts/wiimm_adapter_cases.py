"""Measured Wiimm cases for the P2-T05 adapters, kept out of the 400-line base table."""

from __future__ import annotations

from ops_cases import Case

_STAGE = ("@stage",)
_EMPTY = ("@empty_stage",)
_SZS = ("wszst", "create", "stage", "--dest", "t.szs")

CHECK_CASES: tuple[Case, ...] = (
    Case("check directory", ("wszst", "check", "stage"), (_STAGE,), "findings"),
    Case("check empty directory", ("wszst", "check", "empty"), (_EMPTY,), "findings"),
    Case(
        "check empty archive",
        ("wszst", "check", "empty.szs"),
        (_EMPTY, ("wszst", "create", "empty", "--dest", "empty.szs")),
        "findings",
    ),
)

# P2-T05b: ``analyze --json`` reports per-file analysis in one JSON object. The fake
# models only the directory/junk/missing rows; it never invents analysis of an archive.
ANALYZE_CASES: tuple[Case, ...] = (
    Case("analyze json", ("wszst", "analyze", "--json", "t.szs"), (_STAGE, _SZS), "unmodelled"),
    Case(
        "analyze json uncompressed",
        ("wszst", "analyze", "--json", "u.szs"),
        (_STAGE, ("wszst", "create", "stage", "--dest", "u.szs", "--no-compress")),
        "unmodelled",
    ),
    Case(
        "analyze json empty archive",
        ("wszst", "analyze", "--json", "empty.szs"),
        (_EMPTY, ("wszst", "create", "empty", "--dest", "empty.szs")),
        "unmodelled",
    ),
    Case("analyze json directory", ("wszst", "analyze", "--json", "stage"), (_STAGE,)),
    Case("analyze json empty directory", ("wszst", "analyze", "--json", "empty"), (_EMPTY,)),
    Case("analyze json junk", ("wszst", "analyze", "--json", "junk.szs"), (("@junk", "junk.szs"),)),
    Case("analyze json missing", ("wszst", "analyze", "--json", "missing.szs")),
)
