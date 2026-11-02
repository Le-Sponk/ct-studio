"""The 42 original track and arena file names a custom track can replace (P3-T01).

Copied from ``wszst tracks`` (Wiimms SZS Tools 2.42a): 32 race tracks, then 10 battle arenas,
in the game's own order. These are file names only (``<slot>.szs`` under ``Race/Course``),
not game data. Which slots suit a given track is ``wszst analyze``'s job (TOOLS.md).
"""

from __future__ import annotations

SLOTS: tuple[str, ...] = (
    "beginner_course",
    "farm_course",
    "kinoko_course",
    "factory_course",
    "castle_course",
    "shopping_course",
    "boardcross_course",
    "truck_course",
    "senior_course",
    "water_course",
    "treehouse_course",
    "volcano_course",
    "desert_course",
    "ridgehighway_course",
    "koopa_course",
    "rainbow_course",
    "old_peach_gc",
    "old_falls_ds",
    "old_obake_sfc",
    "old_mario_64",
    "old_sherbet_64",
    "old_heyho_gba",
    "old_town_ds",
    "old_waluigi_gc",
    "old_desert_ds",
    "old_koopa_gba",
    "old_donkey_64",
    "old_mario_gc",
    "old_mario_sfc",
    "old_garden_ds",
    "old_donkey_gc",
    "old_koopa_64",
    "block_battle",
    "venice_battle",
    "skate_battle",
    "casino_battle",
    "sand_battle",
    "old_battle4_sfc",
    "old_battle3_gba",
    "old_matenro_64",
    "old_CookieLand_gc",
    "old_House_ds",
)

DEFAULT_SLOT = "beginner_course"
