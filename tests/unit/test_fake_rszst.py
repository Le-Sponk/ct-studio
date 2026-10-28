"""P2-T04c: the rszst fake behaves like the real RiiStudio CLI's recorded runs.

Every case in ``tests/fakes/recordings/rszst/<version>/windows-ops.json`` (made by
``scripts/record_tool_outputs.py`` with the real rszst) is replayed against the fake through
the core runner, with the recorded fixture DAE and stand-ins for the other inputs.

The Linux help/version recordings show a different build banner and program name and exit
255 where Windows reports -1. Linux operation recordings are still missing; the Linux fake
replays the Windows operations with LF-based progress normalization, not a claim about the
real Linux converter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import fake_rszst
import record_tool_help as rth
import record_tool_outputs as rto
import rszst_cli
import tool_catalogue as tc
from fake_runtime import UNMODELLED_EXIT
from ops_replay import assert_like_recording, stand_ins

from ctstudio.core.tools.discovery import discover
from ctstudio.core.tools.registry import TOOL_BY_ID
from ctstudio.core.tools.versions import VersionCache, probe_versions

pytestmark = pytest.mark.timeout(60)

VERSION = tc.ALL_TOOLS["riistudio"].version
FOLDER = rth.RECORDINGS / "rszst" / VERSION
CASES = {case.name: case for case in rto.TOOLSETS["riistudio"][1]}
WINDOWS_EXIT = 4294967295  # exit(-1) as Windows reports it
OS_NAME = "windows" if os.name == "nt" else "linux"


def cli_records(platform_name: str = OS_NAME) -> list[dict[str, object]]:
    path = FOLDER / f"{platform_name}-cli.json"
    return json.loads(path.read_text(encoding="utf-8"))


def banner(platform_name: str) -> str:
    return str(cli_records(platform_name)[0]["stdout"]).split("\n")[2]


def for_this_os(record: dict[str, object], platform_name: str = OS_NAME) -> dict[str, object]:
    """Translate Windows operation output to our LF-based Linux fake's visible text.

    Windows emits CRLF plus progress CR. With LF on Linux, the runner strips a CR at the
    end of a progress line; this translation does not claim real Linux operation parity.
    """
    if platform_name == "windows":
        return record

    def text(value: object) -> str:
        return (
            str(value)
            .replace(banner("windows"), banner("linux"))
            .replace("rszst.exe", "rszst")
            .replace("\r\n", "\n")
        )

    code = 255 if record["exit_code"] == WINDOWS_EXIT else record["exit_code"]
    return {
        **record,
        "exit_code": code,
        "stdout": text(record["stdout"]),
        "stderr": text(record["stderr"]),
    }


def recorded_cases() -> list[object]:
    params: list[object] = []
    for record in rto.load("rszst", VERSION):
        native = CASES[str(record["case"])].native_only and os.name != "nt"
        marks = (
            [pytest.mark.skip(reason="recorded on Windows; paths differ per OS")] if native else []
        )
        params.append(pytest.param(record, id=str(record["case"]), marks=marks))
    return params


def test_every_recorded_case_is_still_in_the_case_table() -> None:
    recorded = {str(record["case"]) for record in rto.load("rszst", VERSION)}
    assert recorded == set(CASES), "re-run scripts/record_tool_outputs.py after editing the cases"


def test_recorded_dae_uses_repo_lf_line_endings() -> None:
    data = (FOLDER / "inputs" / "course.dae").read_bytes()
    assert b"\r" not in data
    assert b"\n" in data


def test_only_thread_ordered_progress_frames_are_canonicalised() -> None:
    from ops_replay import canonical_stdout

    frame = "Optimizing meshes ({} / 4)       [{}] {} %\r"
    real = (
        "Processing\r"
        + "".join(frame.format(k, "=" * k, 25 * k) for k in (0, 2, 1, 3))
        + "Done\r\n"
    )
    ordered = (
        "Processing\r" + "".join(frame.format(k, "=" * k, 25 * k) for k in range(4)) + "Done\r\n"
    )
    assert real != ordered and canonical_stdout(real) == canonical_stdout(ordered)
    assert canonical_stdout("Compiling meshes 2/4\rCompiling meshes 1/4\r") == (
        "Compiling meshes 2/4\rCompiling meshes 1/4\r"
    )
    assert canonical_stdout(real) != canonical_stdout(real.replace("Done", "Dome"))


def test_the_fake_imitates_the_catalogue_pin() -> None:
    assert fake_rszst.VERSION == VERSION


def test_operation_template_uses_its_recorded_banner_on_other_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux replays the Windows ops recording under the Linux help-recording banner."""
    monkeypatch.setattr(fake_rszst.cli, "BANNER", "DIFFERENT LINUX BANNER")
    assert fake_rszst.template("import").startswith("Processing...")
    assert "RiiStudio CLI Alpha" not in fake_rszst.template("import")


def test_linux_progress_translation_matches_lf_fake_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows' final progress CR is stripped by the runner when fake Linux emits LF."""
    from ctstudio.core.tools.process import _split

    recorded = next(r for r in rto.load("rszst", VERSION) if r["case"] == "import missing")
    expected = for_this_os(recorded, platform_name="linux")
    monkeypatch.setattr(rszst_cli, "BANNER", banner("linux"))
    monkeypatch.setattr(rszst_cli, "NEWLINE", "\n")
    outcome = fake_rszst.reply(-1, fake_rszst.template("import missing"))
    _, lines = _split(outcome.stdout.replace("\n", outcome.newline))
    assert "".join(line + "\n" for line in lines) == expected["stdout"]


def test_the_os_translation_matches_both_help_recordings() -> None:
    # The evidence for ``for_this_os``: the Windows help, translated, is the Linux help.
    for windows, linux in zip(cli_records("windows"), cli_records("linux"), strict=True):
        if os.name == "nt":
            pytest.skip("the translation only runs on Linux")
        assert for_this_os(windows)["stdout"] == linux["stdout"]
        assert for_this_os(windows)["exit_code"] == linux["exit_code"]


@pytest.mark.parametrize("record", recorded_cases())
def test_fake_matches_the_recorded_real_run(
    record: dict[str, object], fake_tools_path, tmp_path: Path
) -> None:
    root = tmp_path / "ct ops é"
    root.mkdir()
    case = CASES[str(record["case"])]
    fake = rto.run_case(case, fake_tools_path.resolve, root, stand_ins(record, FOLDER / "inputs"))
    assert_like_recording(fake, for_this_os(record))


@pytest.mark.parametrize("record", cli_records(), ids=lambda record: " ".join(record["argv"]))
def test_fake_help_and_version_equal_this_os_recordings(
    record: dict[str, object], fake_tools_path, tmp_path: Path
) -> None:
    fake = rth.capture(fake_tools_path.resolve("rszst"), record["argv"], cwd=tmp_path, roots={})  # type: ignore[arg-type]
    assert (fake["exit_code"], fake["stdout"], fake["stderr"]) == (
        record["exit_code"],
        record["stdout"],
        record["stderr"],
    )


def _dae_with_meshes(count: int) -> bytes:
    text = (FOLDER / "inputs" / "course.dae").read_bytes().decode("utf-8")
    start = text.index("<node ")
    end = text.index("</visual_scene>")
    nodes = text[start:end].split("</node>")[:count]
    return (text[:start] + "</node>".join(nodes) + "</node>\n" + text[end:]).encode("utf-8")


@pytest.mark.parametrize(
    ("argv", "dae"),
    [
        (("import-brres", "course.dae", "o.brres", "--scale", "2"), None),  # real, unmodelled
        (("import-brres", "course.dae", "o.brres", "-v"), None),  # adds log lines nobody measured
        (("import-bmd", "course.dae", "o.bmd"), None),  # a real subcommand the fake lacks
        (("import-brres", "course.fbx", "o.brres"), None),  # only DAE was recorded
        (("import-bres", "course.dae"), None),  # clap suggests similar subcommands
        (("import-brres", "course.dae", "o.brres", "--", "x"), None),  # clap's escape
        (("import-brres", "course.dae", "o.brres"), 3),  # mesh counts nobody recorded
        (("dump-presets", "real.brres", "p"), None),  # a real BRRES, not one the fake wrote
    ],
    ids=lambda value: " ".join(value) if isinstance(value, tuple) else str(value),
)
def test_unmodelled_behaviour_fails_loudly(
    argv: tuple[str, ...], dae: int | None, fake_tools_path, tmp_path: Path
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    full = (FOLDER / "inputs" / "course.dae").read_bytes()
    for name in ("course.dae", "course.fbx"):
        (work / name).write_bytes(full if dae is None else _dae_with_meshes(dae))
    (work / "real.brres").write_bytes(b"bres\xfe\xff\x00\x00" + bytes(56))
    before = sorted(path.name for path in work.iterdir())
    fake = rth.capture(fake_tools_path.resolve("rszst"), argv, cwd=work, roots={})
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert "not modelled" in str(fake["stderr"])
    assert fake["stdout"] == ""
    assert sorted(path.name for path in work.iterdir()) == before, "nothing written"
    assert [call["argv"] for call in fake_tools_path.calls()] == [list(argv)], "still logged"


@pytest.mark.parametrize("change", [b"<float_array", b"<node "])
def test_changed_dae_is_not_silently_converted(
    change: bytes, fake_tools_path, tmp_path: Path
) -> None:
    """Only the actual recorded fixture was measured, not other coordinate/topology values."""
    original = (FOLDER / "inputs" / "course.dae").read_bytes()
    assert change in original
    altered = original.replace(change, change + b" ", 1)
    (tmp_path / "course.dae").write_bytes(altered)
    fake = rth.capture(
        fake_tools_path.resolve("rszst"),
        ["import-brres", "course.dae", "o.brres"],
        cwd=tmp_path,
        roots={},
    )
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert not (tmp_path / "o.brres").exists()


@pytest.mark.parametrize("name", ["vrcorn2", "map", "bad-name"])
def test_unrecorded_model_name_is_refused(name: str, fake_tools_path, tmp_path: Path) -> None:
    (tmp_path / "course.dae").write_bytes((FOLDER / "inputs" / "course.dae").read_bytes())
    fake = rth.capture(
        fake_tools_path.resolve("rszst"),
        ["import-brres", "course.dae", "o.brres", "--model-name", name],
        cwd=tmp_path,
        roots={},
    )
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert not (tmp_path / "o.brres").exists()


@pytest.mark.parametrize(("name", "change"), [("road.png", "missing"), ("water.png", "changed")])
def test_import_refuses_unrecorded_texture_input(
    name: str, change: str, fake_tools_path, tmp_path: Path
) -> None:
    inputs = FOLDER / "inputs"
    (tmp_path / "course.dae").write_bytes((inputs / "course.dae").read_bytes())
    for texture in ("road.png", "grass.png", "fence.png", "water.png"):
        if texture != name or change != "missing":
            data = (inputs / texture).read_bytes()
            (tmp_path / texture).write_bytes(data + b"X" if texture == name else data)
    fake = rth.capture(
        fake_tools_path.resolve("rszst"),
        ["import-brres", "course.dae", "o.brres"],
        cwd=tmp_path,
        roots={},
    )
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert not (tmp_path / "o.brres").exists()


@pytest.mark.parametrize(
    "extra",
    [
        ("--model-name", "vrcorn", "--mipmaps", "--min-mip", "64"),
        ("--model-name", "vrcorn", "--preset-path", "nothere"),
    ],
)
def test_import_refuses_unrecorded_option_combinations(
    extra: tuple[str, ...], fake_tools_path, tmp_path: Path
) -> None:
    inputs = FOLDER / "inputs"
    for name in ("course.dae", "road.png", "grass.png", "fence.png", "water.png"):
        (tmp_path / name).write_bytes((inputs / name).read_bytes())
    fake = rth.capture(
        fake_tools_path.resolve("rszst"),
        ["import-brres", "course.dae", "o.brres", *extra],
        cwd=tmp_path,
        roots={},
    )
    assert fake["exit_code"] == UNMODELLED_EXIT
    assert not (tmp_path / "o.brres").exists()


@pytest.mark.parametrize("kind", ["brres", "json", "bin", "preset"])
def test_tampered_fake_formats_are_refused(kind: str, fake_tools_path, tmp_path: Path) -> None:
    inputs = FOLDER / "inputs"
    for name in ("course.dae", "road.png", "grass.png", "fence.png", "water.png"):
        (tmp_path / name).write_bytes((inputs / name).read_bytes())
    exe = fake_tools_path.resolve("rszst")

    def invoke(*argv: str) -> dict[str, object]:
        return rth.capture(exe, argv, cwd=tmp_path, roots={})

    assert invoke("import-brres", "course.dae", "o.brres")["exit_code"] == 0
    if kind == "brres":
        target, command = tmp_path / "o.brres", ("brres-to-json", "o.brres", "o.json")
    else:
        assert invoke("brres-to-json", "o.brres", "o.json")["exit_code"] == 0
        if kind == "preset":
            assert invoke("dump-presets", "o.brres", "presets")["exit_code"] == 0
            target = tmp_path / "presets" / "road.rspreset"
            command = ("import-brres", "course.dae", "p.brres", "--preset-path", "presets")
        else:
            target = tmp_path / f"o.{kind}"
            command = ("json-to-brres", "o.json", "b.brres")
    target.write_bytes(target.read_bytes() + b"TAMPERED")
    fake = invoke(*command)
    assert fake["exit_code"] == UNMODELLED_EXIT
    expected = "o.json" if kind == "brres" else "p.brres" if kind == "preset" else "b.brres"
    assert not (tmp_path / expected).exists()


def test_linux_absolute_path_is_unmodelled_without_a_native_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows prebuilt's ANSI argv failure says nothing about Linux source builds."""
    from types import SimpleNamespace

    source = tmp_path / "course.dae"
    source.write_bytes((FOLDER / "inputs" / "course.dae").read_bytes())
    monkeypatch.setattr(fake_rszst, "os", SimpleNamespace(name="posix"))
    with pytest.raises(fake_rszst.Unmodelled):
        fake_rszst._import_failure(str(source), "")


def test_fake_output_bytes_use_this_os_line_ends(fake_tools_path, tmp_path: Path) -> None:
    # Measured: the Windows build writes CRLF, the Linux build LF. The runner hides CR, so
    # read the raw pipe (tests may spawn directly; src/ may not).
    exe = str(fake_tools_path.resolve("rszst"))
    raw = subprocess.run([exe, "--version"], cwd=tmp_path, capture_output=True, check=False)  # noqa: S603 - our fake
    line_end = b"\r\n" if os.name == "nt" else b"\n"
    assert raw.stdout.endswith(b"::" + line_end)
    assert raw.stdout.count(b"\n") == raw.stdout.count(line_end)


def test_discovery_and_version_probe_find_the_fake(fake_tools_path, tmp_path: Path) -> None:
    spec = TOOL_BY_ID["rszst"]
    location = discover(spec)
    assert location is not None
    assert location.path.samefile(fake_tools_path.resolve("rszst"))
    [result] = probe_versions([(spec, location)], cache=VersionCache(tmp_path / "versions.json"))
    assert result.location.version == VERSION
    assert [call["argv"] for call in fake_tools_path.calls()] == [["--version"]]


# Measured with the real rszst 5.11.5 (Windows): which typo gets clap's "a similar argument
# exists" tip. clap suggests the closest long option when the Jaro similarity exceeds 0.7.
MEASURED_SUGGESTIONS = {
    "--modl": "--model-name",
    "--mipmap": "--mipmaps",
    "--tnt": "--tint",
    "--scal": "--scale",
    "--verbos": "--verbose",
    "--x": "--max-mip",
    "--model": "--model-name",
    "--mod": "--model-name",
    "--presets": "--preset-path",
    "--bogus-flag": None,
    "--cull": "--cull-invalid",
    "--min": "--min-mip",
    "--nametag": None,
    "--tint-color": "--tint",
    "--fuse": "--fuse-vertices",
    "--help-me": "--help",
}


@pytest.mark.parametrize(("typed", "expected"), MEASURED_SUGGESTIONS.items())
def test_option_suggestions_follow_the_measured_clap_rule(typed: str, expected: str | None) -> None:
    command = rszst_cli.COMMANDS["import-brres"]
    assert rszst_cli.suggest(typed, command) == expected
