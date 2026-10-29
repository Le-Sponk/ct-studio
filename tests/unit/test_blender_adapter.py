"""P2-T05f: the typed Blender script adapter (``ctstudio.core.tools.blender.run_script``).

Measured on Blender 5.2.2 (TOOLS.md): a script exception exits 0 unless a nonzero
``--python-exit-code`` comes *before* ``--python``; an unreadable ``.blend`` exits 1 with
only a stdout report; ``sys.exit(N)`` exits N. The adapter always sets the failure code,
checks its inputs first and turns every nonzero exit into a typed, explained error.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ctstudio.core.errors import Cancelled, ToolNotFound, ToolTimedOut
from ctstudio.core.tools import blender
from ctstudio.core.tools.blender import FAILURE_EXIT, BlenderError, run_script
from ctstudio.core.tools.discovery import ToolLocation
from ctstudio.core.tools.process import CancelToken, RunResult

INPUTS = (
    Path(__file__).resolve().parents[1] / "fakes" / "recordings" / "blender" / "5.2.2" / "inputs"
)
pytestmark = pytest.mark.timeout(60)


def _folder(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "dossier é 日本"
    folder.mkdir(exist_ok=True)
    for name in names:
        shutil.copyfile(INPUTS / name, folder / name)
    return folder


# --- through the recorded fake ----------------------------------------------------------------


def test_script_runs_with_arguments_verbatim(fake_tools_path, tmp_path: Path) -> None:
    folder = _folder(tmp_path, "ok.py")
    result = run_script(None, folder / "ok.py", ["a b", "é", "--", "-b"])
    assert "ARGS ['a b', 'é', '--', '-b']" in result.stdout_tail
    [call] = fake_tools_path.calls()
    assert call["argv"] == [
        "-b",
        "--factory-startup",
        "--python-exit-code",
        str(FAILURE_EXIT),
        "--python",
        str(folder / "ok.py"),
        "--",
        "a b",
        "é",
        "--",
        "-b",
    ]
    assert Path(str(call["cwd"])) == folder


def test_blend_is_opened_before_the_script(fake_tools_path, tmp_path: Path) -> None:
    folder = _folder(tmp_path, "ok.py", "good.blend")
    result = run_script(folder / "good.blend", folder / "ok.py", ["x"])
    assert "Read blend:" in result.stdout_tail and "ARGS ['x']" in result.stdout_tail
    assert fake_tools_path.calls()[0]["argv"][:3] == [
        "-b",
        str(folder / "good.blend"),
        "--factory-startup",
    ]


def test_script_exception_is_a_typed_failure_with_the_traceback(
    fake_tools_path, tmp_path: Path
) -> None:
    folder = _folder(tmp_path, "boom.py")
    with pytest.raises(BlenderError, match="RuntimeError: boom") as caught:
        run_script(None, folder / "boom.py")
    assert caught.value.exit_code == FAILURE_EXIT
    assert caught.value.details is not None and "Traceback" in caught.value.details
    assert "Traceback" not in str(caught.value)


def test_script_exit_code_is_reported(fake_tools_path, tmp_path: Path) -> None:
    folder = _folder(tmp_path, "quit3.py")
    with pytest.raises(BlenderError, match="exited 3") as caught:
        run_script(None, folder / "quit3.py")
    assert caught.value.exit_code == 3


def test_unreadable_blend_is_explained(fake_tools_path, tmp_path: Path) -> None:
    folder = _folder(tmp_path, "ok.py")
    (folder / "junk.blend").write_bytes(b"not a track file\n" * 4)
    with pytest.raises(BlenderError, match=r"File format is not supported") as caught:
        run_script(folder / "junk.blend", folder / "ok.py")
    assert str(caught.value).startswith("Blender could not run ok.py: could not open junk.blend:")
    assert caught.value.exit_code == 1


# --- refused before running ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("blend", "script", "reason"),
    [
        (None, "missing.py", "script not found"),
        (None, "notes.txt", "Python"),
        ("missing.blend", "ok.py", "not found"),
        ("ok.py", "ok.py", ".blend"),
    ],
    ids=["missing script", "not python", "missing blend", "not a blend"],
)
def test_inputs_are_checked_first(
    blend: str | None, script: str, reason: str, fake_tools_path, tmp_path: Path
) -> None:
    folder = _folder(tmp_path, "ok.py")
    (folder / "notes.txt").write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(BlenderError, match=reason):
        run_script(None if blend is None else folder / blend, folder / script)
    assert fake_tools_path.calls() == []


@pytest.mark.parametrize("arg", ["a\x00b", 7])
def test_arguments_must_be_text_without_nul(arg: object, fake_tools_path, tmp_path: Path) -> None:
    folder = _folder(tmp_path, "ok.py")
    with pytest.raises(BlenderError, match="argument"):
        run_script(None, folder / "ok.py", [arg])  # type: ignore[list-item]
    assert fake_tools_path.calls() == []


def test_flatpak_blender_is_refused_until_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    folder = _folder(tmp_path, "ok.py")
    flatpak = ToolLocation(
        Path("/usr/bin/flatpak"), None, "flatpak", "flatpak", "org.blender.Blender"
    )
    monkeypatch.setattr(blender, "discover", lambda *_a, **_k: flatpak)
    with pytest.raises(ToolNotFound, match="blender") as caught:
        run_script(None, folder / "ok.py")
    assert caught.value.hint is not None and "Flatpak" in caught.value.hint


def test_missing_blender_is_tool_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(blender, "discover", lambda *_a, **_k: None)
    with pytest.raises(ToolNotFound, match="blender"):
        run_script(None, _folder(tmp_path, "ok.py") / "ok.py")


# --- runner options --------------------------------------------------------------------------


def _capture(monkeypatch: pytest.MonkeyPatch, result: RunResult) -> dict[str, object]:
    seen: dict[str, object] = {}

    def fake_run(cmd: list[object], **kwargs: object) -> RunResult:
        seen.update(kwargs, cmd=cmd)
        return result

    monkeypatch.setattr(blender, "run", fake_run)
    return seen


def test_runner_options_are_passed_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen = _capture(monkeypatch, RunResult(0, 0.1, "ok", "", None))
    folder = _folder(tmp_path, "ok.py")
    cancel, log = CancelToken(), tmp_path / "blender.log"
    tools = [tmp_path / "wiimm bin", tmp_path / "abmatt bin"]
    lines: list[str] = []
    run_script(
        None,
        folder / "ok.py",
        executable=tmp_path / "blender.exe",
        timeout=12.5,
        cancel=cancel,
        log_path=log,
        tool_dirs=tools,
        on_line=lambda _stream, line: lines.append(line),
    )
    assert seen["timeout"] == 12.5 and seen["cancel"] is cancel and seen["log_path"] == log
    assert seen["check"] is False and seen["cwd"] == folder and callable(seen["on_line"])
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["PATH"].split(blender.os.pathsep)[:2] == [str(p) for p in tools]
    assert seen["cmd"][0] == (tmp_path / "blender.exe").resolve()  # type: ignore[index]


def test_without_tool_folders_the_environment_is_inherited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = _capture(monkeypatch, RunResult(0, 0.1, "ok", "", None))
    run_script(None, _folder(tmp_path, "ok.py") / "ok.py", executable=tmp_path / "blender.exe")
    assert seen["env"] is None


@pytest.mark.parametrize("error", [ToolTimedOut(["blender"], 5, None), Cancelled("blender")])
def test_timeouts_and_cancellation_propagate(
    error: Exception, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(*_a: object, **_k: object) -> RunResult:
        raise error

    monkeypatch.setattr(blender, "run", fake_run)
    with pytest.raises(type(error)):
        run_script(None, _folder(tmp_path, "ok.py") / "ok.py", executable=tmp_path / "b.exe")


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (RunResult(FAILURE_EXIT, 0.1, "", "ValueError: x", None), "exited 113"),
        (
            RunResult(
                FAILURE_EXIT, 0.1, "", "Traceback\nKeyError: 'k'\nError: script failed, file", None
            ),
            "KeyError: 'k'",
        ),
        (
            RunResult(
                FAILURE_EXIT,
                0.1,
                "",
                "KeyError: 'inner'\n\nDuring handling of the above exception, another exception"
                " occurred:\n\nValueError: outer\n\nError: script failed, file: 'x.py', exiting.",
                None,
            ),
            r"ok\.py: ValueError: outer\n",
        ),
        (RunResult(1, 0.1, "", "", None), "exited 1"),
        (RunResult(-9, 0.1, "", "", None), "exited -9"),
    ],
    ids=["script's own 113", "last exception line", "chained", "plain 1", "killed"],
)
def test_failure_messages(
    result: RunResult, reason: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _capture(monkeypatch, result)
    with pytest.raises(BlenderError, match=reason) as caught:
        run_script(None, _folder(tmp_path, "ok.py") / "ok.py", executable=tmp_path / "b.exe")
    assert caught.value.exit_code == result.exit_code


def test_relative_paths_are_made_absolute(
    fake_tools_path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path, "ok.py", "good.blend")
    monkeypatch.chdir(tmp_path)
    run_script(Path(folder.name) / "good.blend", Path(folder.name) / "ok.py", ["x"])
    [call] = fake_tools_path.calls()
    assert call["argv"][1] == str(folder / "good.blend")
    assert call["argv"][call["argv"].index("--python") + 1] == str(folder / "ok.py")
