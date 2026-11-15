"""Custom Wine dispatch contract; synthetic paths and launch-only results."""

from __future__ import annotations

import inspect
from functools import partial
from pathlib import Path

import pytest
from custom_wine_helpers import converted, outcome, request

from ctstudio.core.tools import custom_editors, wine
from ctstudio.core.tools.editors import Launched


def test_explicit_wine_keywords_are_optional() -> None:
    parameters = inspect.signature(custom_editors.open_custom).parameters
    assert "wine_executable" in parameters and "wine_prefix" in parameters
    assert parameters["wine_executable"].default is None
    assert parameters["wine_prefix"].default is None
    assert parameters["wine_prefix"].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize(
    ("arch", "prefix_arch"), [("win32", "win32"), ("win32", "win64"), ("win64", "win64")]
)
def test_explicit_wine_preserves_custom_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arch: str, prefix_arch: str
) -> None:
    r = request(tmp_path, monkeypatch, arch, prefix_arch)
    tokens = (
        "",
        "日本 é ;&|>$",
        '"quoted"',
        "{{file}}",
        "--open={file:}",
        "{dir:}",
        "{project:}",
        "{file}/{file}",
    )
    result = outcome(lambda: r.open(r.tool(tokens)))
    assert isinstance(result, Launched), result
    assert result == Launched("brawlcrate", 917, r.document.resolve(), ())
    assert r.conversions == [r.document.resolve(), r.document.parent.resolve(), r.project.resolve()]
    assert r.launches == [
        (
            [
                str(r.launcher.resolve()),
                str(r.exe.resolve()),
                "",
                "日本 é ;&|>$",
                '"quoted"',
                "{file}",
                "--open=" + converted(r.document.resolve()),
                converted(r.document.parent.resolve()),
                converted(r.project.resolve()),
                converted(r.document.resolve()) + "/" + converted(r.document.resolve()),
            ],
            {
                "cwd": r.document.parent.resolve(),
                "env": {"WINEPREFIX": str(r.prefix.resolve())},
                "watch": wine.WATCH_SECONDS,
            },
        )
    ]
    assert r.document.read_bytes() == b"synthetic document unchanged"


@pytest.mark.parametrize(
    "tokens", [(), ("{{file}}", "{{dir}}", "{{project}}"), ("{project:}", "{project}")]
)
def test_only_actual_placeholders_are_converted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tokens: tuple[str, ...]
) -> None:
    r = request(tmp_path, monkeypatch)
    result = outcome(lambda: r.open(r.tool(tokens)))
    assert isinstance(result, Launched), result
    assert r.conversions == ([r.project.resolve()] if "{project:}" in tokens else [])
    assert len(r.launches) == 1
    expected = (
        [converted(r.project.resolve())] * 2
        if "{project:}" in tokens
        else [token.replace("{{", "{").replace("}}", "}") for token in tokens]
    )
    assert r.launches[0][0][2:] == expected


@pytest.mark.parametrize("supplied", ["none", "wine", "prefix"])
def test_wine_requires_both_explicit_choices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, supplied: str
) -> None:
    r = request(tmp_path, monkeypatch)
    result = outcome(
        lambda: custom_editors.open_custom(
            "custom",
            r.tool(),
            r.document,
            project=r.project,
            wine_executable=r.launcher if supplied == "wine" else None,
            wine_prefix=r.prefix if supplied == "prefix" else None,
        )
    )
    from ctstudio.core.errors import ToolNotFound

    assert isinstance(result, ToolNotFound), result
    assert result.hint
    assert "Wine" in result.hint and "prefix" in result.hint and "native" in result.hint
    assert r.conversions == [] and r.launches == []


@pytest.mark.parametrize("os_name", ["windows", "linux"])
def test_native_routes_ignore_even_unsafe_unused_wine_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, os_name: str
) -> None:
    r = request(tmp_path, monkeypatch)
    monkeypatch.setattr(custom_editors, "current_os", lambda: os_name)
    if os_name == "linux":
        r.exe = r.exe.rename(tmp_path / "native-editor")
    result = outcome(
        lambda: custom_editors.open_custom(
            "brawlcrate",
            r.tool(("{file:}", "", "{{project}}")),
            r.document,
            project=r.project,
            wine_executable=Path(str(tmp_path) + "\0"),
            wine_prefix=Path(str(tmp_path) + "\ud800"),
        )
    )
    assert isinstance(result, Launched), result
    assert r.conversions == []
    assert r.launches == [
        (
            [str(r.exe.resolve()), str(r.document.resolve()), "", "{project}"],
            {"cwd": r.document.parent.resolve()},
        )
    ]
    assert result.warnings == ()


@pytest.mark.parametrize("field", ["name", "template", "converted"])
@pytest.mark.parametrize("unsafe", ["\0", "\ud800"])
def test_unsafe_text_never_reaches_helpers_or_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, unsafe: str
) -> None:
    from ctstudio.core.tools.editors import EditorError
    from ctstudio.core.tools.spec import CustomTool

    r = request(tmp_path, monkeypatch)
    tool = CustomTool(
        "name" + unsafe if field == "name" else "name",
        r.exe,
        ("{file}" + unsafe if field == "template" else "{file}",),
    )
    observed: list[Path] = []

    def convert(path: Path, *, wine: Path, prefix: Path) -> str:
        observed.append(path)
        return "Z:\\unsafe" + unsafe

    if field == "converted":
        monkeypatch.setattr(wine, "windows_path", convert)
    result = outcome(lambda: r.open(tool))
    assert isinstance(result, EditorError), result
    assert result.hint and result.__cause__ is not None and r.launches == []
    assert observed == ([r.document.resolve()] if field == "converted" else [])
    assert r.conversions == []


def test_identical_path_values_share_one_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = request(tmp_path, monkeypatch)
    r.project = r.document.parent
    result = outcome(lambda: r.open(r.tool(("{file}", "{dir}", "{project}", "{dir}"))))
    assert isinstance(result, Launched), result
    assert r.conversions == [r.document.resolve(), r.document.parent.resolve()]
    assert r.launches[0][0][2:] == [
        converted(r.document.resolve()),
        *([converted(r.document.parent.resolve())] * 3),
    ]


def test_relative_roots_are_rebound_on_each_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = [request(tmp_path / str(number), monkeypatch) for number in range(2)]
    for r in requests:
        monkeypatch.chdir(r.root)
        monkeypatch.setattr(wine, "run", r.convert)
        monkeypatch.setattr(wine, "launch_detached", r.launch)
        from ctstudio.core.tools.spec import CustomTool

        result = outcome(
            partial(
                custom_editors.open_custom,
                "custom",
                CustomTool("custom", Path(r.exe.name), ("{file}", "{project}")),
                Path(r.document.name),
                project=Path(r.project.name),
                wine_executable=Path(r.launcher.name),
                wine_prefix=Path(r.prefix.name),
            )
        )
        assert isinstance(result, Launched), result
        assert r.conversions == [r.document.resolve(), r.project.resolve()]
        assert r.launches[0][0][1] == str(r.exe.resolve())
        assert r.launches[0][1]["cwd"] == r.document.parent.resolve()
