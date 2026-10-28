"""Measured Wiimm CHECK cases added without growing the original 400-line table."""

from __future__ import annotations

from ops_cases import Case

CHECK_CASES: tuple[Case, ...] = (
    Case("check directory", ("wszst", "check", "stage"), (("@stage",),), "findings"),
    Case("check empty directory", ("wszst", "check", "empty"), (("@empty_stage",),), "findings"),
    Case(
        "check empty archive",
        ("wszst", "check", "empty.szs"),
        (("@empty_stage",), ("wszst", "create", "empty", "--dest", "empty.szs")),
        "findings",
    ),
)
