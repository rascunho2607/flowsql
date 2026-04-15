from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont


HISTORY_FILE = Path.home() / ".flowsql" / "history.json"
MAX_HISTORY = 500


class QueryHistoryDock(QDockWidget):
    """
    Dockable panel (right side) listing all queries executed this session.
    Can be toggled via View > History.
    """

    open_query = pyqtSignal(str)   # emit SQL when double-clicked

    def __init__(self, parent=None):
        super().__init__("Histórico de Consultas", parent)
        self.setObjectName("history_dock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable |
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable
        )

        self._history: list[dict] = []
        self._build_ui()
        self._load_history()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar row
        bar = QWidget()
        b_layout = QHBoxLayout(bar)
        b_layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Sessão atual — duplo clique para abrir")
        lbl.setObjectName("secondary_label")
        lbl.setFont(QFont("Segoe UI", 10))
        btn_clear = QPushButton("Limpar")
        btn_clear.setFixedHeight(22)
        btn_clear.clicked.connect(self._clear)
        b_layout.addWidget(lbl, 1)
        b_layout.addWidget(btn_clear)
        layout.addWidget(bar)

        # List
        self._list = QListWidget()
        self._list.setFont(QFont("Consolas", 10))
        self._list.setWordWrap(True)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list, 1)

        self.setWidget(container)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_entry(self, entry: dict):
        """
        entry = {ts, conn, db, sql, duration_ms, success}
        """
        self._history.insert(0, entry)
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[:MAX_HISTORY]
        self._rebuild_list()
        self._save_history()

    # ── Private ───────────────────────────────────────────────────────────────

    def _rebuild_list(self):
        self._list.clear()
        for entry in self._history:
            ts = entry.get("ts", "")
            conn = entry.get("conn", "")
            db = entry.get("db", "")
            dur = entry.get("duration_ms", 0)
            sql_preview = entry.get("sql", "")[:60].replace("\n", " ")
            success = entry.get("success", True)
            icon = "✓" if success else "✗"
            text = f"{icon} [{ts}] {conn}/{db}  {dur:.0f}ms\n{sql_preview}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry.get("sql", ""))
            if not success:
                item.setForeground(QColor("#f14c4c"))
            self._list.addItem(item)

    def _on_double_click(self, item: QListWidgetItem):
        sql = item.data(Qt.UserRole)
        if sql:
            self.open_query.emit(sql)

    def _clear(self):
        self._history.clear()
        self._list.clear()
        self._save_history()

    def _save_history(self):
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_history(self):
        if not HISTORY_FILE.exists():
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                self._history = json.load(f)
            self._rebuild_list()
        except Exception:
            pass
