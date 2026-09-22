#!/usr/bin/env bash
# Mutation check for the S8 contract tests (P0-T11).
#
# These are characterization tests with no product code behind them yet, so the
# thing worth proving is that they fail when the *contract* changes, not when an
# assertion is flipped. Each mutation below breaks one input the way a wrong
# implementation would, and must turn at least one test red.
set -u
TEST=tests/integration/test_dolphin_launch.py
BACKUP=$(mktemp)
cp "$TEST" "$BACKUP"
trap 'cp "$BACKUP" "$TEST"; rm -f "$BACKUP"' EXIT
export PATH=/usr/games:$PATH

caught=0
total=0
mutate() {
  local name="$1" old="$2" new="$3"
  total=$((total + 1))
  cp "$BACKUP" "$TEST"
  python3 - "$TEST" "$old" "$new" <<'PY'
import sys
from pathlib import Path
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
text = Path(path).read_text()
if old not in text:
    raise SystemExit(f"mutation target not found: {old!r}")
Path(path).write_text(text.replace(old, new, 1))
PY
  if uv run --with pytest python -m pytest "$TEST" -q >/dev/null 2>&1; then
    echo "SURVIVED: $name"
  else
    echo "caught:   $name"
    caught=$((caught + 1))
  fi
}

# 1. Drop sys/boot.bin: the directory is no longer a valid blob, so route 1 dies.
mutate "no sys/boot.bin" \
  '(root / "sys" / "boot.bin").write_bytes(bytes(header))' \
  'pass'
# 2. Wrong descriptor type string: Dolphin must reject what CT Studio writes.
mutate "descriptor type typo" \
  '"type": "dolphin-game-mod-descriptor",' \
  '"type": "dolphin-game-mod-descriptorX",'
# 3. Descriptor version bumped: version 1 is the only accepted value.
mutate "descriptor version 2" \
  '"version": 1,' \
  '"version": 2,'
# 4. Point --exec at the game folder instead of sys/main.dol.
mutate "boot the folder, not the DOL" \
  'result = boot(disc / "sys" / "main.dol", user_dir)' \
  'result = boot(disc, user_dir)'
# 5. Truncate sys/boot.bin below 0x20: the directory blob is no longer valid, so
#    Dolphin silently boots the DOL as a bare executable with no file system.
mutate "short sys/boot.bin" \
  '(root / "sys" / "boot.bin").write_bytes(bytes(header))' \
  '(root / "sys" / "boot.bin").write_bytes(bytes(0x10))'
# 6. Claim the missing-file case exits 0.
mutate "missing file exits 0" \
  'assert result.returncode == 1
    assert "does not exist"' \
  'assert result.returncode == 0
    assert "does not exist"'

echo "---"
echo "$caught/$total mutations caught"
[ "$caught" -eq "$total" ]
