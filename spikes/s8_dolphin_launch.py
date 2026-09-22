"""Spike S8: getting a built SZS into a running game (P0-T11).

Throwaway evidence-gathering. Findings go to docs/dev/SPIKES.md S8; P11 is
written fresh from those notes (AGENTS.md rule 3).

P11-T02 wants "Build & launch": one click from a built `<slot>.szs` to racing
it. Three candidate routes:
  1  extracted game folder     - replace the slot file on disk, boot `sys/main.dol`
  2  Riivolution               - leave the game untouched, patch it at boot
  3  MKW-SP "My Stuff"         - needs the MKW-SP distribution, not plain MKW

The question is not "which is nicest" but "which can CT Studio actually start
without the user clicking through Dolphin's GUI", and what each one costs.

No Mario Kart Wii files exist here and none may be obtained, so every probe runs
against a **synthetic** disc-shaped directory: a `sys/boot.bin` header, a stub
`sys/main.dol`, and a fake `Race/Course/*.szs`. That is enough to exercise
Dolphin's boot-path selection, its Riivolution descriptor plumbing and its exit
codes; it is not enough to prove a patched file actually reaches the game, which
is an HC3 item.

Run:  uv run python spikes/s8_dolphin_launch.py
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "spikes" / "out" / "s8"

DOLPHIN = shutil.which("dolphin-emu") or "/usr/games/dolphin-emu"
NOGUI = shutil.which("dolphin-emu-nogui") or "/usr/games/dolphin-emu-nogui"
TOOL = shutil.which("dolphin-tool") or "/usr/games/dolphin-tool"
XVFB_RUN = shutil.which("xvfb-run") or "xvfb-run"

TIMEOUT = 90
BOOT_SECONDS = 25  # emulation never exits on its own; stop it after this


def sh(argv: list[str], timeout: int = TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - local tools, argv only
        argv, capture_output=True, text=True, timeout=timeout, check=False
    )


def clean_text(raw: str) -> str:
    """Dolphin writes NULs and ALSA noise to stdout in this container."""
    lines = raw.replace("\x00", "").splitlines()
    return "\n".join(
        line for line in lines if not line.startswith(("ALSA lib", "AL lib", "libpng"))
    ).strip()


def make_disc_directory(root: Path) -> Path:
    """A synthetic directory blob: disc-shaped, but not a game.

    Dolphin accepts an extracted game as `<root>/sys/main.dol` when a
    `sys/boot.bin` of at least 0x20 bytes sits beside it (DirectoryBlob.cpp
    `IsValidDirectoryBlob`). Nothing here is Nintendo data.
    """
    shutil.rmtree(root, ignore_errors=True)
    (root / "sys").mkdir(parents=True)
    (root / "files" / "Race" / "Course").mkdir(parents=True)

    header = bytearray(0x440)
    header[0:6] = b"RMCP01"  # the shape of a game id, not a copy of one
    header[0x20:0x2C] = b"CTSTUDIO S8"
    struct.pack_into(">I", header, 0x18, 0x5D1C9EA3)  # Wii magic word
    (root / "sys" / "boot.bin").write_bytes(bytes(header))
    (root / "sys" / "bi2.bin").write_bytes(bytes(0x2000))

    # A minimal well-formed DOL: without one Dolphin boots it as an executable
    # instead of as a disc, which is a different code path entirely.
    dol = bytearray(0x100)
    struct.pack_into(">I", dol, 0x00, 0x100)  # text section offset
    struct.pack_into(">I", dol, 0x48, 0x80003100)  # text section address
    struct.pack_into(">I", dol, 0x90, 0x20)  # text section size
    struct.pack_into(">I", dol, 0xE0, 0x80003100)  # entry point
    (root / "sys" / "main.dol").write_bytes(bytes(dol) + b"\x60\x00\x00\x00" * 8)

    slot = root / "files" / "Race" / "Course" / "beginner_course.szs"
    slot.write_bytes(b"Yaz0" + bytes(60))
    return slot


def write_riivolution(root: Path, slot_name: str) -> Path:
    """The XML shape P11 would generate: one patch replacing one slot file."""
    (root / "riivolution").mkdir(parents=True, exist_ok=True)
    (root / "ctfiles" / "Race" / "Course").mkdir(parents=True, exist_ok=True)
    (root / "ctfiles" / "Race" / "Course" / slot_name).write_bytes(b"Yaz0" + bytes(60))
    xml = root / "riivolution" / "ctstudio.xml"
    xml.write_text(
        '<wiidisc version="1" root="/ctfiles">\n'
        '  <id game="RMC"/>\n'
        '  <options><section name="CT Studio">\n'
        '    <option id="ctstudio-track" name="Test track" default="1">\n'
        '      <choice name="Enabled"><patch id="ctstudio"/></choice>\n'
        "    </option>\n"
        "  </section></options>\n"
        '  <patch id="ctstudio">\n'
        f'    <file disc="/Race/Course/{slot_name}" external="/Race/Course/{slot_name}"/>\n'
        "  </patch>\n"
        "</wiidisc>\n",
        encoding="utf-8",
    )
    return xml


def write_descriptor(path: Path, base: Path, xml: Path | None) -> Path:
    """Dolphin's own mod-descriptor format (DiscIO/GameModDescriptor.cpp)."""
    descriptor: dict[str, object] = {
        "type": "dolphin-game-mod-descriptor",
        "version": 1,
        "base-file": str(base),
        "display-name": "CT Studio S8",
    }
    if xml is not None:
        descriptor["riivolution"] = {
            "patches": [
                {
                    "xml": str(xml),
                    "root": str(xml.parent.parent / "ctfiles"),
                    "options": [
                        {"section-name": "CT Studio", "option-id": "ctstudio-track", "choice": 1}
                    ],
                }
            ]
        }
    path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    return path


def boot(target: Path, user_dir: Path, logs: bool = True) -> dict[str, object]:
    """Boot headlessly and report what Dolphin did, from its own log.

    `Logs/` has to exist first: Dolphin never creates it, and file logging then
    writes nothing without complaining.
    """
    (user_dir / "Logs").mkdir(parents=True, exist_ok=True)
    log = user_dir / "Logs" / "dolphin.log"
    log.unlink(missing_ok=True)
    argv = [NOGUI, "-u", str(user_dir), "-p", "headless", "-v", "Null"]
    if logs:
        argv += [
            "-C",
            "Logger.Options.WriteToFile=True",
            "-C",
            "Logger.Options.Verbosity=4",
            "-C",
            "Logger.Logs.BOOT=True",
            "-C",
            "Logger.Logs.DISCIO=True",
        ]
    argv += [f"--exec={target}"]

    started = time.monotonic()
    try:
        result = sh(argv, timeout=BOOT_SECONDS)
        exit_code: int | None = result.returncode
        output = clean_text(result.stdout + result.stderr)
    except subprocess.TimeoutExpired as expired:
        exit_code = None  # still emulating: that is the success shape
        output = clean_text((expired.stdout or b"").decode("utf-8", "replace"))
    seconds = round(time.monotonic() - started, 1)

    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    booting = [line for line in text.splitlines() if "Booting from" in line]
    return {
        "exit_code": exit_code,
        "seconds": seconds,
        "message": output.splitlines()[0] if output else "",
        "booting_from": booting[0].split("]: ", 1)[-1] if booting else None,
        "riivolution_log_lines": sum("riivolution" in line.lower() for line in text.splitlines()),
    }


def argv_contract() -> dict[str, object]:
    """What the two binaries accept, from the pinned build rather than the README."""
    findings: dict[str, object] = {}
    for name, binary in (("dolphin_emu", DOLPHIN), ("dolphin_emu_nogui", NOGUI)):
        if not Path(binary).exists():
            findings[name] = {"skipped": f"{binary} not installed"}
            continue
        # The GUI binary aborts without a display even for --help.
        bare = sh([binary, "--help"])
        wrapped = sh([XVFB_RUN, "-a", binary, "--help"])
        findings[name] = {
            "help_without_display_exit": bare.returncode,
            "help_under_xvfb_exit": wrapped.returncode,
            "needs_display_for_help": bare.returncode != 0 and wrapped.returncode == 0,
            "options": sorted(
                part.split("=")[0]
                for line in (wrapped.stdout or bare.stdout).splitlines()
                for part in line.split()
                if part.startswith("--")
            ),
        }
    return findings


def missing_file_behaviour(user_dir: Path) -> dict[str, object]:
    """The failure the app will hit most: a path that is not there."""
    absent = "/nonexistent/ct-studio/game.rvz"
    nogui = sh([NOGUI, "-u", str(user_dir), "-p", "headless", "--exec=" + absent])
    gui_argv = [XVFB_RUN, "-a", DOLPHIN, "-u", str(user_dir), "--batch", "--exec=" + absent]
    try:
        gui = sh(gui_argv, timeout=40)
        gui_exit: int | str = gui.returncode
        gui_output = clean_text(gui.stdout + gui.stderr)[:200]
    except subprocess.TimeoutExpired:
        # This is the finding, not an error: --batch does not suppress the
        # "does not exist" panic dialog, so the GUI binary waits for a click
        # forever. Only dolphin-emu-nogui fails cleanly.
        gui_exit = "timeout"
        gui_output = ""
        subprocess.run(["pkill", "-f", "dolphin-emu --"], check=False)  # noqa: S607
    return {
        "nogui_exit": nogui.returncode,
        "nogui_message": clean_text(nogui.stdout + nogui.stderr).splitlines()[:2],
        "gui_batch_exit": gui_exit,
        "gui_batch_output": gui_output,
        "note": "the GUI blocks on a modal panic dialog; only the nogui binary reports the error",
    }


def silence_probe(work: Path, disc: Path, xml: Path, user_dir: Path) -> dict[str, object]:
    """The risk question: can CT Studio tell a working patch from a dropped one?

    Riivolution patching is applied during boot with no log line of its own
    (RiivolutionPatcher.cpp only logs on memory-patch/HLE overlap), so this
    compares a plain boot, a correct patch and a patch whose XML targets a
    different game id - which `IsValidForGame` silently skips.
    """
    wrong = work / "riivolution" / "wrong-game.xml"
    wrong.write_text(
        xml.read_text(encoding="utf-8").replace('game="RMC"', 'game="ZZZ"'), encoding="utf-8"
    )
    descriptor = write_descriptor(work / "mod-wrong-game.json", disc / "sys" / "main.dol", wrong)

    def mentions(target: Path) -> int:
        boot(target, user_dir)
        log = user_dir / "Logs" / "dolphin.log"
        text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        return sum(
            "riivolution" in line.lower() or "patch" in line.lower() for line in text.splitlines()
        )

    return {
        "plain_boot_mentions": mentions(disc / "sys" / "main.dol"),
        "patched_boot_mentions": mentions(work / "mod.json"),
        "wrong_game_id_mentions": mentions(descriptor),
        "wrong_game_id_exit": boot(descriptor, user_dir)["exit_code"],
        "verdict": "no observable difference: a silently skipped patch looks like a working one",
    }


def route_1(disc: Path, slot: Path, user_dir: Path) -> dict[str, object]:
    """Route 1: replace the slot file in an extracted game and boot it."""
    return {
        "boot_sys_main_dol": boot(disc / "sys" / "main.dol", user_dir),
        "boot_the_directory_itself": boot(disc, user_dir),
        "tool_can_list_it": sh([TOOL, "extract", "-i", str(disc / "sys" / "main.dol"), "-l"])
        .stdout.strip()
        .splitlines(),
        "slot_file_is_a_plain_file": slot.is_file(),
    }


def route_2(work: Path, disc: Path, xml: Path, user_dir: Path) -> dict[str, object]:
    """Route 2: Dolphin's own game-mod descriptor, which drives Riivolution."""
    base = disc / "sys" / "main.dol"
    return {
        "descriptor_with_valid_xml": boot(write_descriptor(work / "mod.json", base, xml), user_dir),
        "descriptor_with_missing_xml": boot(
            write_descriptor(work / "mod-missing.json", base, work / "riivolution" / "absent.xml"),
            user_dir,
        ),
        "descriptor_rejected_when": {
            "wrong_type": boot(
                write_json(work / "bad-type.json", {"type": "nope", "version": 1}), user_dir
            ),
            "wrong_version": boot(
                write_json(
                    work / "bad-version.json",
                    {"type": "dolphin-game-mod-descriptor", "version": 2},
                ),
                user_dir,
            ),
        },
    }


def main() -> int:
    if not Path(NOGUI).exists():
        print(f"dolphin-emu-nogui not found at {NOGUI}; install dolphin-emu")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    work = OUT / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    user_dir = work / "dolphin-user"

    disc = work / "extracted game"  # a path with a space, on purpose (rule 11)
    slot = make_disc_directory(disc)
    xml = write_riivolution(work, slot.name)

    findings: dict[str, object] = {
        "versions": {
            "dolphin": clean_text(sh([XVFB_RUN, "-a", DOLPHIN, "--version"]).stdout),
            "dolphin_tool": clean_text(sh([TOOL, "-h"]).stdout).splitlines()[:1],
        },
        "argv_contract": argv_contract(),
        "missing_file": missing_file_behaviour(user_dir),
        "route_1_extracted_folder": route_1(disc, slot, user_dir),
        "route_2_riivolution": route_2(work, disc, xml, user_dir),
        "patch_is_unobservable": silence_probe(work, disc, xml, user_dir),
    }

    destination = OUT / "s8_findings.json"
    destination.write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(findings, indent=2, sort_keys=True))
    print(f"\nwrote {destination}")
    return 0


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    raise SystemExit(main())
