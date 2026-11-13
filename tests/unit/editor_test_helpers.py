"""Synthetic editor documents with explicit Lorenzi-only collision eligibility."""

from pathlib import Path


def document(
    tmp_path: Path,
    name: str,
    folder: str = "dossier e",
    *,
    eligible_for: str | None = None,
) -> Path:
    path = tmp_path / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"document")
    if eligible_for == "kmp_editor_lorenzi":
        path.with_name("course.kcl").write_bytes(b"synthetic collision placeholder")
    return path
