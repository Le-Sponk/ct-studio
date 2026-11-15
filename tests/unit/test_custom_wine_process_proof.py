"""Actual synthetic Wine processes through public custom dispatch, not editor loading."""

from __future__ import annotations

import json
import os
import threading
import time
from functools import partial
from pathlib import Path
from typing import cast

import pytest
from custom_wine_helpers import outcome, pe
from fakes.install import install_program

from ctstudio.core.tools import custom_editors, wine
from ctstudio.core.tools.editors import Launched
from ctstudio.core.tools.spec import CustomTool

CODE = r"""
import json, os, pathlib, sys, uuid
sys.stdout.reconfigure(encoding='utf-8')
record = {'argv': sys.argv[1:], 'cwd': os.getcwd(),
          'prefix': os.environ['WINEPREFIX'], 'pid': os.getpid()}
if sys.argv[1:3] == ['winepath.exe', '-w']:
    output = pathlib.Path(RECEIPTS) / (uuid.uuid4().hex + '.json')
    answer = 'Z:\\Wine proof\\' + pathlib.Path(sys.argv[3]).name
else:
    output = pathlib.Path('receipt.json')
    answer = None
pending = output.with_suffix('.pending')
pending.write_text(json.dumps(record), encoding='utf-8')
os.replace(pending, output)
if answer is not None:
    print(answer)
"""


def read_receipt(path: Path) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.is_file(), "real watched process did not atomically publish a receipt"
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def check_editor_receipt(
    data: dict[str, object], root: Path, document: Path, exe: Path, prefix: Path
) -> None:
    assert data["argv"] == [
        str(exe.resolve()),
        "{file}",
        "--file=Z:\\Wine proof\\" + document.name,
        "",
        "Z:\\Wine proof\\" + root.name,
        "Z:\\Wine proof\\" + root.name,
        "Z:\\Wine proof\\" + document.name,
        '"quoted";&|>$ 日本',
    ]
    assert Path(str(data["cwd"])).resolve() == root.resolve()
    assert data["prefix"] == str(prefix.resolve())
    assert isinstance(data["pid"], int) and data["pid"] != os.getpid()


def exercise_request(root: Path, exe: Path, launcher: Path, prefix: Path) -> tuple[int, object]:
    root.mkdir()
    document = root / "synthetic 日本.brres"
    document.write_bytes(b"unchanged synthetic document")
    tokens = (
        "{{file}}",
        "--file={file:}",
        "",
        "{project}",
        "{dir}",
        "{file}",
        '"quoted";&|>$ 日本',
    )
    tool = CustomTool("RiiStudio custom", exe, tokens)
    result = outcome(
        partial(
            custom_editors.open_custom,
            "riistudio",
            tool,
            document,
            project=root,
            wine_executable=launcher,
            wine_prefix=prefix,
        )
    )
    assert isinstance(result, Launched) and result.pid > 0, result
    data = read_receipt(root / "receipt.json")
    check_editor_receipt(data, root, document, exe, prefix)
    assert result.warnings == () and result.document == document.resolve()
    assert document.read_bytes() == b"unchanged synthetic document"
    (root / "launch-result.json").write_text(
        json.dumps({"launch_pid": result.pid, "writer_pid": data["pid"]}), encoding="utf-8"
    )
    return result.pid, data["pid"]


def check_request_helpers(helpers: list[dict[str, object]], root: Path, prefix: Path) -> None:
    wanted = [["winepath.exe", "-w", str(path)] for path in (root / "synthetic 日本.brres", root)]
    actual = [row for row in helpers if cast("list[str]", row["argv"]) in wanted]
    assert len(actual) == 2
    assert sorted(cast("list[str]", row["argv"]) for row in actual) == sorted(wanted)
    for row in actual:
        args = cast("list[str]", row["argv"])
        assert Path(str(row["cwd"])).resolve() == Path(args[2]).parent
        assert row["prefix"] == str(prefix.resolve())


def check_helpers(receipts: Path, tmp_path: Path, prefix: Path) -> None:
    helpers = [read_receipt(path) for path in receipts.glob("*.json")]
    assert len(helpers) == 4
    for number in range(2):
        root = (tmp_path / f"request é 日本 {number}").resolve()
        check_request_helpers(helpers, root, prefix)


def test_receipt_waits_for_atomic_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "receipt.json"
    release = threading.Event()
    failures: list[BaseException] = []
    real_is_file = Path.is_file

    def publish() -> None:
        try:
            assert release.wait(5)
            pending = target.with_suffix(".pending")
            pending.write_text('{"complete": true}', encoding="utf-8")
            os.replace(pending, target)
        except BaseException as error:
            failures.append(error)

    def observe(path: Path) -> bool:
        exists = real_is_file(path)
        if path == target:
            release.set()
        return exists

    monkeypatch.setattr(Path, "is_file", observe)
    writer = threading.Thread(target=publish)
    writer.start()
    try:
        result = outcome(partial(read_receipt, target))
    finally:
        release.set()
        writer.join(5)
    assert not writer.is_alive() and failures == []
    assert result == {"complete": True}, result


def test_two_public_requests_use_real_conversion_and_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(custom_editors, "current_os", lambda: "linux")
    receipts = tmp_path / "helper receipts"
    receipts.mkdir()
    launcher = install_program(
        tmp_path / "Wine é 日本" / "wine", CODE.replace("RECEIPTS", repr(str(receipts)))
    )
    exe = pe(tmp_path / "synthetic editor.ExE")
    prefix = tmp_path / "prefix é 日本"
    prefix.mkdir()
    registry = prefix / "system.reg"
    registry.write_bytes(b"#arch=win64\n")
    before = {path: path.read_bytes() for path in (exe, launcher, registry)}
    assert wine.WATCH_SECONDS == 3.0
    results = [
        exercise_request(tmp_path / f"request é 日本 {n}", exe, launcher, prefix) for n in range(2)
    ]
    assert results[0][0] != results[1][0] and results[0][1] != results[1][1]
    assert before == {path: path.read_bytes() for path in before}
    assert wine.WATCH_SECONDS == 3.0
    check_helpers(receipts, tmp_path, prefix)
