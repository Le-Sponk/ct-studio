"""Let long paths wrap in word-wrapped banner labels (P5-T07f1, P5-T08a repair, TD-019).

A word-wrapped QLabel breaks only where Qt's line breaker allows: at spaces, and after "/"
unless a "." follows. A path with none of those, such as one long folder name or a Windows
path (Qt cannot break after a backslash), would make the label, and so the window, wider
than the screen. ``breakable`` adds zero-width spaces
(U+200B): after each backslash, and inside every run of more than ``RUN`` characters Qt
cannot break, never between a letter and a following combining accent. Use it only for text
that is shown, never for a path the user can select and copy.
"""

from __future__ import annotations

import re

RUN = 24  # characters; one such run at the enlarged font is far narrower than the screen
ZWSP = "\u200b"
# A character Qt does not break after: anything but a breaking space, "/" or a zero-width
# space, or a "/" followed by "." (Qt keeps "/." together).
_UNBROKEN = r"(?:[^ \t\n\r/\u200b]|/(?=\.))"
_COMBINING = "\u0300-\u036f\u1ab0-\u1aff\u20d0-\u20ff\ufe20-\ufe2f"
_LONG_RUN = re.compile(rf"{_UNBROKEN}{{{RUN}}}(?={_UNBROKEN})(?![{_COMBINING}])")


def breakable(text: str) -> str:
    """``text`` with a break chance after each backslash and inside every run longer than
    ``RUN`` characters; removing the zero-width spaces gives ``text`` back."""
    text = text.replace("\\", "\\" + ZWSP)
    return _LONG_RUN.sub(lambda run: run.group(0) + ZWSP, text)
