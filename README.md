# CT Studio

> **Under development — not ready to use yet.** This repository is public so the work can be
> followed, but CT Studio cannot build a playable track yet, and files, commands and settings
> may still change without notice.

<!-- progress:start (written by scripts/progress.py; do not edit by hand) -->
**Progress:** `████████░░░░░░░░░░░░` 43% — 66 of 151 planned tasks done.
Now working on phase 4, Build engine & SZS assembly (6 of 11 done). Counted from the phase plans; see the [roadmap](docs/ROADMAP.md).
<!-- progress:end -->

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
On the command line, `ctstudio new`, `status` and `open` make a project, show what each part
still needs and open a file in its editor ([docs/dev/CLI.md](docs/dev/CLI.md)).
A build engine can already pack files you supply into an `.szs`, but there is no `ctstudio build`
command or dashboard button for it yet.
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
