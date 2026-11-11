"""Notice files changed outside CT Studio (P5-T06a, ARCHITECTURE §11, ADR-011).

``watch_plan(root, manifest)`` says what to watch: the project folder (with everything in it)
and, for the ``.blend`` and supplied files kept outside it, their folders, watched flat for
those names only. A folder is watched, never a single file, so a program that saves by
writing a temporary file and renaming it over the old one is still noticed.

``ProjectWatcher`` runs watchfiles on named background threads (``ctstudio-watch`` for the
project folder, ``ctstudio-watch-outside`` for outside folders) and passes on only changes
that can alter a part's status (``ChangeFilter``): CT Studio's own bookkeeping in
``.ctstudio/`` (all but the made files in ``.ctstudio/stage/``), the finished tracks in
``build/``, ``.git/`` and Blender's backups (``.blend1``, ``.blend2``…) and save files
(``.blend@``) are left out. Changes in one burst arrive together (``DEBOUNCE_MS``).

Starting does no disk work on the caller's thread. A folder that cannot be watched, a project
folder that goes away, or a watch that ends without being asked is reported through
``on_error`` from the watcher's thread, and the whole watcher then stops (``intact`` turns
False, so following the same plan again starts a whole new one). An outside folder that is
missing (an unplugged drive) is not an error: status already reports the file missing; it is
checked for every ``TICK_MS``, and its going away or coming back is reported as a change, after
which it is watched again.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import watchfiles

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.errors import ProjectError
from ctstudio.core.project.manifest import Manifest

WATCH_THREAD = "ctstudio-watch"
DEBOUNCE_MS = 500  # ARCHITECTURE §11: a save writes several files; report them once
STEP_MS = 50  # how soon after the last change of a burst it is reported
TICK_MS = 250  # the watcher wakes this often when nothing changes (first tick: watching)
_STAGE = (".ctstudio", "stage")  # components.state.GENERATED_DIR
_IGNORED_TOP = (".git", "build")  # core.build.assemble.BUILD_DIR: finished tracks
_BLENDER_BACKUP = re.compile(r"\.blend(?:\d+|@)$", re.IGNORECASE)
_HINT = "After changing files outside CT Studio, press Refresh statuses."
_GONE = "the folder is gone"
_ENDED = "watching ended unexpectedly"


class _Gone(Exception):
    """Watching ended without being asked (the reason is the message)."""


type Names = frozenset[str] | None  # None: everything in the folder
type OnChange = Callable[[frozenset[Path]], None]
type OnError = Callable[[ProjectError], None]
type Watch = Callable[..., Iterable[Iterable[tuple[object, str]]]]


@dataclass(frozen=True)
class WatchPlan:
    root: Path
    outside: Mapping[Path, Names]  # folder outside the project → the names that matter there


def watch_plan(root: Path, manifest: Manifest) -> WatchPlan:
    """What to watch for ``root`` with ``manifest`` (paths only: nothing is read)."""
    outside: dict[Path, Names] = {}
    for text, is_folder in _chosen_paths(manifest):
        path = Path(os.path.normpath(os.path.join(root, text)))
        if path.is_relative_to(root):
            continue
        folder, names = (path, None) if is_folder else (path.parent, frozenset({path.name}))
        known = outside.get(folder, frozenset())
        outside[folder] = None if known is None or names is None else known | names
    return WatchPlan(root, outside)


def _chosen_paths(manifest: Manifest) -> Iterator[tuple[str, bool]]:
    """The ``.blend`` and every supplied file or folder in use, with whether it is a folder."""
    if manifest.project.blend:
        yield manifest.project.blend, False
    for spec in COMPONENTS:
        if spec.manifest_table in (None, "project"):
            continue
        table = getattr(manifest.components, spec.manifest_table)
        if table.mode == "manual" and table.file:
            yield table.file, spec.kind is None  # post-effects: a folder


def _key(path: Path | str) -> str:
    """Comparable text for a path under this system's case rule."""
    return os.path.normcase(os.path.normpath(path))


def _variants(path: Path) -> frozenset[str]:
    """The path as written and as the system resolves it (links, Windows short names)."""
    return frozenset({_key(path), _key(path.resolve())})


def _inside(key: str, folders: frozenset[str]) -> tuple[str, ...] | None:
    """The parts of ``key`` below one of ``folders`` (``()`` for the folder), else None."""
    for folder in folders:
        if key == folder:
            return ()
        prefix = folder.rstrip(os.sep) + os.sep
        if key.startswith(prefix):
            return tuple(key[len(prefix) :].split(os.sep))
    return None


def _counts_inside(parts: Sequence[str]) -> bool:
    if not parts or parts[0] in _IGNORED_TOP:
        return False
    if parts[0] == _STAGE[0] and tuple(parts[:2]) != _STAGE:
        return False
    return _BLENDER_BACKUP.search(parts[-1]) is None


@dataclass(frozen=True)
class ChangeFilter:
    """Decides which reported paths can change a status (resolves paths: not on the UI)."""

    roots: frozenset[str]
    outside: tuple[tuple[frozenset[str], frozenset[str] | None], ...]

    @classmethod
    def of(cls, plan: WatchPlan) -> ChangeFilter:
        outside = tuple(
            (_variants(folder), None if names is None else frozenset(map(_key, names)))
            for folder, names in plan.outside.items()
        )
        return cls(_variants(plan.root), outside)

    def relevant(self, raw: str) -> bool:
        key = _key(raw)
        parts = _inside(key, self.roots)
        if parts is not None:
            return _counts_inside(parts)
        parent, name = os.path.split(key)
        for folders, names in self.outside:
            if names is None:
                if _inside(key, folders) is not None:
                    return True
            elif parent in folders and name in names:
                return True
        return False


def _reason(exc: Exception) -> str:
    if isinstance(exc, OSError):
        if exc.strerror:
            return exc.strerror
        if exc.errno is not None:
            return "a system error"
    return (str(exc) or type(exc).__name__).rstrip(".")


def _cannot_watch(where: str, exc: Exception) -> ProjectError:
    error = ProjectError(
        f"CT Studio cannot notice changes in {where} ({_reason(exc)}).",
        hint=_HINT,
        details=repr(exc),
    )
    error.__cause__ = exc
    return error


class ProjectWatcher:
    """Watches one plan until ``stop``; changes and failures arrive on its own threads."""

    def __init__(
        self,
        plan: WatchPlan,
        on_change: OnChange,
        on_error: OnError,
        *,
        watch: Watch = watchfiles.watch,
    ) -> None:
        self.plan = plan
        self._on_change, self._on_error, self._watch = on_change, on_error, watch
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._unsettled = 0
        self._threads: list[threading.Thread] = []

    @property
    def alive(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    @property
    def intact(self) -> bool:
        """Watching everything it should: started and not stopped. A thread that ends for any
        reason stops the whole watcher, so this also means no thread has ended."""
        return bool(self._threads) and not self._stop.is_set()

    def start(self) -> None:
        """Start the threads (no disk work here); ``ProjectError`` if the system refuses."""
        jobs: list[tuple[str, Callable[[], None]]] = [(WATCH_THREAD, self._watch_project)]
        if self.plan.outside:
            jobs.append((f"{WATCH_THREAD}-outside", self._watch_outside))
        self._unsettled = len(jobs)
        for name, job in jobs:
            thread = threading.Thread(target=job, name=name, daemon=True)
            try:
                thread.start()
            except RuntimeError as exc:
                self.stop()
                raise ProjectError(
                    "CT Studio could not start watching the project for changes.",
                    hint=f"Close other programs or restart CT Studio. {_HINT}",
                    details=str(exc),
                ) from exc
            self._threads.append(thread)

    def wait_ready(self, timeout: float) -> bool:
        """True once every thread is watching (or has given up)."""
        return self._ready.wait(timeout)

    def stop(self) -> None:
        """Ask every thread to end (they notice within ``STEP_MS``); does not wait."""
        self._stop.set()

    def join(self, timeout: float) -> bool:
        """Wait up to ``timeout`` s in total; True when no thread is left."""
        end = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0.0, end - time.monotonic()))
        return not self.alive

    def _watch_project(self) -> None:
        self._guarded(str(self.plan.root), self._project_loop)

    def _watch_outside(self) -> None:
        self._guarded(", ".join(map(str, self.plan.outside)), self._outside_loop)

    def _guarded(self, where: str, loop: Callable[[Callable[[], None]], None]) -> None:
        """Run ``loop``; on a failure not asked for, tell the user and end the other thread."""
        settled = False

        def settle() -> None:
            nonlocal settled
            if not settled:
                settled = True
                self._settle()

        try:
            loop(settle)
        except Exception as exc:  # the thread ends; the user must learn that watching stopped
            if not self._stop.is_set():
                self._on_error(_cannot_watch(where, exc))
        finally:
            settle()
            self._stop.set()  # half a watcher is not kept: Refresh starts a whole one

    def _project_loop(self, settle: Callable[[], None]) -> None:
        root = self.plan.root
        check = ChangeFilter.of(self.plan)
        for batch in self._batches((root,), recursive=True):
            settle()
            if not root.is_dir():  # some systems keep the watch quietly alive
                raise _Gone(_GONE)
            self._pass_on(check, batch)
        if not self._stop.is_set():
            raise _Gone(_GONE if not root.is_dir() else _ENDED)

    def _outside_loop(self, settle: Callable[[], None]) -> None:
        """Outside folders may come and go (a drive): each time is a change, then re-watch."""
        check = ChangeFilter.of(self.plan)
        current = self._present()
        while not self._stop.is_set():
            if current:
                self._watch_present(current, check, settle)
            else:
                settle()
                self._stop.wait(TICK_MS / 1000)
            now = self._present()
            if now != current:
                self._on_change(frozenset(now).symmetric_difference(current))
                current = now

    def _watch_present(
        self, folders: tuple[Path, ...], check: ChangeFilter, settle: Callable[[], None]
    ) -> None:
        """Watch ``folders`` until stopped or until the set of present folders changes."""
        batches = self._batches(folders, recursive=False)
        try:
            for batch in batches:
                settle()
                self._pass_on(check, batch)
                if self._present() != folders:
                    return
        except Exception:
            if self._present() == folders:
                raise
            return  # a watched folder went away under the watch: the caller re-watches
        finally:
            close = getattr(batches, "close", None)
            if close is not None:
                close()
        if not self._stop.is_set() and self._present() == folders:
            raise _Gone(_ENDED)

    def _present(self) -> tuple[Path, ...]:
        return tuple(folder for folder in self.plan.outside if folder.is_dir())

    def _pass_on(self, check: ChangeFilter, batch: Iterable[tuple[object, str]]) -> None:
        changed = frozenset(Path(raw) for _kind, raw in batch if check.relevant(raw))
        if changed:
            self._on_change(changed)

    def _batches(
        self, paths: tuple[Path, ...], *, recursive: bool
    ) -> Iterable[Iterable[tuple[object, str]]]:
        return self._watch(
            *paths,
            watch_filter=None,
            debounce=DEBOUNCE_MS,
            step=STEP_MS,
            stop_event=self._stop,
            rust_timeout=TICK_MS,
            yield_on_timeout=True,
            raise_interrupt=False,
            recursive=recursive,
        )

    def _settle(self) -> None:
        with self._lock:
            self._unsettled -= 1
            if self._unsettled <= 0:
                self._ready.set()
