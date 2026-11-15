"""A CLI launch refusal must remain visible before the receipt handshake is awaited."""

import socket
import subprocess
from pathlib import Path

import pytest
import test_cli_project as cli


@pytest.mark.parametrize("returncode", [1, 2])
def test_cli_refusal_is_reported_before_waiting_for_editor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
) -> None:
    calls: list[str] = []
    diagnostic = "synthetic launch refusal: editor was not started"

    def refused(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
        calls.append("cli")
        return subprocess.CompletedProcess(list(args), returncode, "", diagnostic)

    def accept(server: socket.socket) -> tuple[socket.socket, tuple[str, int]]:
        calls.append("accept")
        raise RuntimeError("test waited for a child after the CLI had already refused")

    monkeypatch.setattr(cli, "_ctstudio", refused)
    monkeypatch.setattr(socket.socket, "accept", accept)
    error: BaseException | None = None
    try:
        cli.test_open_receipt_is_not_published_until_the_writer_closes(tmp_path, monkeypatch)
    except BaseException as exc:
        error = exc
    assert isinstance(error, AssertionError)
    assert diagnostic in str(error)
    assert calls == ["cli"]
