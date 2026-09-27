"""CT Studio: turn a Blender project into a finished Mario Kart Wii custom track."""

from importlib.metadata import version

# Single source of truth is pyproject.toml; the package is always installed (uv sync
# installs it editable), so the metadata lookup cannot miss.
__version__ = version("ctstudio")
