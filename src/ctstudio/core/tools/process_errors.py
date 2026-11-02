"""Why the OS refused to start a tool, in words a user can act on (split from ``process``).

``process._popen`` hands every ``OSError`` from starting a program here. Only failures that are
about the file get a "choose another file" message; anything else (too many open files, out of
memory, needs administrator rights) says what the OS reported, so it is not blamed on the file.
"""

from __future__ import annotations

import errno

from ctstudio.core.errors import CTStudioError, ToolFailedToStart, ToolNotFound

# ENOEXEC; Windows: bad EXE format, EXE for another machine, invalid EXE signature.
_NOT_A_PROGRAM_WINERRORS = frozenset({193, 216, 191})


def start_error(name: str, exc: OSError) -> CTStudioError:
    """The typed error for a failed start of the program called ``name``."""
    if isinstance(exc, FileNotFoundError):
        return ToolNotFound(name)
    if isinstance(exc, PermissionError):
        hint = "Check that the file is a program you are allowed to run, or choose another."
        return ToolNotFound(name, hint=hint)
    if _not_a_program(exc):  # a file, but not one this OS can run
        hint = "Choose another file, or reinstall the tool."
        return ToolNotFound(name, hint=hint, problem="is not a program this system can run")
    return ToolFailedToStart(name, exc.strerror or str(exc))


def _not_a_program(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in _NOT_A_PROGRAM_WINERRORS
    return exc.errno == errno.ENOEXEC
