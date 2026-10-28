"""Measured rszst cases for the P2-T05e adapter, kept out of the 400-line base table.

The adapter stages every input in a private folder under fixed ASCII names (``model.dae``,
``in.brres``, ``in.json``, ``presets``) and always passes ``--model-name``, so these rows
record exactly that argv shape. The non-ASCII rows show why: the Windows build reads argv
through the ANSI code page, so even *relative* non-ASCII names fail or silently miss.
"""

from __future__ import annotations

from ops_cases import Case

_DAE = (("@dae",), ("@move", "course.dae", "model.dae"))
_IMPORT = ("rszst", "import-brres", "model.dae", "out.brres", "--model-name", "course")
_IN_BRRES = ("rszst", "import-brres", "model.dae", "in.brres", "--model-name", "course")
_PRESETS = (*_DAE, _IN_BRRES, ("rszst", "dump-presets", "in.brres", "presets"))

RSZST_ADAPTER_CASES: tuple[Case, ...] = (
    Case("adapter import", _IMPORT, _DAE),
    Case("adapter import mipmaps", (*_IMPORT, "--mipmaps", "--min-mip", "64"), _DAE),
    Case("adapter import presets", (*_IMPORT, "--preset-path", "presets"), _PRESETS),
    Case(
        "adapter import textures folder",
        _IMPORT,
        (*_DAE, ("@move", "fence.png", "textures/fence.png")),
    ),
    # The real tool exits 0 and substitutes a 32x32 placeholder texture: the fake cannot
    # know that output, and the adapter refuses before running.
    Case(
        "adapter import missing texture",
        _IMPORT,
        (*_DAE, ("@move", "fence.png", "unused/fence.png")),
        "unmodelled",
    ),
    Case(
        "import non-ascii relative source",
        ("rszst", "import-brres", "c\u00e9.dae", "out.brres", "--model-name", "course"),
        (*_DAE, ("@move", "model.dae", "c\u00e9.dae")),
        native_only=True,
    ),
    Case(
        "import non-ascii relative presets",
        (*_IMPORT, "--preset-path", "pr\u00e9"),
        (*_PRESETS, ("@move", "presets", "pr\u00e9")),
        native_only=True,
    ),
    Case(
        "adapter to json",
        ("rszst", "brres-to-json", "in.brres", "out.json"),
        (*_DAE, _IN_BRRES),
    ),
    Case(
        "adapter from json",
        ("rszst", "json-to-brres", "in.json", "out.brres"),
        (*_DAE, _IN_BRRES, ("rszst", "brres-to-json", "in.brres", "in.json")),
    ),
    Case(
        "adapter dump presets", ("rszst", "dump-presets", "in.brres", "presets"), (*_DAE, _IN_BRRES)
    ),
)
