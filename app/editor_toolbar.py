from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, QLabel, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon

ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"


def _icon(name: str) -> QIcon:
    p = ICONS_DIR / f"{name}.svg"
    return QIcon(str(p)) if p.exists() else QIcon()


class EditorToolbar(QWidget):
    """
    Thin toolbar (24 px) specific to the SQL editor area.
    Sits between the connection bar and the tab widget.
    """

    execute_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    format_requested = pyqtSignal()
    explain_requested = pyqtSignal()
    flow_builder_requested = pyqtSignal()
    comment_requested = pyqtSignal()
    indent_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("editor_toolbar")
        self.setFixedHeight(28)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Execute (highlighted)
        self._btn_execute = QToolButton()
        self._btn_execute.setObjectName("btn_new_connection")   # reuse accent style
        self._btn_execute.setText("▶  Executar (F5)")
        self._btn_execute.setIcon(_icon("play"))
        self._btn_execute.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._btn_execute.setIconSize(QSize(14, 14))
        self._btn_execute.clicked.connect(self.execute_requested)
        layout.addWidget(self._btn_execute)

        # Cancel
        self._btn_cancel = QToolButton()
        self._btn_cancel.setText("⏹  Cancelar")
        self._btn_cancel.setIcon(_icon("stop"))
        self._btn_cancel.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._btn_cancel.setIconSize(QSize(14, 14))
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self.cancel_requested)
        layout.addWidget(self._btn_cancel)

        layout.addWidget(self._separator())

        # Format SQL
        btn_fmt = QToolButton()
        btn_fmt.setText("Formatar SQL")
        btn_fmt.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_fmt.clicked.connect(self.format_requested)
        layout.addWidget(btn_fmt)

        # Explain
        btn_explain = QToolButton()
        btn_explain.setText("Explicar")
        btn_explain.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_explain.clicked.connect(self.explain_requested)
        layout.addWidget(btn_explain)

        # Flow Builder
        btn_flow = QToolButton()
        btn_flow.setText("→ Flow Builder")
        btn_flow.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_flow.clicked.connect(self.flow_builder_requested)
        layout.addWidget(btn_flow)

        layout.addWidget(self._separator())

        # Comment
        btn_comment = QToolButton()
        btn_comment.setText("Comentar")
        btn_comment.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_comment.setToolTip("Ctrl+K, C")
        btn_comment.clicked.connect(self.comment_requested)
        layout.addWidget(btn_comment)

        # Indent
        btn_indent = QToolButton()
        btn_indent.setText("⇥ Indentar")
        btn_indent.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_indent.setToolTip("Ctrl+]")
        btn_indent.clicked.connect(self.indent_requested)
        layout.addWidget(btn_indent)

        layout.addStretch()

        # Right: status label
        self._lbl_status = QLabel("Ln 1, Col 1")
        self._lbl_status.setObjectName("secondary_label")
        self._lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._lbl_status)

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Plain)
        sep.setFixedWidth(1)
        return sep

    # ── Public API ────────────────────────────────────────────────────────────

    def set_executing(self, executing: bool):
        """Toggle execute/cancel enabled states during query execution."""
        self._btn_execute.setEnabled(not executing)
        self._btn_cancel.setEnabled(executing)

    def update_cursor_pos(self, line: int, col: int, server: str = "", db: str = ""):
        parts = [f"Ln {line}, Col {col}"]
        if server:
            parts.append(server)
        if db:
            parts.append(db)
        self._lbl_status.setText("  |  ".join(parts))
