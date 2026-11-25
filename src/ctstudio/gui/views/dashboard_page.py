"""The dashboard's page in the main window: the cards scroll; the build bar (Build test,
Build release, Cancel, the build's progress and messages) stays pinned below them, so the
build buttons are always on screen (P5-T10b, owner decision D1)."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ctstudio.gui.views.dashboard import Dashboard


class DashboardPage(QWidget):
    def __init__(self, dashboard: Dashboard, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardPage")
        self.cards_area = QScrollArea(self)
        self.cards_area.setObjectName("dashboardScroll")
        self.cards_area.setWidgetResizable(True)
        self.cards_area.setWidget(dashboard)
        controls = dashboard.builds.controls
        cards = dashboard.layout()
        if cards is not None:
            cards.removeWidget(controls)  # a dashboard on its own keeps it at its end
        self.bar = QFrame(self)
        self.bar.setObjectName("buildBar")
        self.bar.setFrameShape(QFrame.Shape.StyledPanel)
        bar_layout = QVBoxLayout(self.bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.addWidget(controls)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.cards_area, 1)
        layout.addWidget(self.bar)
