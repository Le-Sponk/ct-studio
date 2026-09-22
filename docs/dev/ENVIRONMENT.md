# Development environment audit

P0-T01, audited 2026-09-17 UTC. Findings describe the container, not the host desktop.
No application code, Python project environment or track-tool bootstrap was added.

## System and storage

| Item | Observed result | Evidence |
|---|---|---|
| OS | Debian GNU/Linux 13.4 (trixie) | `platform.freedesktop_os_release()` |
| Architecture | x86_64 | `uname -m` |
| Kernel | Linux 7.0.0-31-generic | `uname -srm` |
| Container | Docker marker present; root filesystem is overlay | `/.dockerenv`, `/proc/self/mountinfo` |
| Package privileges | UID 0; `apt-get` available; `sudo` absent and unnecessary | `id`, executable discovery, successful install below |
| Workspace disk | 1,074,995,953,664 bytes available before installation; 1000.92 GiB afterward | `shutil.disk_usage(Path.cwd())`; space is shared, not reserved |
| Workspace execution | Writable; a temporary shell probe in a space/non-ASCII path exited 0 | `tempfile.TemporaryDirectory(prefix="ct audit é ", dir="/workspace")`; probe removed |
| Temporary filesystem | `/tmp` is a 512 MiB tmpfs mounted `noexec,nosuid,nodev` | mountinfo and `df -h / /workspace /tmp` |
| GPU/display | No `/dev/dri` devices; DISPLAY and WAYLAND_DISPLAY unset | device listing and environment lookup |

Keep downloaded executables/build trees on the workspace, not `/tmp`. No native Windows
or host-desktop validation was performed. Software GL is available after installation,
but host GPU performance cannot be inferred from it.

## Python and development tools

| Command/location | Result |
|---|---|
| `python --version` (also default `python3`) | Python 3.11.15, under `/usr/local/bin` |
| `/usr/bin/python3 --version` | Python 3.13.5 |
| `python3.12` on PATH / executable directory scan | Not found in `/usr/local/bin` or `/usr/bin` |
| `uv --version` | uv 0.11.1 (x86_64-unknown-linux-gnu) |
| `git --version` | git version 2.47.3 |
| C compiler | `cc` available; no RiiStudio build attempted |
| Future build tools | `cmake`, `clang`, `rustc`, `cargo` absent from PATH |
| Future build packages | `build-essential`, `libassimp-dev`, `libglfw3-dev`, `mesa-common-dev` not installed; `libfreetype-dev` installed |

The intended Python 3.12 is still a P0-T02 provisioning step, not a reason to change ADR-001.
The RiiStudio compiler/development stack remains for P0-T06; no backend feasibility claim yet.
`pyproject.toml`, `uv.lock`, and `scripts/check.py` do not exist at this stage.

## Package installation

Initial checks found no GL/EGL libraries, Mesa, Xvfb or most Qt/Blender runtime libraries.
Actual installation succeeded; no Dockerfile/restart fallback is required for P0-T01.
Commands executed as container root (both exited 0):

```sh
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  git curl xz-utils unzip ca-certificates \
  libgl1 libegl1 libegl-mesa0 libgl1-mesa-dri \
  libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 \
  libxi6 libxrender1 libsm6 libxfixes3 libxcb-cursor0 xvfb xauth mesa-utils
```

APT reported 59 new packages and 8 upgrades, 58.2 MB downloaded, 228 MB additional space.
`xauth` is needed by `xvfb-run`; `mesa-utils` supplies the diagnostic commands below.
`apt-get check` subsequently exited 0. These are container system packages, not new
application runtime dependencies. Recheck after container recreation; this audit does
not establish that changes to the container's overlay filesystem persist.

Post-install `dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Status}\n'`
reported every requested package installed:

| Packages (same version grouped) | Installed version |
|---|---|
| git | 1:2.47.3-0+deb13u1 |
| curl | 8.14.1-2+deb13u5 |
| xz-utils | 5.8.1-1+deb13u1 |
| unzip | 6.0-29+deb13u1 |
| ca-certificates | 20250419 |
| libgl1, libegl1 | 1.7.0-1+b2 |
| libegl-mesa0, libgl1-mesa-dri | 25.0.7-2+deb13u1 |
| libxkbcommon0, libxkbcommon-x11-0 | 1.7.0-2 |
| libfontconfig1 | 2.15.0-2.3 |
| libdbus-1-3 | 1.16.2-2 |
| libxi6 | 2:1.8.2-1 |
| libxrender1 | 1:0.9.12-1 |
| libsm6 | 2:1.2.6-1 |
| libxfixes3 | 1:6.0.0-2+b4 |
| libxcb-cursor0 | 0.1.5-1 |
| xvfb | 2:21.1.16-1.3+deb13u4 |
| xauth | 1:1.1.2-1.1 |
| mesa-utils | 9.0.0-2+b2 |

## Network

Real HTTPS GETs with certificate verification enabled, redirects followed, and response
bodies discarded. Command for each URL, run concurrently:

```sh
curl --location --silent --show-error --fail --connect-timeout 10 --max-time 45 \
  --output /dev/null --write-out 'http=%{http_code} final=%{url_effective} seconds=%{time_total}' URL
```

| URL (also final URL) | HTTP | Exit | Seconds |
|---|---|---|---|
| https://szs.wiimm.de/ | 200 | 0 | 1.557338 |
| https://github.com/ | 200 | 0 | 0.665676 |
| https://download.blender.org/release/ | 200 | 0 | 0.635970 |
| https://pypi.org/simple/ | 200 | 0 | 3.700381 |

Debian repository metadata and packages also downloaded successfully. These probes prove
origin reachability only, not availability of specific versions or release-asset CDN URLs.
P0-T02 must verify the actual downloads/checksums; no tool version pin was changed here.

## EGL and Mesa smoke checks

Help verified on mesa-utils 9.0.0-2+b2 and xvfb 2:21.1.16-1.3+deb13u4:
`eglinfo -h`, `glxinfo -h`, `xvfb-run --help`. `eglinfo --help` is not supported;
it printed usage with an unknown-option message, so use `-h` instead.
Both shared libraries load through `ctypes.CDLL`: `libGL.so.1`, `libEGL.so.1`.
Mesa's `50_mesa.json` EGL vendor file is present.

Commands and selected real output (each exited 0):

```text
$ env LIBGL_ALWAYS_SOFTWARE=1 eglinfo -B -p surfaceless
Surfaceless platform:
EGL API version: 1.5
EGL vendor string: Mesa Project
OpenGL core profile renderer: llvmpipe (LLVM 19.1.7, 256 bits)
OpenGL core profile version: 4.5 (Core Profile) Mesa 25.0.7-2+deb13u1
OpenGL ES profile version: OpenGL ES 3.2 Mesa 25.0.7-2+deb13u1

$ xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 glxinfo -B
Accelerated: no
Max core profile version: 4.5
OpenGL renderer string: llvmpipe (LLVM 19.1.7, 256 bits)
OpenGL core profile version string: 4.5 (Core Profile) Mesa 25.0.7-2+deb13u1
```

These demonstrate working software contexts, including a core version above the planned
3.3 minimum. They do not validate PySide6, moderngl, QOpenGLWidget integration, rendered
screenshots or frame budgets. Those remain P0-T09/S6. In particular, Qt's `offscreen`
platform and a standalone EGL context are not interchangeable evidence.

## Git and host visibility

- Branch: `main`; initial HEAD: `fa56cc8`; remote `origin` is the project's GitHub repository.
  The initial working tree contained a pre-existing modification to `KICKOFF_PROMPT.md`
  (working-name rename). It is excluded from this task's commit and left untouched.
- Ordinary Git commands failed with dubious ownership (exit 128): process UID 0, repository
  ownership UID/GID 1000. Resolved by trusting this one repository path:
  `git config --global --add safe.directory /workspace/ct-studio` (no wildcard trust, no
  ownership change). Repeat after container recreation if the audit's `--global` file is lost.
- `user.name` and `user.email` were unset and `git var GIT_AUTHOR_IDENT` exited 128. The
  human supplied the identity, which is now set in this repository's local config only;
  both author and committer idents resolve. No identity was inferred or invented.
- `/proc/self/mountinfo` shows `/workspace` as a separate writable ext4 mount rooted at a
  filesystem subdirectory; the container root is overlay. This is consistent with a bind
  mount, but the exact Docker configuration cannot be proved inside this namespace. The
  human confirmed they can read files written here and are not using a host mount, so
  treat the container filesystem, not a host checkout, as the working copy of record.
- Do not publish the underlying host source path or author email in audit notes.

## Quality gate and remaining boundaries

Actual command: `uv run python scripts/check.py`, exit 2:

```text
can't open file '<repo>/scripts/check.py': [Errno 2] No such file or directory
```

The path is redacted; this is not a passing check. P1-T02 creates that script, so ADR-016
records the pre-P1-T02 evidence gate instead of inventing a placeholder or starting P1.
For this documentation-only task, package readback, dependency consistency, network
responses, EGL/GLX contexts, documentation checks and `git diff --check` are the checks.
Diff review and documentation checks passed: UTF-8, whitespace, file-size budgets and
all three local links (including the heading anchor). The pre-existing kickoff edit's
SHA-256 remained unchanged across the task.

Still unverified or deferred:
- Python 3.12 and exact tool releases/downloads: P0-T02.
- QOpenGLWidget/Qt platform choice and preview performance: P0-T09.
- Native Windows behaviour: future Windows CI and human checkpoints.
- Tool versions and install URLs: P0-T02 verifies them against real downloads.

## Preview stack verification (S6, P0-T09)

Confirmed by real render, not just `eglinfo`:

- `moderngl.create_context(standalone=True, require=330, backend="egl")` succeeds in
  0.026 s and reports **GL 4.5 core** on llvmpipe. A 200k-triangle scene renders to a
  1280x720 framebuffer with 719 263 of 921 600 pixels drawn.
- **`QT_QPA_PLATFORM=offscreen` cannot create a GL context**: `QOpenGLWidget is not
  supported on this platform` / `Failed to create context`. Use `xvfb-run` with
  `QT_QPA_PLATFORM=xcb` for anything involving `QOpenGLWidget`; it yields GL 4.5 core
  and a valid framebuffer in about 0.2 s.
- **`libgl-dev` is required**, not just `libgl1`: moderngl loads the unversioned
  `libGL.so`, so with only the runtime package the failure appears as
  `OSError: libGL.so: cannot open shared object file` *after* Qt has already created
  the context successfully.
- Preview Python dependencies used: moderngl 5.12.0, numpy 2.5.3, Pillow 12.3.0,
  PySide6 (essentials + addons).

Frame time at 200k triangles was ~0.10 s (about 10 fps) on llvmpipe. That is a
**software-rasteriser floor** and says nothing about the ARCHITECTURE §15 budget of
>=60 fps on an integrated GPU; upload was ~0.03 s, so the CPU-side path is not the
constraint. Re-measure on real hardware at HC3.

### Container rebuild note
This sandbox is periodically rebuilt and loses apt-installed packages. Two sessions
in a row lost GL/Blender runtime libraries, which surfaced as `libGL.so.1`,
`libglfw.so.3` and `libassimp.so.5` load failures, and as a test run reporting
skips rather than failures. Reinstall before trusting a green run:

```bash
apt-get install -y libgl1 libgl-dev libegl1 libegl-mesa0 libgl1-mesa-dri \
  libglx-mesa0 xvfb xauth mesa-utils libglfw3 libassimp5 \
  libxi6 libxfixes3 libxrender1 libxxf86vm1 libsm6 libice6
```

## Wine prefixes for the Windows-only editors (S7, P0-T10)

BrawlCrate, RiiStudio's GUI and KMP Cloud have no Linux builds. S7 drove all three
under Wine 10.0 (`wine` + `wine32:i386` + `wine64`, after `dpkg --add-architecture i386`),
on a private Xvfb display with software GL. `xdotool` reads window titles,
`imagemagick` (`import`) takes the screenshots two of the tools force us to rely on:

```bash
dpkg --add-architecture i386 && apt-get update
apt-get install -y wine wine32:i386 wine64 cabextract xdotool imagemagick libnss3
```

**Prefix architecture is dictated by the executable, not by preference.** Check with
`file`: PE32 needs win32, PE32+ needs win64, and a mismatch fails with
`ShellExecuteEx failed: Bad EXE format`.

```bash
# win32 + .NET 4.8, for BrawlCrate (PE32) and KMP Cloud (PE32)
export WINEPREFIX=$HOME/s7-wine32
WINEARCH=win32 xvfb-run -a wineboot -u
curl -LO https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks
chmod +x winetricks && xvfb-run -a ./winetricks -q win10 dotnet48   # ~5 minutes

# win64, for RiiStudio (PE32+) and the Windows build of Lorenzi's KMP Editor
WINEARCH=win64 WINEPREFIX=$HOME/s7-wine64 xvfb-run -a wineboot -u
```

Notes that cost time in S7:
- **Wine Mono is not a substitute for `dotnet48`.** Without it BrawlCrate exits 255 with
  `CLRRuntimeInfo_GetRuntimeHost Wine Mono is not installed` and no window.
- `winetricks dotnet48` leaves the prefix reporting **Windows 7**; re-run
  `winetricks -q win10` afterwards, since BrawlCrate disables its API below Windows 8.
- Build the prefix **outside the repository**: `wineboot` on a path under `/workspace`
  failed here, and prefixes must never be committed. The spike and the tests read
  `S7_WINE32`/`S7_WINE64`, defaulting to `/root/s7-wine32` and `/root/s7-wine64`.
- `xvfb-run` is fine for a single launch, but concurrent launches need one shared
  display: start `Xvfb :78` yourself and export `DISPLAY`, as the spike does.
- Electron (Lorenzi's editor, built from source) additionally needs `libnss3` and
  `ELECTRON_DISABLE_SANDBOX=1` as root.
