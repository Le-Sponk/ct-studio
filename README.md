# CT Studio

CT Studio is an in-progress desktop app for building Mario Kart Wii custom tracks from Blender projects.
It targets Windows and Linux as first-class platforms; macOS is currently best-effort.
The goal is to turn a `.blend` project into a finished `.szs` without hiding the underlying files.
Beginners should see clear defaults, while experienced creators can keep using external editors.
The planned pipeline coordinates Blender-MKW-Utilities, Wiimms SZS Tools and a BRRES backend.
Course models, collision, minimaps, KMP data and validation are planned dashboard components.
Projects will remain ordinary directories with readable configuration and inspectable commands.
User-authored files must be backed up before any automated replacement.
Nintendo game files are never included; users provide their own assets when a feature needs them.
The current build has a Qt dashboard shell and About dialog, not yet a track builder.
It supports a Qt-free `--version` and `--help`, plus an offscreen PNG smoke command.
Core utilities, architecture contracts and tests exist, but `.szs` export is not yet implemented.
Follow [STATUS.md](STATUS.md) for progress and [the project brief](docs/PROJECT_BRIEF.md) for the plan.

## Development quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, then in a checkout:

```sh
git submodule update --init
uv sync --locked
uv run ctstudio --version
uv run ctstudio
```

The last command opens the GUI; close its window to return to your shell. To run the quality gate and
broader tests (optional real-tool tests skip when their tools are absent):

```sh
uv run python scripts/check.py
uv run pytest -m "not network" tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow and platform notes. CT Studio is
[GPL-3.0-or-later](LICENSE); dependency and external-tool boundaries are described in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No Nintendo content belongs in this repository.
