"""Install the fake tools as real executables in a folder (for ``fake_tools_path``).

The executables run the fakes with the interpreter running the tests, so they need no
install step and see the same ``tests/fakes`` code:

* Windows: the console launcher pip writes for console scripts (``t64.exe`` from distlib,
  taken from the pip wheel bundled with CPython's ``ensurepip``), followed by a quoted
  ``#!"python.exe"`` line and a zip whose ``__main__.py`` calls the fake. A real ``.exe``,
  so ``CreateProcess`` (and the runner's job object) treat it like any installed tool.
* Linux: an executable sh/Python polyglot. A plain ``#!`` line cannot hold an interpreter
  path with spaces; ``exec "python" "$0" "$@"`` can.
"""

from __future__ import annotations

import ensurepip
import io
import os
import platform
import sys
import zipfile
from pathlib import Path

FAKES = Path(__file__).resolve().parent
WIIMM = ("wszst", "wkclt", "wkmpt", "wimgt")
TOOLS = (*WIIMM, "rszst", "abmatt")
_UNSAFE_IN_SH = set('"$`\\\n')


def entry_point(tool: str) -> str:
    module = (
        "fake_abmatt" if tool == "abmatt" else "fake_rszst" if tool == "rszst" else "fake_wiimm"
    )
    args = f"{tool!r}, sys.argv[1:]" if tool in WIIMM else "sys.argv[1:]"
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(FAKES)!r})\n"
        f"import {module}\n"
        f"raise SystemExit({module}.main({args}))\n"
    )


def install(directory: Path, python: Path | None = None) -> dict[str, Path]:
    interpreter = Path(python or sys.executable)
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        stub = _windows_launcher()
        return {
            tool: _write_exe(directory / f"{tool}.exe", stub, interpreter, entry_point(tool))
            for tool in TOOLS
        }
    return {tool: _write_script(directory / tool, interpreter, entry_point(tool)) for tool in TOOLS}


def _windows_launcher() -> bytes:
    bundled = Path(ensurepip.__file__).parent / "_bundled"
    wheel = next(iter(sorted(bundled.glob("pip-*.whl"))), None)
    if wheel is None:
        raise RuntimeError(f"no pip wheel in {bundled}; the fake .exe launchers need one")
    name = "t64-arm.exe" if platform.machine().upper() == "ARM64" else "t64.exe"
    with zipfile.ZipFile(wheel) as archive:
        return archive.read(f"pip/_vendor/distlib/{name}")


def _write_exe(path: Path, stub: bytes, python: Path, code: str) -> Path:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("__main__.py", code)
    shebang = b'#!"' + str(python).encode("utf-8") + b'"\r\n'
    path.write_bytes(stub + shebang + payload.getvalue())
    return path


def _write_script(path: Path, python: Path, code: str) -> Path:
    if _UNSAFE_IN_SH & set(str(python)):
        raise RuntimeError(f"cannot quote {python} for /bin/sh")
    path.write_text(
        f"#!/bin/sh\n''''exec \"{python}\" \"$0\" \"$@\" #'''\n{code}",
        encoding="utf-8",
        newline="\n",
    )
    path.chmod(0o755)
    return path
