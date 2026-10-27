"""Stop a tool's whole process tree: a POSIX session or a Windows kill-on-close job object.

The runner starts every CLI tool as a new session (POSIX) or suspended in a new process group
(Windows), then wraps it here before it can spawn helpers. Descendants stay in the session or
job even after the tool itself exits, so they can be killed although their parent is gone.
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _NTDLL = ctypes.WinDLL("ntdll")
    _EXTENDED_LIMIT_INFORMATION = 9
    _KILL_ON_JOB_CLOSE = 0x2000
    # PROCESS_TERMINATE | PROCESS_SET_QUOTA (job assignment) | PROCESS_SUSPEND_RESUME
    _ACCESS = 0x0001 | 0x0100 | 0x0800

    class _BasicLimits(ctypes.Structure):
        _fields_ = (
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        )

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = (
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        )

    def _function(library: ctypes.WinDLL, name: str, restype: object, *argtypes: object):
        function = getattr(library, name)
        function.restype = restype
        function.argtypes = argtypes
        return function

    _create_job = _function(
        _KERNEL32, "CreateJobObjectW", wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCWSTR
    )
    _set_job_information = _function(
        _KERNEL32,
        "SetInformationJobObject",
        wintypes.BOOL,
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _assign = _function(
        _KERNEL32, "AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE
    )
    _terminate_job = _function(
        _KERNEL32, "TerminateJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.UINT
    )
    _open_process = _function(
        _KERNEL32, "OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
    )
    _close_handle = _function(_KERNEL32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
    # Undocumented but stable since NT; subprocess does not expose the suspended thread handle.
    _resume_process = _function(_NTDLL, "NtResumeProcess", ctypes.c_long, wintypes.HANDLE)

    def _new_job() -> int:
        job = _create_job(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        size = ctypes.sizeof(limits)
        if not _set_job_information(
            job, _EXTENDED_LIMIT_INFORMATION, ctypes.addressof(limits), size
        ):
            error = ctypes.get_last_error()
            _close_handle(job)
            raise ctypes.WinError(error)
        return int(job)

    class ProcessTree:
        """A kill-on-close job holding a child that was created with ``CREATE_SUSPENDED``."""

        def __init__(self, pid: int) -> None:
            self._job: int | None = _new_job()
            process = _open_process(_ACCESS, False, pid)
            assigned = bool(process) and bool(_assign(self._job, process))
            error = ctypes.get_last_error()
            # Resume only after assignment, so no grandchild can start outside the job.
            resumed = assigned and _resume_process(process) == 0
            if process:
                _close_handle(process)
            if not resumed:
                self.close()
                raise OSError(f"Could not place process {pid} in a job (Windows error {error}).")

        def kill(self) -> None:
            if self._job is not None:
                _terminate_job(self._job, 1)

        def close(self) -> None:
            """Kill any remaining descendants by closing the last handle to the job."""
            if self._job is not None:
                _close_handle(self._job)
                self._job = None

else:
    import signal

    class ProcessTree:
        """The session (and process group) a child started with ``start_new_session``."""

        def __init__(self, pid: int) -> None:
            self._group: int | None = pid

        def kill(self) -> None:
            if self._group is not None:
                try:
                    os.killpg(self._group, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # every member has already exited

        def close(self) -> None:
            """Kill any descendants left behind, then forget the group id (it may be reused)."""
            self.kill()
            self._group = None
