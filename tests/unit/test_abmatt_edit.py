"""P2-T05e3: typed ABMatt material edits and copy/paste (``ctstudio.core.tools.abmatt_edit``).

ABMatt selectors are unanchored regex searches, an edit that changes nothing writes
nothing at exit 0, and paste silently removes the target's textures it leaves unused.
The adapter anchors and escapes every selector, checks materials exist first, skips
no-op edits, requires the archive to change otherwise, and reads the whole ``-c info``
table back: it must equal the expected one exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ctstudio.core.tools import abmatt, abmatt_edit, staging
from ctstudio.core.tools.abmatt import AbmattError, MaterialInfo
from ctstudio.core.tools.abmatt_edit import (
    MaterialEdit,
    MaterialRef,
    edit_materials,
    paste_material,
)
from ctstudio.core.tools.staging import ToolRun

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fakes"))
import fake_abmatt  # type: ignore[reportMissingImports] - tests/fakes inserted above

pytestmark = pytest.mark.timeout(60)
LAYER = "  {0}:\tScale:(1.0, 1.0) Rot:0.0 Trans:(0.0, 0.0)\n"
EDITS = [MaterialEdit("road", "course", xlu=True), MaterialEdit("grass", "course", cull="none")]


def _info(*rows: tuple[str, int, str, str]) -> str:
    return "".join(
        f">course->{m}\txlu:{x} cull:{c}\n" + LAYER.format(layer) for m, x, c, layer in rows
    )


PLAIN = _info(("road", 0, "inside", "road"), ("grass", 0, "inside", "grass"))


def _archive(
    tmp_path: Path, data: bytes = fake_abmatt.MARKER, name: str = "course_model.brres"
) -> Path:
    path = tmp_path / "piste 日本" / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return path


def test_parse_info_keeps_each_materials_layers() -> None:
    text = (
        _info(("road", 1, "none", "road"))
        + LAYER.format("detail")
        + ">course->water\txlu:0 cull:all\n"
    )
    assert abmatt.parse_info(text) == (
        MaterialInfo("course", "road", xlu=True, cull="none", layers=("road", "detail")),
        MaterialInfo("course", "water", xlu=False, cull="all", layers=()),
    )


# --- edit_materials through the recorded fake ---------------------------------------------


def test_edit_applies_checks_and_backs_up(fake_tools_path, tmp_path: Path) -> None:
    path = _archive(tmp_path)
    result = edit_materials(path, EDITS)
    assert result.changed and result.path == path
    table = {m.material: (m.xlu, m.cull) for m in result.materials}
    assert table == {
        "road": (True, "inside"),
        "grass": (False, "none"),
        "fence": (False, "inside"),
        "water": (False, "inside"),
    }
    assert path.read_bytes() == fake_abmatt.EDIT_MARKER
    [backup] = path.parent.glob("course_model.brres.*.bak")
    assert backup.read_bytes() == fake_abmatt.MARKER
    assert [call["argv"] for call in fake_tools_path.calls()] == [
        ["-b", "in.brres", "-c", "info"],
        ["-b", "in.brres", "-f", "edit.txt", "-o"],
        ["-b", "in.brres", "-c", "info"],
    ]


def test_an_edit_that_changes_nothing_does_not_run_or_touch_the_file(
    fake_tools_path, tmp_path: Path
) -> None:
    path = _archive(tmp_path)
    result = edit_materials(path, [MaterialEdit("road", "course", xlu=False, cull="inside")])
    assert not result.changed and path.read_bytes() == fake_abmatt.MARKER
    assert len(fake_tools_path.calls()) == 1 and not list(path.parent.glob("*.bak"))


@pytest.mark.parametrize(
    "edit",
    [MaterialEdit("oad", "course", xlu=True), MaterialEdit("road", "cours", xlu=True)],
    ids=["partial material", "partial model"],
)
def test_edit_refuses_materials_the_archive_does_not_have(
    edit: MaterialEdit, fake_tools_path, tmp_path: Path
) -> None:
    path = _archive(tmp_path)
    with pytest.raises(AbmattError, match="no material"):
        edit_materials(path, [edit])
    assert len(fake_tools_path.calls()) == 1 and path.read_bytes() == fake_abmatt.MARKER


@pytest.mark.parametrize(
    ("edits", "reason"),
    [
        ([], "no edits"),
        ([MaterialEdit("road", "course")], "nothing to change"),
        ([MaterialEdit("road", "course", cull="sideways")], "cull"),
        (
            [MaterialEdit("road", "course", xlu=True), MaterialEdit("road", "course", cull="none")],
            "twice",
        ),
        ([MaterialEdit("my road", "course", xlu=True)], "name"),
        ([MaterialEdit("route", "cöurse", xlu=True)], "name"),
        ([MaterialEdit("", "course", xlu=True)], "name"),
    ],
    ids=["empty", "no field", "bad cull", "duplicate", "space", "non-ascii", "blank"],
)
def test_edit_refuses_bad_requests_before_running(
    edits: list[MaterialEdit], reason: str, fake_tools_path, tmp_path: Path
) -> None:
    with pytest.raises(AbmattError, match=reason):
        edit_materials(_archive(tmp_path), edits)
    assert fake_tools_path.calls() == []


def test_missing_archive_is_refused(fake_tools_path, tmp_path: Path) -> None:
    with pytest.raises(AbmattError, match="not found"):
        edit_materials(tmp_path / "gone.brres", EDITS)
    assert fake_tools_path.calls() == []


# --- scripted runs: what ABMatt writes, and failures it reports at exit 0 -------------------


def _scripted(
    monkeypatch: pytest.MonkeyPatch, replies: list[tuple[int, str, dict[str, bytes]]]
) -> list[dict[str, str]]:
    """Each reply: exit code, stdout, files written; returns each run's command files."""
    seen: list[dict[str, str]] = []

    def fake_run(cmd: object, cwd: Path, **_: object) -> ToolRun:
        del cmd
        seen.append({p.name: p.read_text(encoding="ascii") for p in cwd.glob("*.txt")})
        code, stdout, writes = replies.pop(0)
        for name, data in writes.items():
            (cwd / name).write_bytes(data)
        return ToolRun(code, stdout, "")

    monkeypatch.setattr(abmatt, "run_collecting", fake_run)
    monkeypatch.setattr(staging, "discover", lambda *_a, **_k: None)
    return seen


def _edit(path: Path, edits: list[MaterialEdit]) -> abmatt_edit.EditResult:
    return edit_materials(
        path, edits, executable=path.parent / "abmatt", wimgt=path.parent / "wimgt"
    )


def test_selectors_are_anchored_and_escaped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = _info(("mat.001", 0, "inside", "road"), ("matX001", 0, "inside", "grass"))
    after = _info(("mat.001", 1, "inside", "road"), ("matX001", 0, "inside", "grass"))
    seen = _scripted(
        monkeypatch, [(0, before, {}), (0, "Wrote", {"in.brres": b"bresNEW"}), (0, after, {})]
    )
    _edit(_archive(tmp_path, b"bresOLD"), [MaterialEdit("mat.001", "course", xlu=True)])
    assert seen[1]["edit.txt"] == "set material xlu:true for ^mat\\.001$ in model ^course$\n"


def test_only_changed_fields_are_written(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    after = _info(("road", 0, "all", "road"), ("grass", 0, "inside", "grass"))
    seen = _scripted(
        monkeypatch, [(0, PLAIN, {}), (0, "Wrote", {"in.brres": b"bresNEW"}), (0, after, {})]
    )
    _edit(_archive(tmp_path, b"bresOLD"), [MaterialEdit("road", "course", xlu=False, cull="all")])
    assert seen[1]["edit.txt"] == "set material cullmode:all for ^road$ in model ^course$\n"


@pytest.mark.parametrize(
    ("edit_reply", "after", "reason"),
    [
        ((0, "\n", {}), PLAIN, "did not change"),
        ((0, "Wrote", {"in.brres": b"SENT"}), PLAIN, "no valid"),
        ((0, "Wrote", {"in.brres": b"bresNEW"}), PLAIN, "does not show"),
        (
            (0, "Wrote", {"in.brres": b"bresNEW"}),
            _info(("road", 1, "inside", "road")),
            "does not show",
        ),
        ((0, "ERROR: File in.brres already exists!", {}), PLAIN, "ERROR"),
        ((1, "RuntimeError: No items found in selection!", {}), PLAIN, "exited 1"),
    ],
    ids=["no write", "not brres", "after unchanged", "material lost", "error text", "exit 1"],
)
def test_edit_failures_leave_the_file_untouched(
    edit_reply: tuple[int, str, dict[str, bytes]],
    after: str,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _scripted(monkeypatch, [(0, PLAIN, {}), edit_reply, (0, after, {})])
    path = _archive(tmp_path, b"bresOLD")
    with pytest.raises(AbmattError, match=reason):
        _edit(path, [MaterialEdit("road", "course", xlu=True)])
    assert path.read_bytes() == b"bresOLD" and not list(path.parent.glob("*.bak"))


# --- paste_material ---------------------------------------------------------------------------


def test_paste_through_the_fake_reports_removed_textures(fake_tools_path, tmp_path: Path) -> None:
    src = _archive(tmp_path, fake_abmatt.EDIT_MARKER, "donor.brres")
    dst = _archive(tmp_path, fake_abmatt.MARKER, "course_model.brres")
    result = paste_material(MaterialRef(src, "course", "road"), MaterialRef(dst, "course", "grass"))
    assert result.path == dst and result.removed_textures == ("grass",)
    assert (
        all(w.startswith("Vertex course_") for w in result.warnings) and len(result.warnings) == 2
    )
    grass = next(m for m in result.materials if m.material == "grass")
    assert (grass.xlu, grass.cull, grass.layers) == (True, "inside", ("road",))
    assert (
        dst.read_bytes() == fake_abmatt.PASTE_MARKER and src.read_bytes() == fake_abmatt.EDIT_MARKER
    )
    assert [c["argv"][-1] for c in fake_tools_path.calls()] == ["info", "info", "-o", "info"]


@pytest.mark.parametrize(
    ("copy", "onto", "reason"),
    [
        (("course", "nothing"), ("course", "grass"), "no material 'nothing'"),
        (("course", "road"), ("map", "grass"), "no material 'grass' in model 'map'"),
    ],
    ids=["missing in source", "missing in target"],
)
def test_paste_refuses_missing_materials(
    copy: tuple[str, str], onto: tuple[str, str], reason: str, fake_tools_path, tmp_path: Path
) -> None:
    src = _archive(tmp_path, fake_abmatt.EDIT_MARKER, "donor.brres")
    dst = _archive(tmp_path, fake_abmatt.MARKER)
    with pytest.raises(AbmattError, match=reason):
        paste_material(MaterialRef(src, *copy), MaterialRef(dst, *onto))
    assert all("-f" not in call["argv"] for call in fake_tools_path.calls())  # never pasted
    assert dst.read_bytes() == fake_abmatt.MARKER


def test_pasting_a_material_onto_itself_is_refused(fake_tools_path, tmp_path: Path) -> None:
    path = _archive(tmp_path)
    with pytest.raises(AbmattError, match="onto itself"):
        paste_material(MaterialRef(path, "course", "road"), MaterialRef(path, "course", "road"))
    assert fake_tools_path.calls() == []


def test_paste_commands_name_each_archive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    after = _info(("road", 0, "inside", "road"), ("grass", 0, "inside", "road"))
    seen = _scripted(
        monkeypatch,
        [(0, PLAIN, {}), (0, PLAIN, {}), (0, "Wrote", {"dst.brres": b"bresNEW"}), (0, after, {})],
    )
    path = _archive(tmp_path, b"bresOLD")
    result = paste_material(
        MaterialRef(path, "course", "road"),
        MaterialRef(path, "course", "grass"),
        executable=tmp_path / "abmatt",
        wimgt=tmp_path / "wimgt",
    )
    assert seen[2]["paste.txt"] == (
        "copy material for ^road$ in src.brres model ^course$\n"
        "paste material for ^grass$ in dst.brres model ^course$\n"
    )
    assert result.removed_textures == () and path.read_bytes() == b"bresNEW"


@pytest.mark.parametrize(
    ("paste_reply", "after", "reason"),
    [
        ((0, "Wrote", {"dst.brres": b"bresNEW"}), PLAIN, "does not show"),
        ((1, "abmatt.command.PasteError: No matches found in clipboard.", {}), PLAIN, "exited 1"),
        ((0, "Wrote", {"dst.brres": b"JUNK"}), PLAIN, "no valid"),
    ],
    ids=["not pasted", "paste error", "not brres"],
)
def test_paste_failures_leave_the_target_untouched(
    paste_reply: tuple[int, str, dict[str, bytes]],
    after: str,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _scripted(monkeypatch, [(0, PLAIN, {}), (0, PLAIN, {}), paste_reply, (0, after, {})])
    src, dst = _archive(tmp_path, b"bresA", "a.brres"), _archive(tmp_path, b"bresB", "b.brres")
    with pytest.raises(AbmattError, match=reason):
        paste_material(
            MaterialRef(src, "course", "road"),
            MaterialRef(dst, "course", "grass"),
            executable=tmp_path / "abmatt",
            wimgt=tmp_path / "wimgt",
        )
    assert dst.read_bytes() == b"bresB" and not list(dst.parent.glob("*.bak"))
