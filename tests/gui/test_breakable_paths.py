"""TD-019 / P5-T08a repair: a long path wraps in a word-wrapped banner, even one long folder
name with no punctuation, so it can never widen the Settings window past the screen.

Break chances are measured with Qt's own line breaker (``QTextBoundaryFinder``), not
assumed: Qt does not break after "/" before ".", nor at a no-break space.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from PySide6.QtCore import QTextBoundaryFinder

from ctstudio.gui.views.wrap_text import RUN, ZWSP, breakable

pytestmark = [pytest.mark.gui]


def pieces(text: str) -> list[str]:
    """The text between Qt's line-break chances, without zero-width spaces."""
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Line, text)
    cuts = [0]
    while (position := finder.toNextBoundary()) != -1:
        cuts.append(position)
    return [text[a:b].replace(ZWSP, "") for a, b in pairwise(cuts)]


def longest(text: str) -> int:
    return max(len(piece.rstrip(" ")) for piece in pieces(text))


@pytest.mark.parametrize(
    "path",
    [
        "C:\\Users\\" + "x" * 70 + "\\settings.json",
        "/home/user/" + "y" * 70 + "/settings.json",
        "/home/a_long_user_name_without_spaces_0123456789/.config/settings.json",
        "/home/u/" + "/.".join(["a" * 20, "b" * 20, "c" * 20, "d" * 20]) + "/x",
        "no\u00a0break\u00a0space\u00a0" * 6,
        "z" * (RUN * 3 + 5),
    ],
    ids=["windows", "linux", "dot-config", "slash-dots", "nbsp", "one-run"],
)
def test_every_piece_qt_can_wrap_at_is_short_and_the_text_is_kept(path: str) -> None:
    assert longest(path) > RUN + 1, "the case does not need a break"
    shown = breakable(path)
    assert shown.replace(ZWSP, "") == path, "the path's own characters changed"
    assert longest(shown) <= RUN + 1, f"Qt cannot wrap a piece of {longest(shown)} characters"


def test_a_backslash_is_always_followed_by_a_break() -> None:
    assert breakable("C:\\a\\b") == f"C:\\{ZWSP}a\\{ZWSP}b"


def test_short_words_and_sentences_are_left_alone() -> None:
    text = "CT Studio's settings file /home/u/.config/ct/settings.json cannot be used."
    assert breakable(text) == text, "ordinary text got zero-width spaces"


def test_a_run_of_exactly_run_characters_is_left_alone() -> None:
    assert breakable("w" * RUN) == "w" * RUN
    assert breakable("w" * (RUN + 1)) == "w" * RUN + ZWSP + "w"


def test_an_accent_stays_with_its_letter() -> None:
    accent = "\u0301"  # a combining acute accent, as in decomposed (NFD) Linux names
    text = "x" * (RUN - 1) + "e" + accent + "z" * 10
    shown = breakable(text)
    assert ZWSP + accent not in shown, "a break separates the accent from its letter"
    assert shown.replace(ZWSP, "") == text and longest(shown) <= RUN + 1


def test_a_run_is_short_enough_to_fit_beside_the_page_list() -> None:
    assert 8 <= RUN <= 32, "a run must stay far narrower than an 800 px screen"
