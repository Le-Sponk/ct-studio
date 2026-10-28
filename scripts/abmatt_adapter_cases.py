"""Measured ABMatt cases for the P2-T05e2 conversion adapter, kept out of the base table.

The adapter stages the DAE under ``<model name>.dae`` (ABMatt takes the MDL0 name from the
source stem), its textures beside it, and writes ``out.brres``; minimaps are staged as
``map.obj`` → ``map_model.brres`` because ABMatt adds the minimap bones only when the
*destination* file name contains ``map``. Each conversion is followed by ``-c info`` on the
output, which is how the adapter checks the MDL0 and material names.
"""

from __future__ import annotations

from ops_cases import Case

_DAE = (("@dae",),)
_TO_OUT = ("abmatt", "convert", "course.dae", "to", "out.brres", "-o")
_OUT = (*_DAE, ("abmatt", *_TO_OUT[1:]))
_MAP = (("@abobj",), ("abmatt", "convert", "map.obj", "to", "map_model.brres", "-o"))

ABMATT_ADAPTER_CASES: tuple[Case, ...] = (
    Case("adapter convert", _TO_OUT, _DAE),
    Case("adapter info", ("abmatt", "-b", "out.brres", "-c", "info"), _OUT),
    # A missing texture is only a WARN line at exit 0; the material keeps a grey colour.
    Case(
        "adapter convert missing texture",
        _TO_OUT,
        (*_DAE, ("@move", "fence.png", "unused/fence.png")),
    ),
    # ABMatt does not look in textures/ (unlike rszst): every texture is lost, exit 0.
    Case(
        "adapter convert textures folder",
        _TO_OUT,
        (
            *_DAE,
            *(
                ("@move", f"{t}.png", f"textures/{t}.png")
                for t in ("road", "grass", "fence", "water")
            ),
        ),
    ),
    Case("adapter minimap info", ("abmatt", "-b", "map_model.brres", "-c", "info"), _MAP),
)
