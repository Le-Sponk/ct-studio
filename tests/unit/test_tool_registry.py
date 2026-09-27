"""P2-T01: static external-tool metadata and user-defined argv templates."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from ctstudio.core.errors import ProjectError
from ctstudio.core.tools.registry import TOOL_BY_ID, TOOL_SPECS
from ctstudio.core.tools.spec import CustomTool, ToolSpec

pytestmark = pytest.mark.timeout(30)

EXPECTED_IDS = {
    "wszst",
    "wkclt",
    "wkmpt",
    "wimgt",
    "rszst",
    "abmatt",
    "blender",
    "brawlcrate",
    "riistudio",
    "kmp_editor_lorenzi",
    "kmp_cloud",
    "dolphin",
    "dolphin_tool",
    "wine",
    "winetricks",
}


def test_registry_is_one_table_with_unique_ids() -> None:
    ids = [spec.id for spec in TOOL_SPECS]
    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_IDS
    assert set(TOOL_BY_ID) == EXPECTED_IDS
    assert all(TOOL_BY_ID[spec.id] is spec for spec in TOOL_SPECS)
    assert all(isinstance(spec, ToolSpec) for spec in TOOL_SPECS)
    with pytest.raises(TypeError):
        TOOL_BY_ID["new"] = TOOL_SPECS[0]  # type: ignore[index] - index is deliberately immutable


def test_metadata_has_cross_platform_names_and_well_formed_https_urls() -> None:
    for spec in TOOL_SPECS:
        assert spec.name and spec.used_for and spec.licence
        assert spec.kind in {"cli", "gui"}
        assert set(spec.exe_names) == {"windows", "linux"}
        assert any(spec.exe_names.values()), spec.id
        for platform, names in spec.exe_names.items():
            assert len(names) == len(set(names))
            for name in names:
                assert name and "/" not in name and "\\" not in name
                if platform == "windows":
                    assert name.lower().endswith(".exe"), (spec.id, name)
        for url in (spec.homepage, spec.download_page):
            parsed = urlsplit(url)
            assert parsed.scheme == "https" and parsed.hostname and not parsed.username
            assert not parsed.password and not any(char.isspace() for char in url)


def test_version_probes_are_only_documented_commands_with_compilable_patterns() -> None:
    known = {
        "wszst": ("version",),
        "wkclt": ("version",),
        "wkmpt": ("version",),
        "wimgt": ("version",),
        "rszst": ("--version",),
        "abmatt": ("--help",),
        "blender": ("--version",),
    }
    for spec in TOOL_SPECS:
        assert spec.version_args == known.get(spec.id, ())
        if spec.version_regex is not None:
            re.compile(spec.version_regex)
        if spec.min_version is not None:
            assert re.fullmatch(r"\d+(?:\.\d+)*(?:[a-z])?", spec.min_version)
    assert (
        re.search(
            TOOL_BY_ID["wszst"].version_regex, "wszst: Wiimms SZS Tool v2.42a r8989 cygwin64"
        ).group(1)
        == "2.42a"
    )
    assert re.search(TOOL_BY_ID["blender"].version_regex, "Blender 5.2.2 LTS").group(1) == "5.2.2"
    assert (
        re.search(
            TOOL_BY_ID["rszst"].version_regex, "rszst_arg_parser 0.1.6\nRiiStudio CLI Alpha 5.11.5"
        ).group(1)
        == "5.11.5"
    )
    assert TOOL_BY_ID["abmatt"].version_regex is None  # Linux release banner disagrees with tag.
    assert TOOL_BY_ID["kmp_editor_lorenzi"].exe_names["windows"] == ("Lorenzi's KMP Editor.exe",)


def test_custom_tool_preserves_unicode_paths_as_separate_argv_tokens() -> None:
    spec = CustomTool(
        name="Mesh viewer",
        exe=Path("C:/Apps/Mesh Viewer.exe"),
        args_template=("--input={file}", "{dir}", "{project}"),
    )
    argv = spec.argv(
        file=Path("C:/tracks/course é.kmp"),
        dir=Path("C:/tracks/course é"),
        project=Path("C:/projects/My Track"),
    )
    assert argv == (
        str(Path("C:/Apps/Mesh Viewer.exe")),
        f"--input={Path('C:/tracks/course é.kmp')}",
        str(Path("C:/tracks/course é")),
        str(Path("C:/projects/My Track")),
    )


def test_custom_tool_copies_mutable_user_argument_list() -> None:
    arguments = ["{file}"]
    tool = CustomTool(name="viewer", exe=Path("viewer.exe"), args_template=arguments)
    arguments.append("--later")
    assert tool.argv(file=Path("one.kmp"), dir=Path("."), project=Path(".")) == (
        "viewer.exe",
        "one.kmp",
    )


@pytest.mark.parametrize("template", ["{unknown}", "{file.name}", "{file!r}", "{file:>20}", "{"])
def test_custom_tool_rejects_unrecognised_or_complex_placeholders(template: str) -> None:
    with pytest.raises(ProjectError, match="Invalid custom tool argument"):
        CustomTool(name="Editor", exe=Path("editor.exe"), args_template=(template,))
