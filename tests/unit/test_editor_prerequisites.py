"""P5-T07b: refuse unsafe Lorenzi dispatch before editor discovery or launch."""

import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from editor_test_helpers import document as make_document
from fakes.install import install_program

from ctstudio.core.tools import editors, wine
from ctstudio.core.tools.discovery import Launcher, ToolLocation
from ctstudio.core.tools.editors import EditorError, Launched
from ctstudio.core.tools.spec import ToolSpec

pytestmark = pytest.mark.timeout(30)
LORENZI = "kmp_editor_lorenzi"


def _outcome[T](action: Callable[[], T]) -> T | Exception:
    try:
        return action()
    except Exception as exc:
        return exc


def _dispatch_spies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, launcher: Launcher
) -> list[str]:
    calls: list[str] = []
    exe = tmp_path / "synthetic editor"
    exe.write_bytes(b"not executed: dispatch spy")

    def discover(spec: ToolSpec, **kwargs: object) -> ToolLocation:
        calls.append(f"discover:{spec.id}")
        return ToolLocation(exe, None, "standard", launcher if spec.id != "wine" else "direct")

    def native(*args: object, **kwargs: object) -> int:
        calls.append("native")
        return 111

    def through_wine(*args: object, **kwargs: object) -> int:
        calls.append("wine")
        return 222

    monkeypatch.setattr(editors, "discover", discover)
    monkeypatch.setattr(editors, "launch_detached", native)
    monkeypatch.setattr(wine, "launch", through_wine)
    return calls


def _assert_refusal(result: object, document: Path) -> None:
    assert isinstance(result, EditorError), "ineligible Lorenzi document must be refused"
    assert result.document == document.resolve() and result.tool_id == LORENZI
    assert "course.kcl" in str(result)
    assert result.hint and "course.kcl" in result.hint and "beside" in result.hint


@pytest.mark.parametrize("launcher", ["direct", "wine"])
@pytest.mark.parametrize(
    "companion", ["missing", "Course.kcl", "COURSE.KCL", "course.KCL", "directory", "elsewhere"]
)
def test_missing_lorenzi_collision_refuses_before_discovery_or_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, companion: str, launcher: Launcher
) -> None:
    folder = tmp_path / "track é 日本"
    folder.mkdir()
    document = folder / "course.kmp"
    document.write_bytes(b"synthetic KMP placeholder")
    if companion == "directory":
        (folder / "course.kcl").mkdir()
    elif companion == "elsewhere":
        (tmp_path / "course.kcl").write_bytes(b"unrelated collision")
        monkeypatch.chdir(tmp_path)
    elif companion != "missing":
        (folder / companion).write_bytes(b"wrong-case collision")
    before = {p.name: p.read_bytes() if p.is_file() else None for p in folder.iterdir()}
    calls = _dispatch_spies(monkeypatch, tmp_path, launcher)
    result = _outcome(lambda: editors.open_in(LORENZI, document, wine_prefix=tmp_path / "prefix"))
    assert isinstance(result, EditorError), "missing collision must be refused before discovery"
    assert result.document == document and result.tool_id == "kmp_editor_lorenzi"
    assert "course.kcl" in str(result) and result.hint
    assert calls == [], "an ineligible document must not inspect installed editors"
    assert {p.name: p.read_bytes() if p.is_file() else None for p in folder.iterdir()} == before
    if companion == "elsewhere":
        assert (tmp_path / "course.kcl").read_bytes() == b"unrelated collision"


@pytest.mark.parametrize("launcher", ["direct", "wine"])
@pytest.mark.parametrize("fault", ["iterdir-call", "iterdir-next", "stat"])
def test_collision_inspection_error_is_actionable_and_precedes_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, launcher: Launcher
) -> None:
    document = make_document(tmp_path, "course.kmp", eligible_for=LORENZI)
    collision = document.with_name("course.kcl")
    before = document.read_bytes(), collision.read_bytes()
    calls = _dispatch_spies(monkeypatch, tmp_path, launcher)
    error = (
        PermissionError("synthetic collision stat denied")
        if fault == "stat"
        else OSError("synthetic folder iteration failed")
    )
    inspections: list[str] = []
    original_stat = Path.stat

    def blocked(folder: Path) -> Iterator[Path]:
        inspections.append("iterdir-call")
        raise error

    def interrupted(folder: Path) -> Iterator[Path]:
        yield folder / "unrelated.txt"
        inspections.append("iterdir-next")
        raise error

    def failed_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == collision:
            inspections.append("stat")
            raise error
        return original_stat(path, follow_symlinks=follow_symlinks)

    with monkeypatch.context() as scoped:
        if fault == "stat":
            scoped.setattr(Path, "stat", failed_stat)
        else:
            scoped.setattr(Path, "iterdir", blocked if fault == "iterdir-call" else interrupted)
        result = _outcome(
            lambda: editors.open_in(LORENZI, document, wine_prefix=tmp_path / "prefix")
        )
    _assert_refusal(result, document)
    assert isinstance(result, EditorError) and result.__cause__ is error
    assert inspections == [fault], "the intended failing filesystem operation must run"
    assert calls == [], "inspection failure must precede discovery, Wine and native dispatch"
    assert (document.read_bytes(), collision.read_bytes()) == before


@pytest.mark.parametrize("launcher", ["direct", "wine"])
def test_two_documents_have_independent_collision_eligibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launcher: Launcher
) -> None:
    eligible = make_document(tmp_path, "custom.KMP", "eligible é 日本", eligible_for=LORENZI)
    other = make_document(tmp_path, "course.kmp", "ineligible")
    before = (
        eligible.read_bytes(),
        other.read_bytes(),
        eligible.with_name("course.kcl").read_bytes(),
    )
    calls = _dispatch_spies(monkeypatch, tmp_path, launcher)
    # A valid document must not grant eligibility to the next document, nor vice versa.
    first = _outcome(lambda: editors.open_in(LORENZI, eligible, wine_prefix=tmp_path / "prefix"))
    assert isinstance(first, Launched) and first.document == eligible.resolve()
    expected = (
        [f"discover:{LORENZI}", "native"]
        if launcher == "direct"
        else [f"discover:{LORENZI}", "discover:wine", "wine"]
    )
    assert calls == expected
    calls.clear()
    _assert_refusal(_outcome(lambda: editors.open_in(LORENZI, other)), other)
    assert calls == []
    last = _outcome(lambda: editors.open_in(LORENZI, eligible, wine_prefix=tmp_path / "prefix"))
    assert isinstance(last, Launched) and last.document == eligible.resolve()
    assert calls == expected
    assert (
        eligible.read_bytes(),
        other.read_bytes(),
        eligible.with_name("course.kcl").read_bytes(),
    ) == before


@pytest.mark.parametrize("launcher", ["direct", "wine"])
def test_collision_is_rechecked_after_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launcher: Launcher
) -> None:
    document = make_document(tmp_path, "course.kmp", eligible_for=LORENZI)
    collision = document.with_name("course.kcl")
    original = document.read_bytes(), collision.read_bytes()
    calls = _dispatch_spies(monkeypatch, tmp_path, launcher)
    first = _outcome(lambda: editors.open_in(LORENZI, document, wine_prefix=tmp_path / "prefix"))
    assert isinstance(first, Launched)
    assert (document.read_bytes(), collision.read_bytes()) == original
    collision.unlink()
    calls.clear()
    _assert_refusal(_outcome(lambda: editors.open_in(LORENZI, document)), document)
    assert calls == [], "a previous successful dispatch must not cache eligibility"
    assert not collision.exists() and document.read_bytes() == original[0]


@pytest.mark.parametrize("tool", ["brawlcrate", "riistudio", "kmp_cloud", "blender"])
def test_other_editors_do_not_require_a_collision_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    document = make_document(tmp_path, f"course{editors.EDITOR_DOCUMENTS[tool][0]}")
    calls = _dispatch_spies(monkeypatch, tmp_path, "direct")
    result = _outcome(lambda: editors.open_in(tool, document))
    assert isinstance(result, Launched) and result.document == document.resolve()
    assert calls == [f"discover:{tool}", "native"]
    assert not document.with_name("course.kcl").exists() and document.read_bytes() == b"document"


def test_two_eligible_requests_make_two_real_native_dispatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = [
        make_document(tmp_path, "one.KMP", "first é 日本", eligible_for=LORENZI),
        make_document(tmp_path, "two.kmp", "second é 日本", eligible_for=LORENZI),
    ]
    before = [(p.read_bytes(), p.with_name("course.kcl").read_bytes()) for p in documents]
    exe = install_program(
        tmp_path / "fake editor é" / "lorenzi",
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "target = Path.cwd() / 'receipt.json'\n"
        "pending = target.with_suffix('.pending')\n"
        "pending.write_text(json.dumps({'argv': sys.argv[1:], 'cwd': str(Path.cwd()), "
        "'pid': os.getpid()}), encoding='utf-8')\n"
        "pending.replace(target)\n",
    )
    # Direct on either host: the real native runner and fake executable are unpatched.
    monkeypatch.setattr(editors, "current_os", lambda: "windows")

    def request(document: Path) -> Launched | Exception:
        return _outcome(lambda: editors.open_in(LORENZI, document, executable=exe))

    results = [request(document) for document in documents]
    assert all(isinstance(result, Launched) for result in results), results
    assert len({result.pid for result in results if isinstance(result, Launched)}) == 2
    receipts = [p.parent / "receipt.json" for p in documents]
    deadline = time.monotonic() + 8
    while not all(p.is_file() for p in receipts) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert all(p.is_file() for p in receipts), "both dispatched children must publish receipts"
    rows: list[dict[str, object]] = [json.loads(p.read_text(encoding="utf-8")) for p in receipts]
    assert len({row["pid"] for row in rows}) == 2, "each request must execute a distinct process"
    for document, result, row, original in zip(documents, results, rows, before, strict=True):
        assert isinstance(result, Launched)
        assert result.tool_id == LORENZI and result.document == document.resolve()
        # Windows launcher/venv shims may spawn descendants; their PIDs need not match.
        assert result.pid > 0 and result.warnings == ()
        assert row["argv"] == [str(document.resolve())]
        assert row["cwd"] == str(document.parent.resolve())
        assert (document.read_bytes(), document.with_name("course.kcl").read_bytes()) == original
