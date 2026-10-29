"""P2-T05g: launching a document in an external editor (``ctstudio.core.tools.editors``).

Contracts from TOOLS.md "Launch contracts" (S7, P0-T13, P2-T05g probe): one document per
launch, options after the path, argv only (no ShellExecute association), cwd = the
document's folder. The result says "launched", never "opened".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools import editors, wine
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.editors import EDITOR_DOCUMENTS, EditorError, Launched, open_in
from ctstudio.core.tools.spec import ToolSpec

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_launch(cmd: list[object], *, cwd: Path, env: object = None) -> int:
        calls.append({"cmd": list(cmd), "cwd": cwd, "env": env})
        return 4242

    monkeypatch.setattr(editors, "launch_detached", fake_launch)
    return calls


def _doc(tmp_path: Path, name: str, folder: str = "dossier e") -> Path:
    path = tmp_path / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"document")
    return path


def _exe(tmp_path: Path, name: str = "editor") -> Path:
    path = tmp_path / "tools" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")
    return path


@pytest.mark.parametrize(
    ("tool", "name", "tail"),
    [
        ("brawlcrate", "course_model.brres", ["/audio:none"]),
        ("riistudio", "course_model.brres", []),
        ("kmp_editor_lorenzi", "course.kmp", []),
        ("kmp_cloud", "course.kmp", []),
        ("blender", "course.blend", []),
    ],
)
def test_each_editor_gets_one_absolute_path_first_and_options_after(
    tool: str, name: str, tail: list[str], launches: list[dict[str, object]], tmp_path: Path
) -> None:
    doc, exe = _doc(tmp_path, name), _exe(tmp_path)
    result = open_in(tool, doc, executable=exe)
    assert launches == [
        {"cmd": [exe.resolve(), doc.resolve(), *tail], "cwd": doc.parent.resolve(), "env": None}
    ]
    assert result == Launched(tool, 4242, doc.resolve(), ())


def test_relative_documents_are_made_absolute(
    launches: list[dict[str, object]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = _doc(tmp_path, "course.kmp")
    monkeypatch.chdir(tmp_path)
    open_in("kmp_editor_lorenzi", Path(doc.parent.name) / doc.name, executable=_exe(tmp_path))
    assert launches[0]["cmd"][1] == doc.resolve()  # type: ignore[index]
    assert Path(str(launches[0]["cmd"][1])).is_absolute()  # type: ignore[index]


def test_document_types_are_the_measured_ones() -> None:
    assert dict(EDITOR_DOCUMENTS) == {
        "brawlcrate": (".brres",),
        "riistudio": (".brres",),
        "kmp_editor_lorenzi": (".kmp",),
        "kmp_cloud": (".kmp",),
        "blender": (".blend",),
    }


def test_suffixes_match_case_insensitively(
    launches: list[dict[str, object]], tmp_path: Path
) -> None:
    open_in("kmp_cloud", _doc(tmp_path, "COURSE.KMP"), executable=_exe(tmp_path))
    assert len(launches) == 1


@pytest.mark.parametrize(
    ("tool", "name", "reason"),
    [
        ("wszst", "course.szs", "not an editor"),
        ("dolphin", "game.iso", "not an editor"),
        ("brawlcrate", "notes.txt", r"\.brres"),
        ("brawlcrate", "codes.gct", r"\.brres"),
        ("kmp_editor_lorenzi", "course_model.brres", r"\.kmp"),
        ("blender", "course.kmp", r"\.blend"),
    ],
)
def test_wrong_tool_or_document_type_is_refused(
    tool: str, name: str, reason: str, launches: list[dict[str, object]], tmp_path: Path
) -> None:
    with pytest.raises(EditorError, match=reason):
        open_in(tool, _doc(tmp_path, name), executable=_exe(tmp_path))
    assert launches == []


def test_missing_document_and_folders_are_refused(
    launches: list[dict[str, object]], tmp_path: Path
) -> None:
    with pytest.raises(EditorError, match="not found"):
        open_in("kmp_cloud", tmp_path / "gone.kmp", executable=_exe(tmp_path))
    folder = tmp_path / "folder.kmp"
    folder.mkdir()
    with pytest.raises(EditorError, match="not a file"):
        open_in("kmp_cloud", folder, executable=_exe(tmp_path))
    assert launches == []


def test_riistudio_warns_about_non_ascii_paths_but_still_launches(
    launches: list[dict[str, object]], tmp_path: Path
) -> None:
    doc = _doc(tmp_path, "course_model.brres", folder="dossier é 日本")
    result = open_in("riistudio", doc, executable=_exe(tmp_path))
    assert len(launches) == 1
    [warning] = result.warnings
    assert "RiiStudio" in warning and "non-ASCII" in warning and "empty" in warning


@pytest.mark.parametrize("tool", ["brawlcrate", "kmp_editor_lorenzi", "kmp_cloud", "blender"])
def test_other_editors_take_non_ascii_paths_without_warning(
    tool: str, launches: list[dict[str, object]], tmp_path: Path
) -> None:
    suffix = EDITOR_DOCUMENTS[tool][0]
    result = open_in(
        tool, _doc(tmp_path, f"pièce{suffix}", folder="dossier é 日本"), executable=_exe(tmp_path)
    )
    assert result.warnings == ()


def test_riistudio_ascii_path_has_no_warning(
    launches: list[dict[str, object]], tmp_path: Path
) -> None:
    assert (
        open_in(
            "riistudio", _doc(tmp_path, "course_model.brres"), executable=_exe(tmp_path)
        ).warnings
        == ()
    )


# --- discovery --------------------------------------------------------------------------------


def _discovered(
    monkeypatch: pytest.MonkeyPatch, location: ToolLocation | None
) -> list[tuple[ToolSpec, dict[str, object]]]:
    seen: list[tuple[ToolSpec, dict[str, object]]] = []

    def fake_discover(spec: ToolSpec, **kwargs: object) -> ToolLocation | None:
        seen.append((spec, kwargs))
        return location

    monkeypatch.setattr(editors, "discover", fake_discover)
    return seen


def test_discovered_direct_editor_is_launched(
    launches: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = _exe(tmp_path, "Lorenzi's KMP Editor.exe")
    seen = _discovered(monkeypatch, ToolLocation(exe, None, "standard", "direct"))
    open_in("kmp_editor_lorenzi", _doc(tmp_path, "course.kmp"))
    assert launches[0]["cmd"][0] == exe  # type: ignore[index]
    [(spec, kwargs)] = seen
    assert spec.id == "kmp_editor_lorenzi" and kwargs == {"include_dev": True}


def test_missing_editor_is_tool_not_found(
    launches: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _discovered(monkeypatch, None)
    with pytest.raises(ToolNotFound, match="BrawlCrate") as caught:
        open_in("brawlcrate", _doc(tmp_path, "a.brres"))
    assert (
        caught.value.hint is not None and "github.com/soopercool101/BrawlCrate" in caught.value.hint
    )
    assert launches == []


def test_flatpak_launchers_are_still_refused(
    launches: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    location = ToolLocation(_exe(tmp_path), None, "flatpak", "flatpak", "org.blender.Blender")
    _discovered(monkeypatch, location)
    with pytest.raises(ToolNotFound) as caught:
        open_in("blender", _doc(tmp_path, "x.blend"))
    assert caught.value.hint is not None and "Flatpak" in caught.value.hint
    assert launches == []


# --- Wine (P2-T05g2) ----------------------------------------------------------------------


@pytest.fixture
def wine_launches(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake(exe: Path, document: Path, options: tuple[str, ...], **kwargs: object) -> int:
        calls.append({"exe": exe, "document": document, "options": options, **kwargs})
        return 5150

    monkeypatch.setattr(wine, "launch", fake)
    return calls


def _wine_world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, editor: str = "BrawlCrate.exe"
) -> tuple[Path, Path]:
    exe, wine_exe = _exe(tmp_path, editor), _exe(tmp_path, "wine")

    def fake_discover(spec: ToolSpec, **_kwargs: object) -> ToolLocation | None:
        if spec.id == "wine":
            return ToolLocation(wine_exe, None, "path", "direct")
        return ToolLocation(exe, None, "standard", "wine")

    monkeypatch.setattr(editors, "discover", fake_discover)
    return exe, wine_exe


@pytest.mark.parametrize(
    ("tool", "name", "options"),
    [
        ("brawlcrate", "pièce.brres", ("/audio:none",)),
        ("kmp_cloud", "pièce.kmp", ()),
        ("riistudio", "course.brres", ()),
        ("kmp_editor_lorenzi", "pièce.kmp", ()),
    ],
)
def test_a_wine_editor_is_launched_through_the_wine_adapter(
    tool: str,
    name: str,
    options: tuple[str, ...],
    launches: list[dict[str, object]],
    wine_launches: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    exe, wine_exe = _wine_world(monkeypatch, tmp_path)
    doc, prefix = _doc(tmp_path, name, folder="dossier é 日本"), tmp_path / "prefix"
    result = open_in(tool, doc, wine_prefix=prefix)
    assert launches == []  # never started directly
    assert wine_launches == [
        {
            "exe": exe,
            "document": doc.resolve(),
            "options": options,
            "wine": wine_exe,
            "prefix": prefix,
        }
    ]
    assert result == Launched(tool, 5150, doc.resolve(), ())


def test_riistudio_under_wine_has_no_non_ascii_warning(
    launches: list[dict[str, object]],
    wine_launches: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Linux run: RiiStudio started on "dossier é 日本/pièce map_model.brres" like on an ASCII
    # path; the Windows-only warning is about the native build's path handling.
    _wine_world(monkeypatch, tmp_path, "RiiStudio.exe")
    doc = _doc(tmp_path, "pièce.brres", folder="dossier é 日本")
    assert open_in("riistudio", doc, wine_prefix=tmp_path / "p").warnings == ()


@pytest.mark.parametrize(
    ("tool", "recipe"),
    [
        ("brawlcrate", ("WINEARCH=win32", "dotnet48")),
        ("kmp_cloud", ("WINEARCH=win32", "dotnet48")),
        ("riistudio", ("WINEARCH=win64",)),
        ("kmp_editor_lorenzi", ("WINEARCH=win64",)),
    ],
)
def test_a_wine_editor_without_a_prefix_says_which_prefix_to_make(
    tool: str,
    recipe: tuple[str, ...],
    wine_launches: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _wine_world(monkeypatch, tmp_path)
    with pytest.raises(wine.WineError, match="Wine prefix") as caught:
        open_in(tool, _doc(tmp_path, f"x{EDITOR_DOCUMENTS[tool][0]}"))
    hint = caught.value.hint or ""
    assert all(part in hint for part in recipe), hint
    assert ("dotnet48" in hint) == ("dotnet48" in recipe)
    assert wine_launches == []


def test_missing_wine_is_tool_not_found(
    wine_launches: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = _exe(tmp_path, "BrawlCrate.exe")

    def fake_discover(spec: ToolSpec, **_kwargs: object) -> ToolLocation | None:
        return None if spec.id == "wine" else ToolLocation(exe, None, "standard", "wine")

    monkeypatch.setattr(editors, "discover", fake_discover)
    with pytest.raises(ToolNotFound, match="Wine") as caught:
        open_in("brawlcrate", _doc(tmp_path, "a.brres"), wine_prefix=tmp_path / "p")
    assert caught.value.hint is not None and "winehq" in caught.value.hint
    assert wine_launches == []


def test_a_configured_wine_executable_is_used(
    wine_launches: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _wine_world(monkeypatch, tmp_path)
    mine = _exe(tmp_path, "wine-staging")
    monkeypatch.chdir(mine.parent)
    open_in(
        "brawlcrate",
        _doc(tmp_path, "a.brres"),
        wine_prefix=tmp_path / "p",
        wine_executable=Path(mine.name),  # relative to the cwd
    )
    assert wine_launches[0]["wine"] == mine.resolve()
    assert Path(str(wine_launches[0]["wine"])).is_absolute()


def test_blender_is_never_run_through_wine(
    wine_launches: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _wine_world(monkeypatch, tmp_path, "blender.exe")
    with pytest.raises(ToolNotFound) as caught:
        open_in("blender", _doc(tmp_path, "x.blend"), wine_prefix=tmp_path / "p")
    assert caught.value.hint is not None and "Linux build of Blender" in caught.value.hint
    assert wine_launches == []


def test_a_configured_exe_on_linux_goes_through_wine(
    launches: list[dict[str, object]],
    wine_launches: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _exe_found, wine_exe = _wine_world(monkeypatch, tmp_path)
    monkeypatch.setattr(editors, "current_os", lambda: "linux")
    configured = _exe(tmp_path, "My BrawlCrate.EXE")
    open_in(
        "brawlcrate", _doc(tmp_path, "a.brres"), executable=configured, wine_prefix=tmp_path / "p"
    )
    assert launches == []
    assert wine_launches[0]["exe"] == configured.resolve()
    assert wine_launches[0]["wine"] == wine_exe


@pytest.mark.parametrize(
    ("os_name", "name"), [("windows", "BrawlCrate.exe"), ("linux", "brawlcrate")]
)
def test_other_configured_executables_run_directly(
    os_name: str,
    name: str,
    launches: list[dict[str, object]],
    wine_launches: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(editors, "current_os", lambda: os_name)
    open_in("brawlcrate", _doc(tmp_path, "a.brres"), executable=_exe(tmp_path, name))
    assert len(launches) == 1 and wine_launches == []


def test_configured_executable_must_exist(
    launches: list[dict[str, object]], tmp_path: Path
) -> None:
    with pytest.raises(ToolNotFound):
        open_in("kmp_cloud", _doc(tmp_path, "c.kmp"), executable=tmp_path / "missing.exe")
    assert launches == []


def test_launch_errors_propagate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def broken(*_a: object, **_k: object) -> int:
        raise ToolNotFound("KMP Cloud.exe", hint="permission")

    monkeypatch.setattr(editors, "launch_detached", broken)
    with pytest.raises(ToolNotFound, match="KMP Cloud"):
        open_in("kmp_cloud", _doc(tmp_path, "c.kmp"), executable=_exe(tmp_path))
