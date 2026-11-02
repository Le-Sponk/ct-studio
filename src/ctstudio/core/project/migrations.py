"""Upgrades for older ``ctstudio.toml`` files (P3-T01).

Each step takes the raw TOML data of one schema version and returns the data of the next
version. ``upgrade`` runs the steps in order until the data is at ``CURRENT``. A step must
set ``schema_version`` to ``from_version + 1``; forgetting is a programming mistake, so it is
a ``RuntimeError``, not a user-facing error. Only version 1 exists today, so ``STEPS`` is
empty; the first format change adds ``(1, _v1_to_v2)`` here and bumps ``CURRENT``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

CURRENT = 1

type Step = tuple[int, Callable[[dict[str, object]], dict[str, object]]]

STEPS: tuple[Step, ...] = ()


def oldest_readable(steps: tuple[Step, ...] | None = None) -> int:
    """The lowest schema version that ``upgrade`` can bring up to date."""
    chain = {version for version, _ in (STEPS if steps is None else steps)}
    oldest = CURRENT
    while oldest - 1 in chain:
        oldest -= 1
    return oldest


def upgrade(
    data: dict[str, object],
    *,
    steps: tuple[Step, ...] | None = None,
    current: int | None = None,
) -> dict[str, object]:
    """``data`` brought up to the current schema version, one step at a time.

    The caller checks first (``oldest_readable``) that every needed step exists.
    """
    target = CURRENT if current is None else current
    by_version = dict(STEPS if steps is None else steps)
    version = cast("int", data["schema_version"])  # checked by manifest_io before upgrading
    while version < target:
        data = by_version[version](data)
        after = data.get("schema_version")
        if after != version + 1:
            raise RuntimeError(f"upgrade from version {version} produced version {after}")
        version += 1
    return data
