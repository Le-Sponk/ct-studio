"""CT Studio: turn a Blender project into a finished Mario Kart Wii custom track."""

from functools import cache
from typing import TYPE_CHECKING


@cache
def version() -> str:
    """CT Studio's version, read once from the installed package's metadata.

    Single source of truth is pyproject.toml; the package is always installed (uv sync
    installs it editable), so the lookup cannot miss. It is read on first use, not at
    import: ``importlib.metadata`` costs about 0.14 s, which every CLI command and window
    start would pay; only ``--version`` and Help → About need it.
    """
    from importlib.metadata import version as installed

    return installed("ctstudio")


if TYPE_CHECKING:
    __version__: str
else:

    def __getattr__(name: str) -> str:
        if name == "__version__":
            return version()
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
