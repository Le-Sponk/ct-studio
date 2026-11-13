# CT Studio

> **Under development — not ready to use yet.** This repository is public so the work can be
> followed, but automatic track creation from Blender is not yet ready. Files, commands and settings
> may still change without notice.

<!-- progress:start (written by scripts/progress.py; do not edit by hand) -->
**Progress:** `███████████░░░░░░░░░` 57% — 109 of 188 planned tasks done.
Now working on phase 5, GUI shell & dashboard (manual-mode MVP) (36 of 48 done). Counted from the phase plans; see the [roadmap](docs/ROADMAP.md).
<!-- progress:end -->

CT Studio is an in-progress desktop app for building Mario Kart Wii custom tracks from Blender projects.
It targets Windows and Linux as first-class platforms; macOS is currently best-effort.
The goal is to turn a `.blend` project into a finished `.szs` without hiding the underlying files.
Beginners should see clear defaults, while experienced creators can keep using external editors.
The planned pipeline coordinates Blender-MKW-Utilities, Wiimms SZS Tools and a BRRES backend.
The Blender add-on is pinned from [Le-Sponk's compatibility fork](https://github.com/Le-Sponk/Blender-MKW-Utilities)
in `vendor/blender-mkw-utilities`; its Linux and modern-Blender export support is part of the plan.
Course models, collision, minimaps, KMP data and validation are planned dashboard components.
Projects will remain ordinary directories with readable configuration and inspectable commands.
User-authored files must be backed up before any automated replacement.
Nintendo game files are never included; users provide their own assets when a feature needs them.
The GUI can create and open projects, remember the ten most recent folders between runs,
and show a live dashboard of component statuses with refresh and path copying
([project navigation](docs/user/PROJECT_NAVIGATION.md)). Project details can change the original
track slot and Blender source; component cards can change supported modes, with backed-up saves.
The dashboard can launch Blender, request component folders, and run test/release builds from
supplied component files, with cancellation, live part progress and a collapsible live build log.
GUI file assignment, automatic generation and trusted command copying are still under development.
It supports a Qt-free `--version` and `--help`, plus an offscreen PNG smoke command.
On the command line, `ctstudio new`, `status` and `open` make a project, show what each part
still needs and open a file in its editor ([docs/dev/CLI.md](docs/dev/CLI.md)).
`ctstudio build` turns a project whose parts are files you supply into a checked `.szs`;
CT Studio cannot make those parts from a Blender scene yet; building still requires the
project's supplied files and configured tools.
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
