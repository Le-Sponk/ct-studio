"""P2-T05e2: the typed ABMatt conversion adapter (``ctstudio.core.tools.abmatt``) via the fake.

ABMatt names the MDL0 after the source stem, adds minimap bones only when the destination
name contains ``map``, reports lost textures or a missing wimgt as text at exit 0, and can
crash after writing (CJK path). The adapter stages fixed names, puts wimgt on PATH, treats
those texts as failures and confirms the result with ``-c info``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.tools.staging import ToolRun

INPUTS = (
    Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "abmatt" / "1.3.2" / "inputs"
)
TEXTURES = ("road.png", "grass.png", "fence.png", "water.png")
INFO = (
    ">course->road\txlu:0 cull:inside\n  road:\tScale:(1.0, 1.0) Rot:0.0 Trans:(0.0, 0.0)\n"
    ">course->grass\txlu:1 cull:none\n  grass:\tScale:(1.0, 1.0) Rot:0.0 Trans:(0.0, 0.0)\n"
)
pytestmark = pytest.mark.timeout(60)


def _project(tmp_path: Path, *, name: str = "piste 日本") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    shutil.copyfile(INPUTS / "course.dae", folder / "course.dae")
    for texture in TEXTURES:
        shutil.copyfile(INPUTS / texture, folder / texture)
    return folder / "course.dae"


def _minimap(tmp_path: Path) -> Path:
    obj = tmp_path / "carte 日本" / "drivable.obj"
    obj.parent.mkdir()
    shutil.copyfile(INPUTS / "map.obj", obj)
    return obj


# --- info parser -----------------------------------------------------------------------------


def test_parse_info_reads_model_and_materials() -> None:
    from ctstudio.core.tools.abmatt import MaterialInfo, parse_info

    assert parse_info(INFO) == (
        MaterialInfo("course", "road", xlu=False, cull="inside"),
        MaterialInfo("course", "grass", xlu=True, cull="none"),
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Wrote file 'x'\n",
        ">course->road\txlu:2 cull:inside\n",
        ">course->road\txlu:0 cull:sideways\n",
        INFO + "unexpected line\n",
    ],
    ids=["empty", "no rows", "bad xlu", "bad cull", "junk line"],
)
def test_parse_info_refuses_reports_it_cannot_fully_read(text: str) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, parse_info

    with pytest.raises(AbmattError, match="info"):
        parse_info(text)


# --- convert_model --------------------------------------------------------------------------


def test_convert_model_stages_the_model_name_and_checks_info(
    fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.abmatt import convert_model

    dae = _project(tmp_path)
    result = convert_model(
        dae, tmp_path / "sortie 日本" / "course_model.brres", model_name="course"
    )
    assert result.path.read_bytes()[:4] == b"bres"
    assert [m.material for m in result.materials] == ["road", "grass", "fence", "water"]
    assert {m.model for m in result.materials} == {"course"}
    convert, info = fake_tools_path.calls()
    assert convert["argv"] == ["convert", "course.dae", "to", "out.brres", "-o"]
    assert info["argv"] == ["-b", "out.brres", "-c", "info"]
    assert Path(str(convert["cwd"])).name.startswith("ctstudio-abmatt-")


@pytest.mark.parametrize(("move", "reason"), [("unused", "missing"), ("textures", "missing")])
def test_convert_model_refuses_textures_abmatt_would_drop(
    move: str, reason: str, fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    dae = _project(tmp_path)
    (dae.parent / move).mkdir()
    shutil.move(dae.parent / "fence.png", dae.parent / move / "fence.png")
    with pytest.raises(AbmattError, match=rf"{reason}.*fence\.png"):
        convert_model(dae, tmp_path / "o.brres", model_name="course")
    assert fake_tools_path.calls() == [] and not (tmp_path / "o.brres").exists()


@pytest.mark.parametrize("reference", ["sub/fence.png", "fé.png", "C:fence.png", "../fence.png"])
def test_convert_model_refuses_texture_paths_abmatt_cannot_stage(
    reference: str, fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    dae = _project(tmp_path)
    dae.write_bytes(
        dae.read_bytes().replace(b"<init_from>fence.png<", f"<init_from>{reference}<".encode())
    )
    with pytest.raises(AbmattError, match="plain name"):
        convert_model(dae, tmp_path / "o.brres", model_name="course")
    assert fake_tools_path.calls() == []


def test_the_source_file_name_never_names_the_model(fake_tools_path, tmp_path: Path) -> None:
    """ABMatt names the MDL0 after the source stem: a user's file name must not leak in."""
    from ctstudio.core.tools.abmatt import convert_model

    dae = _project(tmp_path)
    renamed = dae.rename(dae.with_name("my_track_v2.dae"))
    result = convert_model(renamed, tmp_path / "o.brres", model_name="course")
    assert {m.model for m in result.materials} == {"course"}
    assert fake_tools_path.calls()[0]["argv"][1] == "course.dae"


@pytest.mark.parametrize("name", ["cours é", "", "a" * 65, "course_model", "map"])
def test_convert_model_refuses_names_abmatt_would_change(
    name: str, fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    with pytest.raises(AbmattError, match="model name"):
        convert_model(_project(tmp_path), tmp_path / "o.brres", model_name=name)
    assert fake_tools_path.calls() == []


def test_convert_model_refuses_a_map_destination_name(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    with pytest.raises(AbmattError, match="map"):
        convert_model(_project(tmp_path), tmp_path / "roadmap.brres", model_name="course")
    assert fake_tools_path.calls() == []


def test_existing_destination_needs_overwrite_and_keeps_a_backup(
    fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    dest = tmp_path / "course_model.brres"
    dest.write_bytes(b"edited")
    with pytest.raises(AbmattError, match="already exists"):
        convert_model(_project(tmp_path), dest, model_name="course")
    assert fake_tools_path.calls() == []
    convert_model(_project(tmp_path, name="again"), dest, model_name="course", overwrite=True)
    [backup] = tmp_path.glob("course_model.brres.*.bak")
    assert backup.read_bytes() == b"edited" and dest.read_bytes()[:4] == b"bres"


def test_non_collada_input_is_refused(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    junk = tmp_path / "junk.dae"
    junk.write_bytes(b"not a track file\n")
    with pytest.raises(AbmattError, match="COLLADA"):
        convert_model(junk, tmp_path / "o.brres", model_name="course")
    assert fake_tools_path.calls() == []


# --- convert_minimap ------------------------------------------------------------------------


def test_convert_minimap_stages_map_names(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.abmatt import convert_minimap

    result = convert_minimap(_minimap(tmp_path), tmp_path / "out 日本" / "map_model.brres")
    assert result.path.read_bytes()[:4] == b"bres"
    assert [(m.model, m.material) for m in result.materials] == [("map", "road")]
    convert, info = fake_tools_path.calls()
    assert convert["argv"] == ["convert", "map.obj", "to", "map_model.brres", "-o"]
    assert info["argv"] == ["-b", "map_model.brres", "-c", "info"]


def test_convert_minimap_refuses_non_obj(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_minimap

    with pytest.raises(AbmattError, match="OBJ"):
        convert_minimap(_project(tmp_path), tmp_path / "map_model.brres")
    assert fake_tools_path.calls() == []


# --- failures the tool reports at exit 0, or not at all ------------------------------------------


def _scripted(
    monkeypatch: pytest.MonkeyPatch, replies: list[tuple[int, str, str, bytes | None]]
) -> None:
    from ctstudio.core.tools import abmatt

    def fake_run(cmd: object, cwd: Path, **_: object) -> ToolRun:
        del cmd
        code, stdout, stderr, write = replies.pop(0)
        if write is not None:
            (cwd / "out.brres").write_bytes(write)
        return ToolRun(code, stdout, stderr)

    monkeypatch.setattr(abmatt, "run_collecting", fake_run)


@pytest.mark.parametrize(
    ("convert", "reason"),
    [
        (
            (
                0,
                "ERROR: wimgt not found, please install Wiimms SZS Tools\nWrote file 'x'",
                "",
                b"bres",
            ),
            "wimgt",
        ),
        (
            (
                0,
                "No texture matching fence\n(FIXED): Remove reference\nWrote file 'x'",
                "",
                b"bres",
            ),
            "texture",
        ),
        ((0, "WARN: Failed to find image fence.png\nWrote file 'x'", "", b"bres"), "texture"),
        ((0, "ERROR: File x already exists!\n", "", None), "ERROR"),
        ((0, "Wrote file 'x'\n", "", None), "no valid"),
        ((0, "Wrote file 'x'\n", "", b"SENT"), "no valid"),
        ((1, "abmatt.command.NoSuchFile\n", "", None), "exited 1"),
        ((0xFFFFFFFF, "", "Failed to execute script __main__", b"bres"), "exited 4294967295"),
    ],
    ids=[
        "no wimgt",
        "texture removed",
        "image not found",
        "error text",
        "nothing written",
        "wrong magic",
        "exit 1",
        "exit -1 after writing",
    ],
)
def test_conversion_failures_are_typed_and_deliver_nothing(
    convert: tuple[int, str, str, bytes | None],
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    _scripted(monkeypatch, [convert, (0, INFO, "", None)])
    with pytest.raises(AbmattError, match=reason) as caught:
        convert_model(
            _project(tmp_path), tmp_path / "o.brres", model_name="course", executable=tmp_path / "x"
        )
    assert caught.value.details and not (tmp_path / "o.brres").exists()


def test_cjk_print_crash_after_writing_is_accepted_only_with_a_valid_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Measured: in a CJK folder ABMatt writes, then dies printing the path (exit 0)."""
    from ctstudio.core.tools.abmatt import convert_model

    crash = "Exception in thread Thread-2:\nUnicodeEncodeError: 'charmap' codec can't encode"
    _scripted(
        monkeypatch, [(0, "Converting .\\course.dae... \n", crash, b"bres"), (0, INFO, "", None)]
    )
    result = convert_model(
        _project(tmp_path), tmp_path / "o.brres", model_name="course", executable=tmp_path / "x"
    )
    assert result.path.read_bytes() == b"bres"


@pytest.mark.parametrize(
    ("info", "reason"),
    [
        ((0, INFO.replace("course", "other"), "", None), "named 'other'"),
        ((0, "", "", None), "info"),
        ((1, "Traceback", "", None), "exited 1"),
    ],
    ids=["wrong model name", "empty info", "info failed"],
)
def test_info_mismatch_or_failure_rejects_the_conversion(
    info: tuple[int, str, str, bytes | None],
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ctstudio.core.tools.abmatt import AbmattError, convert_model

    _scripted(monkeypatch, [(0, "Wrote file 'x'\n", "", b"bres"), info])
    with pytest.raises(AbmattError, match=reason):
        convert_model(
            _project(tmp_path), tmp_path / "o.brres", model_name="course", executable=tmp_path / "x"
        )
    assert not (tmp_path / "o.brres").exists()


def test_wimgt_is_put_on_the_tool_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ctstudio.core.tools import abmatt

    seen: list[object] = []

    def fake_run(
        cmd: object, cwd: Path, *, env: dict[str, str] | None = None, **_: object
    ) -> ToolRun:
        seen.append(env)
        (cwd / "out.brres").write_bytes(b"bres")
        return ToolRun(0, INFO if len(seen) == 2 else "", "")

    wimgt = tmp_path / "wiimm bin" / "wimgt.exe"
    monkeypatch.setattr(abmatt, "run_collecting", fake_run)
    abmatt.convert_model(
        _project(tmp_path),
        tmp_path / "o.brres",
        model_name="course",
        executable=tmp_path / "x",
        wimgt=wimgt,
    )
    env = seen[0]
    assert isinstance(env, dict) and env["PATH"].split(abmatt.os.pathsep)[0] == str(wimgt.parent)
