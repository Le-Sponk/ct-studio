# Phase 11 — Dolphin testing & release build

**Goal:** one click from change to racing; a clean release artefact for sharing the track.
**Read first:** SPIKES.md §S8 (and re-verify it — Dolphin changes often), MKW_DOMAIN.md (slots, legal).

### [ ] P11-T01 — Test setup wizard
Implement the S8-recommended method: **an extracted game folder** (route 1). User selects their own
MKW disc image → the app explains disk usage and asks consent → one-time extraction into the user
data dir via `dolphin-tool extract` → verification with `dolphin-tool extract -i <game>/sys/main.dol -l`
(lists the tree without booting; S8 verified this works on an extracted game, not just an ISO).
Store paths in user settings. The launch target is `<game>/sys/main.dol`, **never** the folder —
S8 measured `--exec=<folder>` as `Could not recognize file`, exit 1.
**Acceptance:** tests with fakes for every step; real run is `realdata` + HC3/HC4.

### [ ] P11-T02 — Build & launch
"Build & launch Dolphin": test build → install the SZS into the test setup for the project's slot
(backup/restore the original file in the test copy; never touch the user's original image) → launch
Dolphin detached with the right arguments → optionally close the previous Dolphin started by the app
(ask once, remember).
Constraints S8 measured, all in `tests/integration/test_dolphin_launch.py`:
- **Install is a plain file copy** over `files/Race/Course/<slot>.szs`. No repack.
- **Launch `<game>/sys/main.dol`** and confirm the log says `Booting from disc:`. A folder whose
  `sys/boot.bin` is missing or under 0x20 bytes (half-extracted, or the wrong folder) boots the DOL
  as a bare *executable* with no file system — success-looking, track absent.
- **`dolphin-emu --batch` does not fail cleanly**: a missing file leaves it on a modal panic dialog
  forever. Either use `dolphin-emu-nogui` for anything the app must check, or pass
  `-C Main.Interface.UsePanicHandlers=False`, and never wait on the process for a result.
- **A successful boot never exits.** Detached launch, no exit-code check for success.
- **`-u <dir>`** isolates the user directory; do not probe for `Config` to validate one.
**Acceptance:** argument/path construction tests on both OSes; process handling tests with a fake
Dolphin.

### [ ] P11-T02b — Riivolution route (optional, second)
S8 confirmed a GUI-free Riivolution path: CT Studio writes a `dolphin-game-mod-descriptor` JSON
(shape and enforced fields in TOOLS.md) and passes it to `--exec`. It leaves the user's game
untouched, which is the reason to offer it.
**The blocker to design around:** a descriptor whose XML is missing, malformed or scoped to another
game id **still boots, exit 0, silently**. So this route requires CT Studio to validate the XML it
generates before launching, and the UI must never present "Dolphin launched" as "your track is in
the game".
**Acceptance:** descriptor/XML generation tests; a validation step with its own tests; HC3 confirms
the patch actually lands.

### [ ] P11-T03 — Slot helper
Run `wszst slots` on the built SZS; show compatible slots in the slot picker (badge "compatible"/
"may not work"); warn when the chosen slot is flagged; short explanation + wiki link.
**Acceptance:** parser tests on recordings; UI test.

### [ ] P11-T04 — Release build
Release profile: best compression, `_d` variant, strict validation (errors block, warnings listed),
release checklist (all components Ready, KMP checklist complete or explicitly waived), output naming
template (default `{name} v{version} [{author}].szs` — confirm conventions against current mkwiiki
guidance), optional zip with a generated `README.txt` (credits, version, slot).
**Acceptance:** fixture release build test; checklist UI test.

### [ ] P11-GATE — Phase review
