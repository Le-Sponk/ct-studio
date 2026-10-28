"""Structured validation results shared by CLI and GUI without Qt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning", "hint", "info"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    component: str
    code: str
    message: str
    hint: str | None
    source: str
    file: Path | None = None
    wiki: str | None = None
