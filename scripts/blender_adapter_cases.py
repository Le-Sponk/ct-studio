"""Measured Blender 5.2.2 cases for the P2-T05f script adapter, kept out of the base table.

The adapter always passes ``--python-exit-code 113`` *before* ``--python`` (measured: after
it the flag is ignored and a failing script exits 0), an absolute script path inside the
working folder and, when given, an absolute ``.blend``; script arguments follow ``--``
verbatim, including further ``--`` and ``-b`` tokens.
"""

from __future__ import annotations

from ops_cases import Case

_ADAPTER = ("blender", "-b", "--factory-startup", "--python-exit-code", "113", "--python")
_BLEND = (
    "blender",
    "-b",
    "{work}{sep}good.blend",
    "--factory-startup",
    "--python-exit-code",
    "113",
    "--python",
)


def _script(name: str) -> tuple[tuple[str, str]]:
    return (("@blscript", name),)


BLENDER_ADAPTER_CASES: tuple[Case, ...] = (
    Case(
        "adapter script",
        (*_ADAPTER, "{work}{sep}ok.py", "--", "a b", "é", "--", "-b"),
        _script("ok.py"),
    ),
    Case(
        "adapter blend",
        (*_BLEND, "{work}{sep}ok.py", "--", "x"),
        (("@blend",), *_script("ok.py")),
    ),
    # The failure code is used, with the traceback and a "script failed" line on stderr.
    Case("adapter exception", (*_ADAPTER, "{work}{sep}boom.py"), _script("boom.py")),
    # sys.exit(N) exits N without "Blender quit" or any error line.
    Case("adapter script exits 3", (*_ADAPTER, "{work}{sep}quit3.py"), _script("quit3.py")),
    # An unreadable .blend exits 1 with only a stdout report line; the script never runs.
    Case(
        "adapter junk blend",
        (
            "blender",
            "-b",
            "{work}{sep}junk.blend",
            "--factory-startup",
            "--python-exit-code",
            "113",
            "--python",
            "{work}{sep}ok.py",
        ),
        (("@junk", "junk.blend"), *_script("ok.py")),
    ),
)
