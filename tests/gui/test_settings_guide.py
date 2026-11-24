"""P5-T08f: the Settings user guide matches the app (pages, labels, choices, defaults, keys,
where the files are, what happens when the settings file cannot be used)."""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

from ctstudio.core import platform as ct_platform
from ctstudio.core.build.build_log import KEEP
from ctstudio.core.build.runner import default_jobs
from ctstudio.core.project import settings
from ctstudio.core.project.custom_tool_preferences import CUSTOM_TOOLS
from ctstudio.core.project.editor_preferences import EDITOR_PREFERENCES
from ctstudio.core.project.manifest import COMPRESSIONS, BuildSettings
from ctstudio.core.project.settings import (
    AUTO_ADD_LIBRARY,
    BUILD_IGNORED,
    BUILD_JOBS,
    BUILD_LOGS_KEPT,
    COLOUR_SCHEME,
    DEVELOPER_MODE,
    MAX_BUILD_JOBS,
    MAX_BUILD_LOGS_KEPT,
    SHOW_TOOL_COMMANDS,
)
from ctstudio.core.project.wine_preferences import WINE_PREFIXES
from ctstudio.gui.settings_window import PAGES
from ctstudio.gui.views import advanced_page, appearance_section, build_jobs, build_page
from ctstudio.gui.views.machine_choice import ChoiceRow
from ctstudio.gui.watchdog import StallWatchdog

pytestmark = pytest.mark.timeout(30)
ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/user/SETTINGS.md"
SOURCE = ROOT / "src/ctstudio/gui"


def _flat(text: str) -> str:
    return " ".join(text.replace("`", "").split())


def _plain(label: str) -> str:
    """A label as the user reads it (the & marks the access key)."""
    return label.replace("&", "")


def _section(heading: str) -> str:
    text = GUIDE.read_text(encoding="utf-8")
    assert f"\n## {heading}\n" in text, f"the guide has no '## {heading}' section"
    return text.split(f"\n## {heading}\n", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def _row(section: str, first_cell: str) -> list[str]:
    rows = [line for line in section.splitlines() if line.startswith(f"| {first_cell} |")]
    assert len(rows) == 1, f"the table needs exactly one row for {first_cell}"
    return [cell.strip() for cell in rows[0].strip("|").split("|")]


def _choices(row: ChoiceRow | tuple[tuple[str, object], ...]) -> str:
    pairs = row.choices if isinstance(row, ChoiceRow) else row
    return ", ".join(text for text, _value in pairs)


def test_the_guide_is_linked_from_the_readme_and_the_navigation_guide() -> None:
    assert "(docs/user/SETTINGS.md)" in (ROOT / "README.md").read_text(encoding="utf-8")
    navigation = (ROOT / "docs/user/PROJECT_NAVIGATION.md").read_text(encoding="utf-8")
    assert "(SETTINGS.md)" in navigation


def test_the_pages_menus_and_shortcut_are_the_app_s_own() -> None:
    intro = _flat(GUIDE.read_text(encoding="utf-8").split("\n## ", maxsplit=1)[0])
    assert f"The pages are, in order: {', '.join(PAGES)}." in intro, intro
    menu = (SOURCE / "main_window.py").read_text(encoding="utf-8")
    for action in ("Settings…", "Tools…", "Editors…"):
        assert f'QAction("{action}"' in menu and f"Settings → {action}" in intro, action
    assert 'QKeySequence("Ctrl+,")' in menu and "(Ctrl+,)" in intro
    for page in PAGES:
        _section(page)  # one section per page


def test_the_settings_folder_is_where_the_guide_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = _flat(_section("Where settings are kept"))
    assert r"%LOCALAPPDATA%\ctstudio\ctstudio on Windows" in where
    assert "~/.config/ctstudio on Linux (or $XDG_CONFIG_HOME/ctstudio" in where
    monkeypatch.setenv("WIN_PD_OVERRIDE_LOCAL_APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # settings.default_path is redirected for every GUI test; this is what it returns.
    found = ct_platform.user_directories().config / settings.FILE_NAME
    expected = ("ctstudio", "ctstudio") if sys.platform == "win32" else ("ctstudio",)
    assert found == tmp_path.joinpath(*expected, settings.FILE_NAME), found
    source = (ROOT / "src/ctstudio/core/project/settings.py").read_text(encoding="utf-8")
    assert "return ct_platform.user_directories().config / FILE_NAME" in source


def test_the_build_page_table_matches_the_page() -> None:
    section = _section("Build")
    source = (SOURCE / "views/build_page.py").read_text(encoding="utf-8")
    texts = ", ".join(build_page.COMPRESSION_TEXT[value] for value in COMPRESSIONS)
    defaults = BuildSettings()
    test = _row(section, "Test builds")
    assert test[1] == texts, test
    assert test[2].lower() == defaults.test_compression
    assert _row(section, "Release builds")[2].lower() == defaults.release_compression
    assert '"&Test builds"' in source and '"&Release builds"' in source
    assert '"Also make the track\'s _&d copy"' in source
    assert _row(section, "Also make the track's _d copy")[2] == (
        "on" if defaults.make_d_variant else "off"
    )
    assert '"&Auto-add missing object files"' in source
    assert _row(section, "Auto-add missing object files")[2] == (
        "on" if defaults.auto_add else "off"
    )
    for tab in ('"This &project"', '"This co&mputer"'):
        assert tab in source and f"**{_plain(tab.strip(chr(34)))}**" in section, tab
    assert '"&Undo changes"' in source and '"&Save"' in source
    assert "when you press Save; Undo changes goes back" in _flat(section)


def test_the_tools_buttons_are_the_page_s_own() -> None:
    section = _flat(_section("Tools"))
    source = (SOURCE / "views/tools_page.py").read_text(encoding="utf-8")
    for button, does in (
        ("Browse…", "sets"),
        ("Clear", "forgets"),
        ("Download page", "opens"),
        ("Re-check", "looks again"),
    ):
        assert f'"{button}"' in source, button
        assert f"{button} {does}" in section, button


def test_the_build_steps_text_matches_the_choice() -> None:
    section = _flat(_section("Build"))
    assert f"**This computer**: {_plain(build_jobs.TEXTS.label)}," in section
    assert "Automatic (the default) runs up to 4" in section
    assert default_jobs() <= 4 and MAX_BUILD_JOBS == 64
    assert f"any whole number from 1 to {MAX_BUILD_JOBS}" in section
    assert "the numbers from 1 to 8 (or to the number of processors" in section
    source = (SOURCE / "views/build_jobs.py").read_text(encoding="utf-8")
    assert "max(8, os.cpu_count() or 1)" in source


def test_the_editors_tabs_are_the_page_s_own() -> None:
    section = _flat(_section("Editors"))
    source = (SOURCE / "views/editors_page.py").read_text(encoding="utf-8")
    for tab in ('"&Order"', '"&Your editors"', '"&Wine (Linux)"'):
        assert tab in source, tab
    assert "on the tabs Order, Your editors and Wine (Linux)" in section
    assert "(OPEN_IN.md)" in section


def test_the_appearance_text_matches_the_choice() -> None:
    section = _flat(_section("Appearance"))
    choices = appearance_section.CHOICES
    assert choices[0][1] is None, "the first scheme must be the default"
    names = [text for text, _value in choices]
    assert f"{_plain(appearance_section.TEXTS.label)}: {names[0]} (the default), " in section
    assert f"{names[1]} or {names[2]}." in section


def test_the_advanced_table_matches_the_choices() -> None:
    section = _section("Advanced")
    commands = _row(section, _plain(advanced_page.COMMANDS.label))
    assert commands[1] == _choices(advanced_page.COMMAND_CHOICES)
    assert commands[2] == advanced_page.COMMAND_CHOICES[0][0], "Shown is the default"
    logs = _row(section, _plain(advanced_page.LOGS.label))
    assert logs[1] == _choices(advanced_page.LOGS) and logs[2] == str(KEEP)
    developer = _row(section, _plain(advanced_page.DEVELOPER.label))
    assert developer[1] == _choices(advanced_page.DEVELOPER)
    assert developer[2] == advanced_page.DEVELOPER.choices[0][0], "Off is the default"
    flat = _flat(section)
    assert f"any whole number from 1 to {MAX_BUILD_LOGS_KEPT}" in flat
    stall = inspect.signature(StallWatchdog).parameters["threshold"].default
    assert "CTSTUDIO_DEV=1 also turns it on" in flat and f"more than {stall * 1000:.0f} ms" in flat
    source = (SOURCE / "views/advanced_page.py").read_text(encoding="utf-8")
    for tab in ('"This co&mputer"', '"This &project"'):
        assert tab in source and f"**{_plain(tab.strip(chr(34)))}**" in section, tab
    assert "[build] extra_wszst_args" in flat and "read-only" in flat


@pytest.mark.parametrize(
    ("key", "absent"),
    [
        ("tools", "found automatically"),
        (BUILD_JOBS, "Automatic"),
        (AUTO_ADD_LIBRARY, "nothing is added"),
        (EDITOR_PREFERENCES, "the default order"),
        (CUSTOM_TOOLS, "none"),
        (WINE_PREFIXES, "none chosen"),
        (COLOUR_SCHEME, "follow the system"),
        (SHOW_TOOL_COMMANDS, "shown"),
        (BUILD_LOGS_KEPT, str(KEEP)),
        (DEVELOPER_MODE, "off"),
        ("format", "counts as `1`"),
        ("recent_projects", "none"),
    ],
)
def test_every_settings_key_has_a_row(key: str, absent: str) -> None:
    row = _row(_section("Keys in settings.json"), f"`{key}`")
    assert row[3] == absent, row


def _keys_in_code() -> set[str]:
    """Every settings.json key the code names: the settings module's key constants, the
    editor preference modules' keys, the two save writes by name, and recent projects."""
    keys = {
        value
        for name, value in vars(settings).items()
        if name.isupper() and isinstance(value, str) and re.fullmatch(r"[a-z_]+", value)
    }
    saved = (ROOT / "src/ctstudio/core/project/settings.py").read_text(encoding="utf-8")
    assert 'data = {"format": FORMAT, **settings.other, "tools": dict(settings.tools)}' in saved
    recent = (SOURCE / "recent_projects.py").read_text(encoding="utf-8")
    assert recent.count('"recent_projects"') >= 2 and "roots[:10]" in recent
    editors = {EDITOR_PREFERENCES, CUSTOM_TOOLS, WINE_PREFIXES}  # their own modules
    return keys | editors | {"format", "tools", "recent_projects"}


def test_the_keys_table_lists_exactly_the_keys_the_code_names() -> None:
    section = _section("Keys in settings.json")
    listed = set(re.findall(r"^\| `([a-z_]+)` \|", section, flags=re.MULTILINE))
    assert listed == _keys_in_code(), (sorted(listed), sorted(_keys_in_code()))
    assert _row(section, "`recent_projects`")[2] == "up to ten project folders"
    assert settings.FORMAT == 1 and _row(section, "`format`")[2] == f"`{settings.FORMAT}`"


def test_the_ranges_in_the_keys_table_are_the_app_s() -> None:
    section = _section("Keys in settings.json")
    assert _row(section, f"`{BUILD_JOBS}`")[2] == f"a whole number from 1 to {MAX_BUILD_JOBS}"
    assert _row(section, f"`{BUILD_LOGS_KEPT}`")[2] == (
        f"a whole number from 1 to {MAX_BUILD_LOGS_KEPT}"
    )
    schemes = ", ".join(f'`"{scheme}"`' for scheme in settings.COLOUR_SCHEMES)
    assert _row(section, f"`{COLOUR_SCHEME}`")[2] == schemes


def test_the_damaged_file_text_quotes_the_build_notice() -> None:
    section = _flat(_section("When the settings file cannot be used"))
    assert f'"{BUILD_IGNORED}"' in section, BUILD_IGNORED
    assert f"{KEEP} build logs" in section
    assert "developer mode off (unless CTSTUDIO_DEV=1)" in section
    # A damaged file gives builds empty settings: no auto-add library, so nothing is added.
    assert settings.UserSettings().auto_add_library() is None
    for module in ("cli/build.py", "gui/build_controller.py"):
        code = (ROOT / "src/ctstudio" / module).read_text(encoding="utf-8")
        assert "library=user.auto_add_library()" in code and "return UserSettings()" in code
    assert "no missing object files are added even with Auto-add on" in section
    assert "Open in… shows why and starts no editor" in section
