"""P2-T05e: the typed rszst adapter (``ctstudio.core.tools.riistudio``) through the fake.

The adapter copies inputs into a private staging folder under fixed ASCII names and runs
rszst there with bare names, because the Windows build reads argv through the ANSI code
page: any non-ASCII path, relative or absolute, fails or is silently ignored (measured).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.tools.staging import ToolRun

INPUTS = (
    Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "rszst" / "5.11.5" / "inputs"
)
TEXTURES = ("road.png", "grass.png", "fence.png", "water.png")
pytestmark = pytest.mark.timeout(60)


def _project(tmp_path: Path, *, move_fence: str | None = None) -> Path:
    """The recorded DAE and textures in a folder whose path is not ASCII."""
    folder = tmp_path / "piste é"
    folder.mkdir()
    shutil.copyfile(INPUTS / "course.dae", folder / "course.dae")
    for name in TEXTURES:
        target = folder / (move_fence if name == "fence.png" and move_fence else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(INPUTS / name, target)
    return folder / "course.dae"


def _only_call(fake_tools_path) -> dict[str, object]:
    [call] = fake_tools_path.calls()
    return call


def test_import_runs_bare_ascii_names_in_a_private_stage(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import import_brres

    dae = _project(tmp_path)
    out = import_brres(dae, dae.parent / "course_model.brres", model_name="course")
    assert out == dae.parent / "course_model.brres" and out.read_bytes()[:4] == b"bres"
    call = _only_call(fake_tools_path)
    assert call["argv"] == ["import-brres", "model.dae", "out.brres", "--model-name", "course"]
    stage = Path(str(call["cwd"]))
    assert stage.name.startswith("ctstudio-rszst-") and not stage.exists()


def test_import_with_mipmaps_and_textures_subfolder(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import import_brres

    dae = _project(tmp_path, move_fence="textures/fence.png")
    import_brres(dae, tmp_path / "m.brres", model_name="course", min_mip=64)
    argv = _only_call(fake_tools_path)["argv"]
    assert isinstance(argv, list)
    assert argv[-3:] == ["--mipmaps", "--min-mip", "64"]


def test_presets_round_trip(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import dump_presets, import_brres

    dae = _project(tmp_path)
    model = import_brres(dae, tmp_path / "course_model.brres", model_name="course")
    presets = dump_presets(model, tmp_path / "captured é")
    assert [path.name for path in presets] == [
        "fence.rspreset",
        "grass.rspreset",
        "road.rspreset",
        "water.rspreset",
    ]
    again = import_brres(
        dae, tmp_path / "again.brres", model_name="course", presets=presets[0].parent
    )
    assert again.read_bytes()[:4] == b"bres"
    assert fake_tools_path.calls()[-1]["argv"][-2:] == ["--preset-path", "presets"]


@pytest.mark.parametrize("make", [False, True], ids=["missing folder", "empty folder"])
def test_import_refuses_preset_folder_rszst_would_ignore(
    make: bool, fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, import_brres

    folder = tmp_path / "presets"
    if make:
        folder.mkdir()
        (folder / "notes.txt").write_bytes(b"not a preset")
    with pytest.raises(RiiStudioError, match=r"no \.rspreset"):
        import_brres(_project(tmp_path), tmp_path / "o.brres", model_name="course", presets=folder)
    assert fake_tools_path.calls() == []


def test_dump_presets_keeps_other_files_and_refuses_collisions(
    fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, dump_presets, import_brres

    model = import_brres(_project(tmp_path), tmp_path / "m.brres", model_name="course")
    folder = tmp_path / "captured"
    folder.mkdir()
    (folder / "notes.txt").write_bytes(b"mine")
    (folder / "road.rspreset").write_bytes(b"old")
    with pytest.raises(RiiStudioError, match="already exists"):
        dump_presets(model, folder)
    assert (folder / "road.rspreset").read_bytes() == b"old"
    written = dump_presets(model, folder, overwrite=True)
    assert len(written) == 4 and (folder / "notes.txt").read_bytes() == b"mine"
    assert (folder / "road.rspreset").read_bytes() != b"old"


@pytest.mark.parametrize(
    ("reference", "reason"),
    [
        ("fé.png", "non-ASCII"),
        ("../fence.png", "outside"),
        ("missing.png", "missing"),
        ("C:/textures/fence.png", "outside"),
    ],
)
def test_import_refuses_textures_rszst_would_silently_replace(
    reference: str, reason: str, fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, import_brres

    dae = _project(tmp_path)
    text = dae.read_bytes().replace(b"<init_from>fence.png<", f"<init_from>{reference}<".encode())
    dae.write_bytes(text)
    with pytest.raises(RiiStudioError, match=reason):
        import_brres(dae, tmp_path / "o.brres", model_name="course")
    assert fake_tools_path.calls() == []
    assert not (tmp_path / "o.brres").exists()


def test_import_refuses_a_missing_texture_file(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, import_brres

    dae = _project(tmp_path, move_fence="unused/fence.png")
    with pytest.raises(RiiStudioError, match=r"missing.*fence\.png"):
        import_brres(dae, tmp_path / "o.brres", model_name="course")
    assert fake_tools_path.calls() == []


def test_import_refuses_unreadable_dae_and_bad_model_name(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, import_brres

    junk = tmp_path / "junk.dae"
    junk.write_bytes(b"not a track file\n")
    with pytest.raises(RiiStudioError, match="COLLADA"):
        import_brres(junk, tmp_path / "o.brres", model_name="course")
    with pytest.raises(RiiStudioError, match="model name"):
        import_brres(_project(tmp_path), tmp_path / "o.brres", model_name="cours é")
    assert fake_tools_path.calls() == []


def test_existing_destination_needs_overwrite_and_keeps_a_backup(
    fake_tools_path, tmp_path: Path
) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, import_brres

    dae = _project(tmp_path)
    dest = tmp_path / "course_model.brres"
    dest.write_bytes(b"edited in BrawlCrate")
    with pytest.raises(RiiStudioError, match="already exists"):
        import_brres(dae, dest, model_name="course")
    assert fake_tools_path.calls() == [] and dest.read_bytes() == b"edited in BrawlCrate"
    import_brres(dae, dest, model_name="course", overwrite=True)
    assert dest.read_bytes()[:4] == b"bres"
    [backup] = tmp_path.glob("course_model.brres.*.bak")
    assert backup.read_bytes() == b"edited in BrawlCrate"


def test_json_round_trip_keeps_the_bin_sidecar(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import (
        RiiStudioError,
        brres_to_json,
        import_brres,
        json_to_brres,
    )

    model = import_brres(_project(tmp_path), tmp_path / "m.brres", model_name="course")
    json_path, bin_path = brres_to_json(model, tmp_path / "j é" / "model.json")
    assert bin_path == json_path.with_suffix(".bin")
    assert json_path.read_bytes()[:1] == b"{" and bin_path.read_bytes()[:4] == b"RBUF"
    back = json_to_brres(json_path, tmp_path / "back.brres")
    assert back.read_bytes()[:4] == b"bres"
    bin_path.unlink()
    with pytest.raises(RiiStudioError, match=r"model\.bin"):
        json_to_brres(json_path, tmp_path / "again.brres")
    assert len(fake_tools_path.calls()) == 3


def test_tool_failure_is_typed_with_details(fake_tools_path, tmp_path: Path) -> None:
    from ctstudio.core.tools.riistudio import RiiStudioError, dump_presets

    junk = tmp_path / "junk.brres"
    junk.write_bytes(b"bres but not really")
    with pytest.raises(RiiStudioError) as caught:
        dump_presets(junk, tmp_path / "p")
    assert caught.value.exit_code == 121 and "not modelled" in str(caught.value.details)
    assert not (tmp_path / "p").exists()


@pytest.mark.parametrize(
    ("exit_code", "write"),
    [(0xFFFFFFFF, True), (255, True), (0, False)],
    ids=["windows exit -1", "linux exit -1", "exit 0 without output"],
)
def test_exit_minus_one_and_silent_no_output_are_failures(
    exit_code: int, write: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ctstudio.core.tools import riistudio

    def fake_run(cmd: object, cwd: Path, **_: object) -> ToolRun:
        del cmd
        if write:
            (cwd / "out.brres").write_bytes(b"bres")
        return ToolRun(exit_code, "", "")

    monkeypatch.setattr(riistudio, "run_collecting", fake_run)
    with pytest.raises(riistudio.RiiStudioError) as caught:
        riistudio.import_brres(
            _project(tmp_path), tmp_path / "o.brres", model_name="course", executable=tmp_path / "x"
        )
    assert caught.value.exit_code == exit_code
    assert not (tmp_path / "o.brres").exists()
