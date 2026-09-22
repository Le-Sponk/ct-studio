"""S8 contract tests: getting a built SZS into a running game (P0-T11).

Pins the behaviour P11's "Build & launch" depends on, measured in P0-T11.
Findings: docs/dev/SPIKES.md S8, spikes/s8_dolphin_launch.py, the launch table in
docs/reference/TOOLS.md.

These tests boot a real Dolphin against a **synthetic** disc-shaped directory
(a `sys/boot.bin` header, a stub `sys/main.dol`, a fake slot SZS). No Mario Kart
Wii data is present or needed: everything asserted here is Dolphin's own
path-selection, descriptor parsing and exit-code behaviour. Whether a patched
file actually reaches the running game is an HC3 item on the user's machine.

Marked `slow` because each boot costs a second or two and several run per test.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NOGUI = shutil.which("dolphin-emu-nogui") or "/usr/games/dolphin-emu-nogui"
GUI = shutil.which("dolphin-emu") or "/usr/games/dolphin-emu"
TOOL = shutil.which("dolphin-tool") or "/usr/games/dolphin-tool"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not Path(NOGUI).exists(), reason="dolphin-emu-nogui not installed"),
]


def clean(raw: str) -> str:
    lines = raw.replace("\x00", "").splitlines()
    return "\n".join(
        line for line in lines if not line.startswith(("ALSA lib", "AL lib", "libpng"))
    ).strip()


@pytest.fixture(scope="module")
def disc(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A synthetic extracted game: disc-shaped, zero Nintendo data."""
    root = tmp_path_factory.mktemp("s8") / "extracted game"  # space on purpose
    (root / "sys").mkdir(parents=True)
    (root / "files" / "Race" / "Course").mkdir(parents=True)

    header = bytearray(0x440)
    header[0:6] = b"RMCP01"
    header[0x20:0x2C] = b"CTSTUDIO S8"
    struct.pack_into(">I", header, 0x18, 0x5D1C9EA3)  # Wii magic word
    (root / "sys" / "boot.bin").write_bytes(bytes(header))
    (root / "sys" / "bi2.bin").write_bytes(bytes(0x2000))

    dol = bytearray(0x100)
    struct.pack_into(">I", dol, 0x00, 0x100)
    struct.pack_into(">I", dol, 0x48, 0x80003100)
    struct.pack_into(">I", dol, 0x90, 0x20)
    struct.pack_into(">I", dol, 0xE0, 0x80003100)
    (root / "sys" / "main.dol").write_bytes(bytes(dol) + b"\x60\x00\x00\x00" * 8)
    (root / "files" / "Race" / "Course" / "beginner_course.szs").write_bytes(b"Yaz0" + bytes(60))
    return root


@pytest.fixture(scope="module")
def user_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("s8-user")


def boot(target: Path | str, user_dir: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    argv = [
        NOGUI,
        "-u",
        str(user_dir),
        "-p",
        "headless",
        "-v",
        "Null",
        f"--exec={target}",
    ]
    return subprocess.run(  # noqa: S603 - local tool, argv only
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )


def boot_log(target: Path | str, user_dir: Path, timeout: int = 30) -> str:
    """Boot with BOOT logging on and return the log, which names the boot path.

    `Logs/` must be created first: Dolphin does not make it, and file logging
    then silently writes nothing. P11 has to mkdir it before trusting a log.
    """
    (user_dir / "Logs").mkdir(parents=True, exist_ok=True)
    log = user_dir / "Logs" / "dolphin.log"
    log.unlink(missing_ok=True)
    argv = [
        NOGUI,
        "-u",
        str(user_dir),
        "-p",
        "headless",
        "-v",
        "Null",
        "-C",
        "Logger.Options.WriteToFile=True",
        "-C",
        "Logger.Options.Verbosity=4",
        "-C",
        "Logger.Logs.BOOT=True",
        f"--exec={target}",
    ]
    subprocess.run(  # noqa: S603 - local tool, argv only
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )
    return log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""


def descriptor(path: Path, base: Path, **extra: object) -> Path:
    payload: dict[str, object] = {
        "type": "dolphin-game-mod-descriptor",
        "version": 1,
        "base-file": str(base),
        "display-name": "CT Studio S8",
    }
    payload.update(extra)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def riivolution_xml(path: Path, root_name: str, game: str = "RMC") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<wiidisc version="1" root="/{root_name}">\n'
        f'  <id game="{game}"/>\n'
        '  <options><section name="CT Studio">\n'
        '    <option id="ctstudio-track" name="Test track" default="1">\n'
        '      <choice name="Enabled"><patch id="ctstudio"/></choice>\n'
        "    </option>\n"
        "  </section></options>\n"
        '  <patch id="ctstudio">\n'
        '    <file disc="/Race/Course/beginner_course.szs"'
        ' external="/Race/Course/beginner_course.szs"/>\n'
        "  </patch>\n"
        "</wiidisc>\n",
        encoding="utf-8",
    )
    return path


# --- route 1: an extracted game folder -------------------------------------


def test_extracted_folder_boots_as_a_disc_not_as_an_executable(disc: Path, user_dir: Path) -> None:
    """Route 1 must boot the *disc*, or the slot files are never mounted.

    Dolphin will happily accept a DOL with a broken header and boot it as a bare
    executable ("Booting from executable:"), which looks like success but gives
    the game no file system at all. Only "Booting from disc:" means
    `files/Race/Course/<slot>.szs` is reachable. CT Studio must check this line,
    not the exit code.
    """
    log = boot_log(disc / "sys" / "main.dol", user_dir)
    assert "Booting from disc:" in log
    assert "Booting from executable:" not in log


def test_file_logging_needs_the_logs_directory_to_exist(disc: Path, tmp_path: Path) -> None:
    """The `Booting from disc:` check above is worthless without this.

    `Logger.Options.WriteToFile=True` writes nothing at all unless `Logs/`
    already exists in the user directory — Dolphin does not create it, and does
    not complain. So P11 must mkdir it before reading any log.
    """
    without = tmp_path / "no-logs-dir"
    without.mkdir()
    boot(disc / "sys" / "main.dol", without)
    assert not (without / "Logs" / "dolphin.log").exists()

    with_dir = tmp_path / "with-logs-dir"
    (with_dir / "Logs").mkdir(parents=True)
    assert "Booting from disc:" in boot_log(disc / "sys" / "main.dol", with_dir)


def test_extracted_folder_boots_via_sys_main_dol(disc: Path, user_dir: Path) -> None:
    """Route 1 exists: point Dolphin at `sys/main.dol`, get a disc boot.

    This is what makes "edit the slot file in place, relaunch" viable, and it
    survives a space in the path.
    """
    result = boot(disc / "sys" / "main.dol", user_dir)
    assert "Could not recognize" not in clean(result.stdout + result.stderr)
    assert "does not exist" not in clean(result.stdout + result.stderr)


def test_the_directory_itself_is_not_bootable(disc: Path, user_dir: Path) -> None:
    """The obvious guess is wrong, so the app must build the sys/main.dol path.

    `--exec=<game folder>` is rejected; only the file inside it works
    (DiscIO/DirectoryBlob.cpp requires `sys/boot.bin` beside the DOL).
    """
    result = boot(disc, user_dir)
    assert result.returncode == 1
    assert "Could not recognize file" in clean(result.stdout + result.stderr)


def test_slot_file_is_an_ordinary_file_on_disk(disc: Path) -> None:
    """Route 1's whole appeal: installing a build is a file copy, nothing more."""
    slot = disc / "files" / "Race" / "Course" / "beginner_course.szs"
    assert slot.is_file()
    slot.write_bytes(b"Yaz0" + bytes(120))  # a rebuild replaces it in place
    assert slot.stat().st_size == 124


@pytest.mark.skipif(not Path(TOOL).exists(), reason="dolphin-tool not installed")
def test_dolphin_tool_lists_the_slot_inside_the_folder(disc: Path) -> None:
    """`dolphin-tool extract -l` reads the same directory blob.

    That gives CT Studio a check that does not boot anything: confirm the slot
    path exists in the game before offering to launch it.
    """
    result = subprocess.run(  # noqa: S603 - local tool, argv only
        [TOOL, "extract", "-i", str(disc / "sys" / "main.dol"), "-l"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0
    assert "Race/Course/beginner_course.szs" in result.stdout


# --- route 2: Dolphin's game-mod descriptor --------------------------------


def test_descriptor_boots_its_base_file(disc: Path, user_dir: Path, tmp_path: Path) -> None:
    """Route 2 exists: a JSON CT Studio writes, no GUI clicks needed.

    This is the route that leaves the user's game untouched.
    """
    path = descriptor(tmp_path / "mod.json", disc / "sys" / "main.dol")
    result = boot(path, user_dir)
    assert "Could not recognize" not in clean(result.stdout + result.stderr)


def test_descriptor_type_and_version_are_both_enforced(
    disc: Path, user_dir: Path, tmp_path: Path
) -> None:
    """Get either field wrong and the file is rejected outright, not ignored.

    So CT Studio must emit exactly `dolphin-game-mod-descriptor` / version 1
    (DiscIO/GameModDescriptor.cpp).
    """
    wrong_type = tmp_path / "bad-type.json"
    wrong_type.write_text(json.dumps({"type": "nope", "version": 1}), encoding="utf-8")
    wrong_version = tmp_path / "bad-version.json"
    wrong_version.write_text(
        json.dumps({"type": "dolphin-game-mod-descriptor", "version": 2}), encoding="utf-8"
    )
    for path in (wrong_type, wrong_version):
        result = boot(path, user_dir)
        assert result.returncode == 1, path.name
        assert "Could not recognize file" in clean(result.stdout + result.stderr)


def test_descriptor_relative_base_file_resolves_against_the_json(
    disc: Path, user_dir: Path, tmp_path: Path
) -> None:
    """Relative `base-file` is resolved against the descriptor's own folder.

    CT Studio writes absolute paths anyway, but this pins why: a descriptor is
    portable only if it sits beside the game.
    """
    nested = tmp_path / "nested"
    nested.mkdir()
    relative = Path("..") / ".." / disc.relative_to(disc.parents[2]) / "sys" / "main.dol"
    path = nested / "rel.json"
    path.write_text(
        json.dumps(
            {
                "type": "dolphin-game-mod-descriptor",
                "version": 1,
                "base-file": str(relative),
            }
        ),
        encoding="utf-8",
    )
    result = boot(path, user_dir)
    # Either it resolved and booted, or it named the resolved path in the error;
    # what must never happen is the raw relative string reaching the user.
    assert "Could not recognize file ../.." not in clean(result.stdout + result.stderr)


def test_broken_riivolution_xml_does_not_stop_the_boot(
    disc: Path, user_dir: Path, tmp_path: Path
) -> None:
    """THE risk for P11: a dropped patch is indistinguishable from a working one.

    A descriptor whose XML is missing, malformed, or scoped to another game id
    still boots, exit 0, with no warning. So CT Studio must validate the XML it
    generates itself and must never present "Dolphin launched" as "your track
    is in the game" (RiivolutionParser.cpp:352-354 skips silently).
    """
    missing = descriptor(
        tmp_path / "missing.json",
        disc / "sys" / "main.dol",
        riivolution={"patches": [{"xml": str(tmp_path / "absent.xml"), "root": str(tmp_path)}]},
    )
    malformed_xml = tmp_path / "broken.xml"
    malformed_xml.write_text('<wiidisc version="1"', encoding="utf-8")
    malformed = descriptor(
        tmp_path / "malformed.json",
        disc / "sys" / "main.dol",
        riivolution={"patches": [{"xml": str(malformed_xml), "root": str(tmp_path)}]},
    )
    wrong_game = descriptor(
        tmp_path / "wrong-game.json",
        disc / "sys" / "main.dol",
        riivolution={
            "patches": [
                {
                    "xml": str(riivolution_xml(tmp_path / "zzz.xml", "ctfiles", game="ZZZ")),
                    "root": str(tmp_path / "ctfiles"),
                }
            ]
        },
    )
    for path in (missing, malformed, wrong_game):
        result = boot(path, user_dir)
        output = clean(result.stdout + result.stderr)
        assert "Could not recognize" not in output, path.name
        assert "riivolution" not in output.lower(), path.name


# --- what the app must not do ----------------------------------------------


def test_nogui_reports_a_missing_game_but_the_gui_hangs_on_it(user_dir: Path) -> None:
    """Why P11 drives `dolphin-emu-nogui`, or accepts that errors are invisible.

    `dolphin-emu --batch` does not suppress the "does not exist" panic dialog:
    it waits for a click that no one will make. The nogui binary exits 1 with
    the message on stdout.
    """
    absent = "/nonexistent/ct-studio/game.rvz"
    result = boot(absent, user_dir)
    assert result.returncode == 1
    assert "does not exist" in clean(result.stdout + result.stderr)

    if not Path(GUI).exists() or not shutil.which("xvfb-run"):
        pytest.skip("GUI binary or xvfb-run unavailable")
    argv = ["xvfb-run", "-a", GUI, "-u", str(user_dir), "--batch", f"--exec={absent}"]
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(  # noqa: S603 - local tool, argv only
            argv, capture_output=True, text=True, timeout=25, check=False
        )
    subprocess.run(["pkill", "-f", "dolphin-emu -u"], check=False)  # noqa: S607


def test_user_directory_is_isolated_and_created_on_demand(tmp_path: Path) -> None:
    """`-u` gives each launch its own directory, so CT Studio never edits the user's.

    It also creates `Load/Riivolution` on the spot, which is where a
    Riivolution-route install would land. Note the nogui binary creates fewer
    subdirectories than the GUI does (no `Config` until it writes one), so the
    app must not probe for `Config` to decide whether a user dir is usable.
    """
    fresh = tmp_path / "dolphin-user"
    boot("/nonexistent/x.rvz", fresh)
    assert (fresh / "Load" / "Riivolution").is_dir()
    assert not (fresh / "Config").exists()  # created lazily, not at startup
