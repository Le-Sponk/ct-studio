"""P5-T07d2: joined editor preparation and explicit saved-choice dispatch ownership."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from editor_owner_helpers import (
    BUILTIN,
    CUSTOM,
    EditorWork,
    Results,
    editor_owner,
    outcome,
    snapshot_for,
)
from fakes.install import install_program
from PySide6.QtCore import QCoreApplication
from pytestqt.qtbot import QtBot

from ctstudio.core.errors import CTStudioError, ProjectError
from ctstudio.core.project.project import Project
from ctstudio.core.project.settings import SettingsError
from ctstudio.core.tools import editors
from ctstudio.core.tools.saved_editors import EditorChoice
from ctstudio.gui.editor_launch import EditorLaunchService, PreparedEditors
from ctstudio.gui.launch_controller import THREAD_NAME, LaunchController

pytestmark = [pytest.mark.gui, pytest.mark.timeout(60)]


def prepared(
    qtbot: QtBot, owner: LaunchController, project: Project, document: Path
) -> PreparedEditors | None:
    """The delivered preparation receipt (None when it failed; callers assert the type)."""
    results = Results(owner)
    assert owner.prepare_editors(project, document) is True
    receipt = results.settle(qtbot, 1).receipt
    return receipt if isinstance(receipt, PreparedEditors) else None


def test_preparation_runs_joined_on_the_launch_worker_with_exact_identity(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = EditorWork()
    with editor_owner(tmp_path, work) as (owner, project, document):
        results = Results(owner)
        manifest = project.manifest
        assert owner.prepare_editors(project, document) is True
        assert work.entered.wait(5) and owner.busy
        assert owner.prepare_editors(project, document) is False  # one request at a time
        work.gate.set()
        result = results.settle(qtbot, 1)
        kind, called, path, choice, thread = work.calls[0]
        assert (kind, called, path, choice) == ("prepare", project, document, None)
        assert thread.name == THREAD_NAME and thread is not threading.main_thread()
        assert not thread.is_alive(), "delivery must follow the worker's join"
        assert results.threads == [threading.main_thread()]
        assert result.project is project and result.root == project.root
        assert result.manifest is manifest and result.component_id is None
        assert result.editor_action == "prepare" and result.document == document
        assert result.choice is None and result.error is None
        assert result.receipt == snapshot_for(document)
        assert isinstance(result.receipt, PreparedEditors)
        assert len(work.calls) == 1


def test_open_dispatches_an_offered_choice_of_the_latest_preparation(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = EditorWork()
    work.gate.set()
    with editor_owner(tmp_path, work) as (owner, project, document):
        snapshot = prepared(qtbot, owner, project, document)
        assert isinstance(snapshot, PreparedEditors)
        results = Results(owner)
        assert outcome(lambda: owner.open_editor(project, snapshot, CUSTOM)) is True
        result = results.settle(qtbot, 1)
        kind, called, path, choice, thread = work.calls[-1]
        assert (kind, called, path, choice) == ("open", project, document, CUSTOM)
        assert thread.name == THREAD_NAME
        assert result.receipt is work.launched and result.error is None
        assert result.editor_action == "open" and result.choice == CUSTOM
        assert result.document == document and result.component_id is None
        assert (
            outcome(lambda: owner.open_editor(project, snapshot, BUILTIN)) is True
        )  # still the latest
        assert results.settle(qtbot, 2).choice == BUILTIN


def test_stale_or_unoffered_open_requests_are_refused_without_dispatch(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = EditorWork()
    work.gate.set()
    with editor_owner(tmp_path, work) as (owner, project, document):
        never = snapshot_for(document)
        refused = outcome(lambda: owner.open_editor(project, never, CUSTOM))
        assert isinstance(refused, ProjectError) and refused.hint, refused
        first = prepared(qtbot, owner, project, document)
        second = prepared(qtbot, owner, project, document)
        assert isinstance(first, PreparedEditors) and isinstance(second, PreparedEditors)
        assert first is not second
        assert isinstance(outcome(lambda: owner.open_editor(project, first, CUSTOM)), ProjectError)
        other = EditorChoice("custom", "not offered")
        assert isinstance(outcome(lambda: owner.open_editor(project, second, other)), ProjectError)
        with editor_owner(tmp_path / "other", work) as (_owner, foreign, _document):
            wrong = outcome(lambda: owner.open_editor(foreign, second, CUSTOM))
            assert isinstance(wrong, ProjectError)
        project.manifest = replace(project.manifest)  # a saved change makes it stale
        assert isinstance(outcome(lambda: owner.open_editor(project, second, CUSTOM)), ProjectError)
        reader = Project.open(project.root)  # another handle on the same folder
        try:
            reader.manifest = project.manifest
            assert reader.root == project.root and reader is not project
            third = prepared(qtbot, owner, project, document)
            assert isinstance(third, PreparedEditors)
            borrowed = outcome(lambda: owner.open_editor(reader, third, CUSTOM))
            assert isinstance(borrowed, ProjectError), "another handle reused these choices"
        finally:
            reader.close()
        results = Results(owner)
        work.gate.clear()
        work.entered.clear()
        assert owner.prepare_editors(project, document) is True
        assert work.entered.wait(5)
        busy = outcome(lambda: owner.open_editor(project, third, CUSTOM))
        assert busy is False, f"a busy owner must decline, not refuse: {busy!r}"
        work.gate.set()
        results.settle(qtbot, 1)
        assert [call[0] for call in work.calls] == ["prepare"] * 4
        assert not owner.busy


def test_shutdown_and_a_failed_preparation_both_retire_the_latest_choices(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = EditorWork()
    work.gate.set()
    with editor_owner(tmp_path, work) as (owner, project, document):
        snapshot = prepared(qtbot, owner, project, document)
        assert isinstance(snapshot, PreparedEditors)
        assert owner.shutdown(10) is True
        assert isinstance(
            outcome(lambda: owner.open_editor(project, snapshot, CUSTOM)), ProjectError
        )
        again = prepared(qtbot, owner, project, document)
        assert isinstance(again, PreparedEditors)
        failure = ProjectError("Synthetic preparation failure.", hint="Retry.")
        work.error = failure
        results = Results(owner)
        assert owner.prepare_editors(project, document) is True
        result = results.settle(qtbot, 1)
        assert result.error is failure and result.receipt is None
        assert isinstance(outcome(lambda: owner.open_editor(project, again, CUSTOM)), ProjectError)
        assert [call[0] for call in work.calls] == ["prepare", "prepare", "prepare"]


@pytest.mark.parametrize("kind", ["prepare", "open"])
@pytest.mark.parametrize(
    "error",
    [
        KeyboardInterrupt(),
        SystemExit(3),
        RuntimeError("crash"),
        editors.EditorError("brawlcrate", Path("x.brres"), "synthetic", hint="Choose again."),
    ],
    ids=["interrupt", "exit", "crash", "typed"],
)
def test_every_editor_failure_is_delivered_exactly_once_and_frees_the_owner(
    qtbot: QtBot, tmp_path: Path, kind: str, error: BaseException
) -> None:
    work = EditorWork()
    work.gate.set()
    with editor_owner(tmp_path, work) as (owner, project, document):
        snapshot = prepared(qtbot, owner, project, document)
        assert isinstance(snapshot, PreparedEditors)
        work.error = error
        results = Results(owner)
        started = (
            owner.prepare_editors(project, document)
            if kind == "prepare"
            else owner.open_editor(project, snapshot, CUSTOM)
        )
        assert started is True
        result = results.settle(qtbot, 1)
        assert result.error is error and result.receipt is None
        assert result.editor_action == kind
        qtbot.wait(50)
        assert len(results.items) == 1


def test_one_owner_spans_editor_and_existing_operations(qtbot: QtBot, tmp_path: Path) -> None:
    work = EditorWork()
    with editor_owner(tmp_path, work) as (owner, project, document):
        results = Results(owner)
        assert owner.prepare_editors(project, document) is True
        assert work.entered.wait(5)
        assert owner.start(project, None) is False
        assert owner.start(project, "kcl") is False
        assert owner.assign(project, "kcl", document, reference=True) is False
        assert owner.reconcile(project, "kcl", "lock") is False
        work.gate.set()
        snapshot = results.settle(qtbot, 1).receipt
        assert isinstance(snapshot, PreparedEditors)
        work.gate.clear()
        work.entered.clear()
        assert outcome(lambda: owner.open_editor(project, snapshot, BUILTIN)) is True
        assert work.entered.wait(5)
        assert owner.prepare_editors(project, document) is False
        assert outcome(lambda: owner.open_editor(project, snapshot, CUSTOM)) is False
        assert owner.start(project, "kcl") is False
        work.gate.set()
        assert results.settle(qtbot, 2).receipt is work.launched
        assert owner.start(project, "kcl") is True  # existing operations resume afterwards
        results.settle(qtbot, 3)
        assert owner.prepare_editors(project, document) is True
        assert results.settle(qtbot, 4).editor_action == "prepare"
        assert [call[0] for call in work.calls] == ["prepare", "open", "prepare"]


def test_shutdown_timeout_keeps_ownership_and_drops_a_queued_preparation(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = EditorWork()
    with editor_owner(tmp_path, work) as (owner, project, document):
        results = Results(owner)
        assert owner.prepare_editors(project, document) is True
        assert work.entered.wait(5)
        assert owner.shutdown(0.05) is False and owner.busy
        work.gate.set()
        assert owner.shutdown(10) is True and not owner.busy
        QCoreApplication.sendPostedEvents()  # the joined worker's queued result arrives now
        qtbot.wait(20)
        assert results.items == []
        assert len(work.snapshots) == 1, "the worker's real receipt was not recorded"
        late = work.snapshots[0]  # the exact queued receipt, never delivered
        assert isinstance(outcome(lambda: owner.open_editor(project, late, CUSTOM)), ProjectError)
        assert [call[0] for call in work.calls] == ["prepare"]


@pytest.mark.parametrize("kind", ["prepare", "open"])
def test_uncertain_native_start_keeps_the_owner_and_never_authorises_choices(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    work = EditorWork()
    work.gate.set()
    original = threading.Thread.start
    interrupt = KeyboardInterrupt()

    def started_then_interrupted(thread: threading.Thread) -> None:
        original(thread)
        if thread.name == THREAD_NAME:
            raise interrupt

    with editor_owner(tmp_path, work) as (owner, project, document):
        first = None
        if kind == "open":
            first = prepared(qtbot, owner, project, document)
            assert isinstance(first, PreparedEditors)
        results = Results(owner)
        monkeypatch.setattr(threading.Thread, "start", started_then_interrupted)
        try:
            started = outcome(
                lambda: (
                    owner.prepare_editors(project, document)
                    if first is None
                    else owner.open_editor(project, first, CUSTOM)
                )
            )
        finally:
            monkeypatch.undo()
        assert started is False, started
        assert owner.busy, "an acknowledged worker must keep the owner busy"
        result = results.settle(qtbot, 1)
        assert result.error is interrupt and result.receipt is None
        assert result.editor_action == kind
        expected = ["prepare"] if first is None else ["prepare", "open"]
        assert [call[0] for call in work.calls] == expected
        late = work.snapshots[-1]  # the worker's exact receipt from the uncertain start
        if first is None:
            refused = outcome(lambda: owner.open_editor(project, late, CUSTOM))
            assert isinstance(refused, ProjectError), "an uncertain start authorised choices"
        assert [call[0] for call in work.calls] == expected


def test_an_editor_request_without_a_document_never_falls_through_to_blender(
    qtbot: QtBot, tmp_path: Path
) -> None:
    work = EditorWork()
    work.gate.set()
    with editor_owner(tmp_path, work) as (owner, project, _document):
        results = Results(owner)
        assert owner.prepare_editors(project, cast("Path", None)) is True  # untyped caller
        result = results.settle(qtbot, 1)
        assert result.receipt is None, f"another action ran: {result.receipt!r}"
        assert isinstance(result.error, ProjectError) and result.error.hint
        assert work.calls == []


CHILD = r"""
import json, os, pathlib, sys, uuid
folder = pathlib.Path(OUTPUT)
record = {'argv': sys.argv[1:], 'cwd': os.getcwd(), 'pid': os.getpid(), 'program': PROGRAM}
pending = folder / (uuid.uuid4().hex + '.pending')
pending.write_text(json.dumps(record), encoding='utf-8')
os.replace(pending, pending.with_suffix('.json'))
"""


def save_settings(path: Path, tool: Path, revision: int) -> None:
    fields = {
        "format": 1,
        "custom_tools": {
            CUSTOM.tool_id: {
                "name": "Custom 日本",
                "exe": str(tool),
                "args_template": ["{file}", f"--revision={revision} é 日本"],
            }
        },
    }
    path.write_bytes((json.dumps(fields, ensure_ascii=True) + "\n").encode("utf-8"))


def child_records(folder: Path, count: int) -> list[dict[str, object]]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        found = sorted(folder.glob("*.json"))
        if len(found) >= count:
            return [json.loads(item.read_text(encoding="utf-8")) for item in found]
        time.sleep(0.05)
    raise AssertionError(f"expected {count} child record(s) in {folder}")


def test_real_dispatch_rereads_fresh_settings_and_reports_damaged_ones(
    qtbot: QtBot, tmp_path: Path
) -> None:
    output = tmp_path / "records 日本"
    output.mkdir()
    tools = [
        install_program(
            tmp_path / f"tool {n} é 日本" / "editor",
            CHILD.replace("OUTPUT", repr(str(output))).replace("PROGRAM", repr(f"tool-{n}")),
        )
        for n in (0, 1)
    ]
    settings = tmp_path / "machine settings 日本.json"
    save_settings(settings, tools[0], 0)
    service = EditorLaunchService(settings)
    with editor_owner(tmp_path / "project", service) as (owner, project, document):
        snapshot = prepared(qtbot, owner, project, document)
        assert isinstance(snapshot, PreparedEditors)
        assert CUSTOM in [option.choice for option in snapshot.options]
        save_settings(settings, tools[1], 1)  # changed after preparation, before dispatch
        results = Results(owner)
        assert outcome(lambda: owner.open_editor(project, snapshot, CUSTOM)) is True
        result = results.settle(qtbot, 1)
        receipt = result.receipt
        assert isinstance(receipt, editors.Launched), result.error
        assert receipt == editors.Launched(CUSTOM.tool_id, receipt.pid, document.resolve(), ())
        record = child_records(output, 1)[0]
        assert record["program"] == "tool-1"
        assert record["argv"] == [str(document.resolve()), "--revision=1 é 日本"]
        assert record["pid"] != os.getpid()
        settings.write_bytes(b"{damaged")
        assert outcome(lambda: owner.open_editor(project, snapshot, CUSTOM)) is True
        damaged = results.settle(qtbot, 2)
        assert isinstance(damaged.error, SettingsError) and damaged.receipt is None
        assert isinstance(damaged.error, CTStudioError) and damaged.error.hint
        qtbot.wait(200)
        assert len(list(output.glob("*.json"))) == 1, "a damaged settings file started a child"
