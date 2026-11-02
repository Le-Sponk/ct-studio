"""P3-T07: ``ctstudio new`` and ``ctstudio open`` in-process (``ctstudio.cli``).

No real editor is ever started here: ``open_in`` and the tool search are replaced, and each
test checks exactly what would have been launched. ``test_cli_project.py`` runs the same
commands as real processes against fake programs.
"""

from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path

import pytest

from ctstudio.__main__ import main
from ctstudio.cli import open_file
from ctstudio.core.errors import ToolNotFound
from ctstudio.core.tools.editors import Launched

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(autouse=True)
def no_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("ctstudio.gui.app")

    def run_gui(*_args: object) -> int:
        raise AssertionError("the GUI was started")

    fake.run_gui = run_gui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ctstudio.gui.app", fake)


@pytest.fixture(autouse=True)
def settings_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from ctstudio.core.project import settings

    path = tmp_path / "config é" / "settings.json"
    monkeypatch.setattr(settings, "default_path", lambda: path)
    return path


def _manifest(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "ctstudio.toml").read_text(encoding="utf-8"))["project"]


# --- new --------------------------------------------------------------------------------------


def test_new_makes_a_project_named_after_its_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "Sponk Raceway é"
    assert main(["new", str(root)]) == 0
    assert _manifest(root) == {
        "name": "Sponk Raceway é",
        "author": "",
        "version": "1.0",
        "slot": "beginner_course",
    }
    assert sorted(p.name for p in root.iterdir()) == [
        ".ctstudio", ".gitignore", "build", "ctstudio.toml", "files", "overrides"
    ]  # fmt: skip
    assert not (root / ".ctstudio" / "lock").exists(), "the project is not left locked"
    assert capsys.readouterr().out == (
        f"Created 'Sponk Raceway é' in {root.resolve().as_posix()},"
        " replacing Luigi Circuit (Mushroom Cup, track 1).\n"
        f'See what is left to do: ctstudio status "{root}"\n'
    )


@pytest.mark.parametrize("slot", ["farm_course", "Moo Moo Meadows", "mmm", " MMM "])
def test_new_accepts_any_name_for_the_slot(tmp_path: Path, slot: str) -> None:
    root = tmp_path / "p"
    assert main(["new", str(root), "--name", "Sponk", "--slot", slot]) == 0
    assert _manifest(root) == {
        "name": "Sponk",
        "author": "",
        "version": "1.0",
        "slot": "farm_course",
    }


def test_new_refuses_an_unknown_slot_with_a_suggestion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as info:
        main(["new", str(tmp_path / "p"), "--slot", "moo moo medows"])
    assert info.value.code == 2
    err = capsys.readouterr().err
    assert "argument --slot:" in err and "Did you mean farm_course (Moo Moo Meadows)?" in err
    assert not (tmp_path / "p").exists(), "nothing is created for a bad command line"


def test_new_stores_a_blend_inside_the_folder_relative(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "p"
    blend = root / "files" / "track é.blend"
    blend.parent.mkdir(parents=True)
    blend.write_bytes(b"BLENDER-v300REND")
    assert main(["new", str(root), "--blend", str(blend), "--force"]) == 0
    assert _manifest(root)["blend"] == "files/track é.blend"
    assert "Blender file: files/track é.blend\n" in capsys.readouterr().out


def test_new_refuses_a_blend_that_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "p"
    assert main(["new", str(root), "--blend", str(tmp_path / "nope.blend")]) == 1
    err = capsys.readouterr().err
    assert "nope.blend was not found." in err and "leave --blend out" in err
    assert not root.exists()


def test_new_refuses_a_folder_with_files_unless_forced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    (root / "notes.txt").write_text("mine", encoding="utf-8")
    assert main(["new", str(root)]) == 1
    assert "is not empty" in capsys.readouterr().err
    assert not (root / "ctstudio.toml").exists()
    assert main(["new", str(root), "--force"]) == 0
    assert (root / "notes.txt").read_text(encoding="utf-8") == "mine"


def test_new_never_replaces_a_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "p"
    assert main(["new", str(root), "--name", "First"]) == 0
    assert main(["new", str(root), "--name", "Second", "--force"]) == 1
    assert "already has a CT Studio project" in capsys.readouterr().err
    assert _manifest(root)["name"] == "First"


# --- open -------------------------------------------------------------------------------------


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_open_in(tool_id: str, document: Path, **kwargs: object) -> Launched:
        calls.append({"tool": tool_id, "document": document, **kwargs})
        warnings = ("it may not load",) if tool_id == "riistudio" else ()
        return Launched(tool_id, 4321, document.resolve(), warnings)

    monkeypatch.setattr(open_file, "open_in", fake_open_in)
    return calls


def _available(monkeypatch: pytest.MonkeyPatch, *tools: str) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> frozenset[str]:
        calls.append(kwargs)
        return frozenset(tools)

    monkeypatch.setattr(open_file, "available_tools", fake)
    return calls


def _file(tmp_path: Path, name: str) -> Path:
    path = tmp_path / "files é" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"data")
    return path


def test_open_uses_the_first_installed_editor_for_the_file_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    searched = _available(monkeypatch, "riistudio", "kmp_cloud")
    brres = _file(tmp_path, "course_model.brres")
    assert main(["open", str(brres)]) == 0
    assert launches == [
        {"tool": "riistudio", "document": brres, "executable": None, "wine_prefix": None}
    ]
    assert searched == [{"configured": {}}]
    captured = capsys.readouterr()
    assert captured.out == (
        "Started RiiStudio for course_model.brres (process 4321).\n"
        "CT Studio cannot tell whether the editor loaded the file; check its window.\n"
    )
    assert captured.err == "Warning: it may not load\n"


@pytest.mark.parametrize(
    ("name", "available", "expected"),
    [
        ("a.brres", ("brawlcrate", "riistudio"), "brawlcrate"),
        ("a.BRRES", ("riistudio",), "riistudio"),
        ("course.kmp", ("kmp_cloud", "kmp_editor_lorenzi"), "kmp_editor_lorenzi"),
        ("course.kmp", ("kmp_cloud",), "kmp_cloud"),
        ("track.blend", ("blender",), "blender"),
    ],
)
def test_editor_preference_follows_the_editor_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[dict[str, object]],
    name: str,
    available: tuple[str, ...],
    expected: str,
) -> None:
    _available(monkeypatch, *available)
    assert main(["open", str(_file(tmp_path, name))]) == 0
    assert [c["tool"] for c in launches] == [expected]


def test_with_names_the_editor_and_skips_the_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launches: list[dict[str, object]]
) -> None:
    searched = _available(monkeypatch)
    prefix = tmp_path / "prefix"
    kmp = _file(tmp_path, "course.kmp")
    assert main(["open", str(kmp), "--with", "kmp_cloud", "--wine-prefix", str(prefix)]) == 0
    assert launches == [
        {"tool": "kmp_cloud", "document": kmp, "executable": None, "wine_prefix": prefix}
    ]
    assert searched == []


def test_a_path_set_in_ct_studio_is_what_gets_launched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launches: list[dict[str, object]]
) -> None:
    from ctstudio.core.project import settings

    chosen = tmp_path / "BrawlCrate here" / "BrawlCrate.exe"
    settings.save(settings.UserSettings({"brawlcrate": str(chosen)}))
    searched = _available(monkeypatch, "brawlcrate")
    assert main(["open", str(_file(tmp_path, "a.brres"))]) == 0
    assert launches[0]["executable"] == chosen
    assert searched == [{"configured": {"brawlcrate": chosen}}]


def test_with_refuses_an_editor_ct_studio_cannot_launch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as info:
        main(["open", str(_file(tmp_path, "a.brres")), "--with", "wszst"])
    assert info.value.code == 2
    assert "invalid choice: 'wszst'" in capsys.readouterr().err


def test_no_installed_editor_names_the_ones_to_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _available(monkeypatch, "blender")
    assert main(["open", str(_file(tmp_path, "a.kmp"))]) == 1
    err = capsys.readouterr().err
    assert "Lorenzi's KMP Editor or KMP Cloud was not found." in err
    assert "ctstudio doctor" in err
    assert launches == []


def test_a_file_type_without_an_editor_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    searched = _available(monkeypatch, "blender", "brawlcrate")
    assert main(["open", str(_file(tmp_path, "course.kcl"))]) == 1
    err = capsys.readouterr().err
    assert "CT Studio has no editor for .kcl files." in err
    assert "Next: CT Studio opens .blend, .brres, .kmp files in an editor." in err
    assert launches == [] and searched == []


def test_a_missing_file_is_reported_before_any_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    launches: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    searched = _available(monkeypatch, "brawlcrate")
    assert main(["open", str(tmp_path / "gone.brres")]) == 1
    assert "gone.brres was not found." in capsys.readouterr().err
    assert launches == [] and searched == []


def test_editor_errors_are_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _available(monkeypatch, "brawlcrate")

    def refuse(*_a: object, **_k: object) -> Launched:
        raise ToolNotFound("BrawlCrate", hint="Install it.")

    monkeypatch.setattr(open_file, "open_in", refuse)
    assert main(["open", str(_file(tmp_path, "a.brres"))]) == 1
    assert "BrawlCrate was not found." in capsys.readouterr().err
