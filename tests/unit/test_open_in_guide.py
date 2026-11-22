"""P5-T07g: the Open in… user guide matches the app and says what only HC1 can check."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.project.editor_preferences import DEFAULT_EDITORS
from ctstudio.core.tools.editors import PREFIX_RECIPES, TOOL_BY_ID

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/user/OPEN_IN.md"
CHECKPOINTS = ROOT / "docs/process/HUMAN_CHECKPOINTS.md"
LAUNCH_TEXT = ROOT / "src/ctstudio/gui/launch_text.py"
CHOICES = ROOT / "src/ctstudio/gui/views/editor_choices.py"
EDITORS_PAGE = ROOT / "src/ctstudio/gui/views/editors_page.py"


def _flat(text: str) -> str:
    return " ".join(text.replace("`", "").split())


def _section(heading: str) -> str:
    text = GUIDE.read_text(encoding="utf-8")
    assert f"\n## {heading}\n" in text, f"the guide has no '## {heading}' section"
    return text.split(f"\n## {heading}\n", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def _table_row(section: str, first_cell: str) -> list[str]:
    rows = [line for line in section.splitlines() if line.startswith(f"| {first_cell} |")]
    assert len(rows) == 1, f"the defaults table needs exactly one row for {first_cell}"
    return [cell.strip() for cell in rows[0].strip("|").split("|")]


def test_the_guide_is_linked_from_the_readme_and_the_navigation_guide() -> None:
    assert "(docs/user/OPEN_IN.md)" in (ROOT / "README.md").read_text(encoding="utf-8")
    navigation = (ROOT / "docs/user/PROJECT_NAVIGATION.md").read_text(encoding="utf-8")
    assert "(OPEN_IN.md)" in navigation


@pytest.mark.parametrize("kind", [kind for kind in DEFAULT_EDITORS if kind != "folder"])
def test_the_defaults_table_matches_the_catalogue(kind: str) -> None:
    names = ", ".join(TOOL_BY_ID[tool].name for tool in DEFAULT_EDITORS[kind])
    row = _table_row(_section("Default editors"), f"`{kind}`")
    assert row[1] == names, f"the guide lists {row[1]!r} for {kind}, the app offers {names!r}"


def test_the_defaults_table_names_the_folder_and_own_editor_targets() -> None:
    section = _section("Default editors")
    assert DEFAULT_EDITORS["folder"] == ("system",)
    assert "file manager" in _table_row(section, "Folders")[1].lower()
    assert "your own editors" in _table_row(section, "Any file")[1].lower()


def test_the_started_wording_is_the_app_s_own() -> None:
    """The guide quotes the result lines the app really shows (launch only, never 'opened')."""
    section = _flat(_section("What “started” means"))
    source = LAUNCH_TEXT.read_text(encoding="utf-8")
    for words in ("was started (process", "cannot tell whether", "finished opening the file"):
        assert words in source, f"launch_text.py no longer says {words!r}; update the guide"
        assert words in section, f"the guide does not quote {words!r}"
    assert "empty window" in section and "never reads" in section


@pytest.mark.parametrize(
    "words",
    [
        "one file",
        "new editor process",
        "never sends a second file",
        "course.kcl",
        "exactly",
        "set up",
        "settings → tools",
        "read-only",
    ],
)
def test_open_in_explains_one_file_new_processes_and_prerequisites(words: str) -> None:
    assert words in _flat(_section("Open in…")).lower()


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ('" (not found)"', CHOICES),
        ('" (cannot open this file)"', CHOICES),
        ('"Set up {name} in Tools…"', CHOICES),
        ('"&Order"', EDITORS_PAGE),
        ('"&Your editors"', EDITORS_PAGE),
        ('"&Wine (Linux)"', EDITORS_PAGE),
    ],
)
def test_the_labels_the_guide_quotes_are_the_app_s_own(label: str, source: Path) -> None:
    assert label in source.read_text(encoding="utf-8"), f"{source.name} no longer has {label}"
    shown = label.strip('"').strip().replace("&", "").replace("{name}", "…")
    assert shown in _flat(GUIDE.read_text(encoding="utf-8")), f"the guide lacks {shown!r}"


@pytest.mark.parametrize(
    "words",
    ["{file}", "{dir}", "{project}", "one argument", "no shell", "backup", "never overwrite"],
)
def test_the_editors_settings_section_explains_saving_and_arguments(words: str) -> None:
    assert words in _flat(_section("Choosing editors: Settings → Editors…")).lower()


@pytest.mark.parametrize("tool", sorted(PREFIX_RECIPES))
def test_the_linux_section_names_every_windows_editor(tool: str) -> None:
    section = _flat(_section("Linux and Wine"))
    assert TOOL_BY_ID[tool].name in section
    assert "Wine (Linux)" in section and "prefix" in section and "Blender" in section


def test_the_linux_section_says_own_exe_editors_need_the_wine_program_set() -> None:
    """Own .exe editors use only the Wine program saved in Settings → Tools (no search)."""
    section = _flat(_section("Linux and Wine"))
    assert "only with the Wine program set in Settings → Tools" in section
    assert "does not search for it" in section and '"(not found)"' in section


@pytest.mark.parametrize(
    "words", ["hc1", "stand-in", "loads", "saves", "desktop", "wine", "human_checkpoints.md"]
)
def test_the_guide_says_what_only_the_human_checkpoint_checks(words: str) -> None:
    assert words in _flat(_section("What is checked by hand")).lower()


def test_hc1_asks_for_the_manual_open_in_run() -> None:
    text = _flat(CHECKPOINTS.read_text(encoding="utf-8").split("## HC2")[0])
    assert 'Try "Open in…" for the BRRES and the KMP.' in text
    assert "Settings → Editors…" in text and "Wine prefix" in text and "started" in text
