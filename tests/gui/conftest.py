"""Initialize the headless Qt platform before pytest-qt creates QApplication."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
