"""Measured ABMatt cases for the P2-T05e2 conversion adapter, kept out of the base table.

The adapter stages the DAE under ``<model name>.dae`` (ABMatt takes the MDL0 name from the
source stem), its textures beside it, and writes ``out.brres``; minimaps are staged as
``map.obj`` → ``map_model.brres`` because ABMatt adds the minimap bones only when the
*destination* file name contains ``map``. Each conversion is followed by ``-c info`` on the
output, which is how the adapter checks the MDL0 and material names.

P2-T05e3 material edits stage the archive as ``in.brres`` with ``edit.txt``; copy/paste
stages ``src.brres`` and ``dst.brres`` with ``paste.txt``. Selectors are anchored
(``^road$``) and always qualified (ABMatt's are unanchored regex searches); with two
archives the qualifier must name the archive (``in dst.brres model ^course$``).
"""

from __future__ import annotations

from ops_cases import Case

_DAE = (("@dae",),)
_TO_OUT = ("abmatt", "convert", "course.dae", "to", "out.brres", "-o")
_OUT = (*_DAE, ("abmatt", *_TO_OUT[1:]))
_MAP = (("@abobj",), ("abmatt", "convert", "map.obj", "to", "map_model.brres", "-o"))

# Setups reuse recorded rows only (the fake replays setups too): convert to out.brres,
# then rename, and make the edited source with the recorded edit on in.brres.
_IN = (*_OUT, ("@move", "out.brres", "in.brres"))
_INFO_IN = ("abmatt", "-b", "in.brres", "-c", "info")
_EDIT = ("abmatt", "-b", "in.brres", "-f", "edit.txt", "-o")
_PAIR = (
    *_IN,
    ("@abcmd", "edit.txt"),
    _EDIT,
    ("@move", "in.brres", "src.brres"),
    ("abmatt", *_TO_OUT[1:]),
    ("@move", "out.brres", "dst.brres"),
)
_INFO_DST = ("abmatt", "-b", "dst.brres", "-c", "info")
_PASTE = ("abmatt", "-b", "src.brres", "-b", "dst.brres", "-f", "paste.txt", "-o")
# Command files exactly as the adapter writes them (the fake compares bytes).
ABMATT_ADAPTER_COMMANDS = {
    "edit.txt": (
        "set material xlu:true for ^road$ in model ^course$\n"
        "set material cullmode:none for ^grass$ in model ^course$\n"
    ),
    "noop.txt": "set material xlu:false for ^road$ in model ^course$\n",
    "paste.txt": (
        "copy material for ^road$ in src.brres model ^course$\n"
        "paste material for ^grass$ in dst.brres model ^course$\n"
    ),
}

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
    # --- P2-T05e3: material edits and copy/paste on staged archives ---
    Case("adapter edit info", _INFO_IN, _IN),
    Case("adapter edit", _EDIT, (*_IN, ("@abcmd", "edit.txt"))),
    Case("adapter edited info", _INFO_IN, (*_IN, ("@abcmd", "edit.txt"), _EDIT)),
    # Nothing to change: ABMatt prints a blank line and writes nothing, exit 0.
    Case("adapter edit unchanged", _EDIT, (*_IN, ("@abcmd", "edit.txt", "noop.txt"))),
    Case("adapter paste source info", ("abmatt", "-b", "src.brres", "-c", "info"), _PAIR),
    Case("adapter paste target info", _INFO_DST, _PAIR),
    Case("adapter paste", _PASTE, (*_PAIR, ("@abcmd", "paste.txt"))),
    Case("adapter pasted info", _INFO_DST, (*_PAIR, ("@abcmd", "paste.txt"), _PASTE)),
)
