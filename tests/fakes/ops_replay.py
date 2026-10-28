"""Replay recorded real-tool operation runs against the fakes (P2-T04b/c).

Shared by the per-tool fake tests: ``stand_ins`` rebuilds a case's fixture inputs from the
recording, and ``assert_like_recording`` checks a fake run against the real one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from fake_runtime import UNMODELLED_EXIT


def stand_ins(record: Mapping[str, object], kept: Path) -> Callable[[str], bytes]:
    """Fixture reader for a replay: the copy kept in ``kept`` if any, else a stand-in.

    A stand-in has the recorded size and leading bytes, which is all the binary-format
    fakes look at. Inputs a fake must parse (rszst's DAE) are kept whole by the recorder.
    """
    inputs: Mapping[str, Mapping[str, object]] = record["inputs"]  # type: ignore[assignment]

    def fixture(name: str) -> bytes:
        size = int(str(inputs[name]["size"]))
        head = bytes.fromhex(str(inputs[name]["head"]))
        path = kept / name
        if path.is_file():
            data = path.read_bytes()
            assert len(data) == size, f"{path} is not the recorded input; re-record"
            assert data.startswith(head), f"{path} is not the recorded input; re-record"
            return data
        return head + b"\0" * (size - len(head))

    return fixture


def assert_like_recording(fake: Mapping[str, object], record: Mapping[str, object]) -> None:
    """Exit code, stderr and file effects exactly; stdout as ``compare`` says."""
    compare = record["compare"]
    if compare == "unmodelled":
        assert fake["exit_code"] == UNMODELLED_EXIT, "the fake must refuse this case"
        assert (fake["stdout"], fake["files"]) == ("", {})
        return
    # A fake never invents findings: where the real exit code reports them, it exits 0.
    expected_exit = 0 if compare == "findings" else record["exit_code"]
    assert fake["exit_code"] == expected_exit
    assert fake["stderr"] == record["stderr"]
    assert fake["files"] == record["files"]
    if compare == "exact":
        assert fake["stdout"] == record["stdout"]
        return
    lines = str(fake["stdout"]).splitlines(keepends=True)
    assert lines, "a fake prints at least the real opening line"
    assert lines == str(record["stdout"]).splitlines(keepends=True)[: len(lines)]
