"""P5-GATE delta reviews: the end-to-end stall check excuses only the screenshot's grab."""

from __future__ import annotations

from e2e_helpers import in_product

TEST = "C:/dev/ct-studio/tests/gui/test_end_to_end.py"
FAKES = "C:/dev/ct-studio/tests/gui/wizard_fakes.py"
WAITS = "C:/dev/ct-studio/tests/gui/waits.py"
DASHBOARD = "C:/dev/ct-studio/src/ctstudio/gui/views/dashboard.py"
PYTEST = "C:/venv/Lib/site-packages/_pytest/python.py"
QTBOT = "C:/venv/Lib/site-packages/pytestqt/qtbot.py"
WAIT_SIGNAL = "C:/venv/Lib/site-packages/pytestqt/wait_signal.py"


def stall(*frames: tuple[str, str, str]) -> str:
    text = "".join(
        f'  File "{path}", line 1, in {func}\n    {source}\n' for path, func, source in frames
    )
    return f"The UI thread has not responded for over 100 ms. It was here:\n{text}"


RUN = (PYTEST, "pytest_pyfunc_call", "result = testfunction(**testargs)")
SHOT_CALL = (TEST, "test_flow", 'shot(window, "p5-t09-4-built.png")')


def test_the_screenshot_grab_is_excused() -> None:
    grab = (FAKES, "shot", 'assert widget.grab().save(str(SCREENS / name), "PNG")')
    assert not in_product(stall(RUN, SHOT_CALL, grab))


def test_product_painting_inside_the_grab_counts() -> None:
    """The grab paints widgets; a slow product paint or size hint is the product's stall."""
    grab = (FAKES, "shot", 'assert widget.grab().save(str(SCREENS / name), "PNG")')
    paint = ("C:/dev/ct-studio/src/ctstudio/gui/views/path_label.py", "paintEvent", "x()")
    assert in_product(stall(RUN, SHOT_CALL, grab, paint))


def test_the_events_processed_before_the_grab_count() -> None:
    events = (FAKES, "shot", "QApplication.processEvents()  # let the layout follow")
    assert in_product(stall(RUN, SHOT_CALL, events))


def test_a_stall_while_the_test_waits_counts() -> None:
    """A worker holding the GIL or Qt painting product widgets leaves only the wait's frames."""
    waiting = (
        RUN,
        (TEST, "test_flow", "assert settled(qtbot, lambda: idle(window, services))"),
        (WAITS, "settled", "qtbot.wait(10)"),
        (QTBOT, "wait", "blocker.wait()"),
        (WAIT_SIGNAL, "wait", "self._loop.exec()"),
    )
    assert in_product(stall(*waiting))


def test_a_product_slot_counts_even_when_it_calls_a_test_fake() -> None:
    slot = (DASHBOARD, "sync", "self._refresh()")
    fake = (FAKES, "choose_folder", "return self.folder")
    assert in_product(stall(RUN, (QTBOT, "wait", "loop.exec()"), slot))
    assert in_product(stall(RUN, (QTBOT, "wait", "loop.exec()"), slot, fake))


def test_an_unknown_stack_counts() -> None:
    assert in_product("The UI thread has not responded for over 100 ms. It was here:\n(unknown)\n")
