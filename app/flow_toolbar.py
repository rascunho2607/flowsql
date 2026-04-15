from __future__ import annotations
"""
flow_toolbar.py — Top toolbar for the Flow Builder canvas.
"""

from PyQt5.QtCore  import Qt, pyqtSignal
from PyQt5.QtGui   import QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QMessageBox, QFileDialog,
)


class FlowToolbar(QWidget):
    """Thin toolbar (~36px) placed above the FlowCanvas."""

    # ── Signals ───────────────────────────────────────────────────────────────
    execute_requested   = pyqtSignal()          # Run the current flow
    save_requested      = pyqtSignal()          # Save .flowsql.json
    load_requested      = pyqtSignal()          # Open .flowsql.json
    zoom_in_requested   = pyqtSignal()
    zoom_out_requested  = pyqtSignal()
    zoom_fit_requested  = pyqtSignal()
    zoom_reset_requested = pyqtSignal()
    copy_sql_requested  = pyqtSignal()          # Copy generated SQL
    open_editor_requested = pyqtSignal()        # Open SQL in editor tab
    clear_requested     = pyqtSignal()          # Clear canvas (with confirm)
    undo_requested      = pyqtSignal()
    redo_requested      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("flow_toolbar")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)

        def _btn(text: str, tooltip: str, signal: pyqtSignal = None,
                 obj: str = "toolbar_btn") -> QPushButton:
            b = QPushButton(text)
            b.setToolTip(tooltip)
            b.setObjectName(obj)
            b.setFont(QFont("Segoe UI", 9))
            if signal is not None:
                b.clicked.connect(lambda: signal.emit())
            return b

        # ── Left group: Flow actions ───────────────────────────────────────
        self._btn_exec = _btn("▶ Executar", "Executar o Flow (F5)",
                              self.execute_requested, "btn_execute")
        self._btn_save = _btn("💾 Salvar", "Salvar Flow (.flowsql.json)",
                              self.save_requested)
        self._btn_load = _btn("📂 Abrir",  "Abrir Flow (.flowsql.json)",
                              self.load_requested)

        layout.addWidget(self._btn_exec)
        layout.addWidget(self._btn_save)
        layout.addWidget(self._btn_load)

        layout.addWidget(_separator())

        # ── Undo / redo ───────────────────────────────────────────────────
        self._btn_undo = _btn("↩ Desfazer", "Desfazer (Ctrl+Z)", self.undo_requested)
        self._btn_redo = _btn("↪ Refazer",  "Refazer (Ctrl+Y)",  self.redo_requested)
        layout.addWidget(self._btn_undo)
        layout.addWidget(self._btn_redo)

        layout.addWidget(_separator())

        # ── Zoom group ────────────────────────────────────────────────────
        self._btn_zoom_in  = _btn("⊕",  "Zoom +",    self.zoom_in_requested)
        self._btn_zoom_out = _btn("⊖",  "Zoom −",    self.zoom_out_requested)
        self._btn_zoom_fit = _btn("⊞",  "Ajustar",   self.zoom_fit_requested)
        self._btn_zoom_100 = _btn("100%", "Zoom 100%", self.zoom_reset_requested)
        for b in (self._btn_zoom_in, self._btn_zoom_out,
                  self._btn_zoom_fit, self._btn_zoom_100):
            b.setFixedWidth(36)
            layout.addWidget(b)

        layout.addWidget(_separator())

        # ── SQL group ─────────────────────────────────────────────────────
        self._btn_copy_sql = _btn("Copiar SQL",      "Copiar SQL gerado",
                                  self.copy_sql_requested)
        self._btn_to_editor = _btn("↗ Abrir no Editor", "Abrir SQL no Editor",
                                   self.open_editor_requested)
        layout.addWidget(self._btn_copy_sql)
        layout.addWidget(self._btn_to_editor)

        layout.addWidget(_separator())

        # ── Clear ─────────────────────────────────────────────────────────
        btn_clear = _btn("🗑 Limpar", "Limpar canvas (confirmar)", obj="btn_danger")
        btn_clear.clicked.connect(self._confirm_clear)
        layout.addWidget(btn_clear)

        # ── Spacer + status label ──────────────────────────────────────────
        layout.addItem(
            __import__("PyQt5.QtWidgets", fromlist=["QSpacerItem"]).QSpacerItem(
                0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum
            )
        )

        self._status_label = QLabel("Zoom: 100% | Snap: On | 0 nós | —")
        self._status_label.setObjectName("flow_status_label")
        self._status_label.setFont(QFont("Segoe UI", 8))
        self._status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._status_label)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_undo_enabled(self, enabled: bool, text: str = "Desfazer"):
        self._btn_undo.setEnabled(enabled)
        self._btn_undo.setToolTip(text)

    def set_redo_enabled(self, enabled: bool, text: str = "Refazer"):
        self._btn_redo.setEnabled(enabled)
        self._btn_redo.setToolTip(text)

    def update_status(self, zoom: float, snap: bool, node_count: int,
                      conn_name: str = ""):
        parts = [
            f"Zoom: {int(zoom * 100)}%",
            f"Snap: {'On' if snap else 'Off'}",
            f"{node_count} nó{'s' if node_count != 1 else ''}",
        ]
        if conn_name:
            parts.append(conn_name)
        self._status_label.setText(" | ".join(parts))

    # ── Internal ──────────────────────────────────────────────────────────────
    def _confirm_clear(self):
        reply = QMessageBox.question(
            self,
            "Limpar Canvas",
            "Tem certeza que deseja remover todos os nodes e conexões?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.clear_requested.emit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _separator() -> QWidget:
    from PyQt5.QtWidgets import QFrame
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setObjectName("toolbar_separator")
    sep.setFixedHeight(20)
    return sep
