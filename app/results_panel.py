from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableView,
    QPlainTextEdit, QLabel, QPushButton, QHeaderView, QAbstractItemView,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QSortFilterProxyModel, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QColor, QFont, QBrush


HISTORY_FILE = Path.home() / ".flowsql" / "history.json"
MAX_HISTORY = 500


class ResultsPanel(QWidget):
    """
    Bottom panel with tabs: Results | Messages | Execution Plan | History.
    Attached below the SQL editor via a QSplitter.
    """

    # Signal: user double-clicks a history item → open in new editor
    open_history_query = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._col_names: List[str] = []
        self._rows: List[dict] = []
        self._history: List[dict] = []

        self._build_ui()
        self._load_history()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("results_tabs")
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_results_tab(), "Resultados")
        self._tabs.addTab(self._build_messages_tab(), "Mensagens")
        self._tabs.addTab(self._build_plan_tab(), "Plano de Execução")
        self._tabs.addTab(self._build_history_tab(), "Histórico")

    # ── Results tab ───────────────────────────────────────────────────────────

    def _build_results_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Table view
        self._model = QStandardItemModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setObjectName("results_table")
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.verticalHeader().setVisible(True)

        font = QFont("Consolas", 12)
        self._table.setFont(font)
        self._table.horizontalHeader().setFont(QFont("Segoe UI", 11))

        layout.addWidget(self._table, 1)

        # Footer bar
        footer = QWidget()
        footer.setObjectName("results_footer")
        footer.setFixedHeight(26)
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(8, 2, 8, 2)
        f_layout.setSpacing(12)

        self._lbl_row_count = QLabel("0 linhas")
        self._lbl_row_count.setObjectName("secondary_label")
        self._lbl_elapsed = QLabel("")
        self._lbl_elapsed.setObjectName("secondary_label")

        f_layout.addWidget(self._lbl_row_count)
        f_layout.addWidget(self._lbl_elapsed)
        f_layout.addStretch()

        btn_csv = QPushButton("Exportar CSV")
        btn_csv.setFixedHeight(20)
        btn_csv.clicked.connect(self._export_csv)
        btn_excel = QPushButton("Exportar Excel")
        btn_excel.setFixedHeight(20)
        btn_excel.clicked.connect(self._export_excel)

        f_layout.addWidget(btn_csv)
        f_layout.addWidget(btn_excel)

        layout.addWidget(footer)
        return container

    # ── Messages tab ──────────────────────────────────────────────────────────

    def _build_messages_tab(self) -> QWidget:
        self._messages = QPlainTextEdit()
        self._messages.setReadOnly(True)
        self._messages.setObjectName("messages_editor")
        font = QFont("Consolas", 12)
        self._messages.setFont(font)
        self._messages.setPlaceholderText("Mensagens de execução aparecerão aqui...")
        return self._messages

    # ── Plan tab ──────────────────────────────────────────────────────────────

    def _build_plan_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        self._plan_tree = QTreeWidget()
        self._plan_tree.setObjectName("plan_tree")
        self._plan_tree.setHeaderLabels(["Operação", "Custo", "Linhas", "Largura"])
        self._plan_tree.setColumnWidth(0, 300)
        self._plan_tree.setColumnWidth(1, 100)
        self._plan_tree.setColumnWidth(2, 100)
        self._plan_tree.setColumnWidth(3, 100)

        placeholder_lbl = QLabel("Execute uma consulta com EXPLAIN para ver o plano.")
        placeholder_lbl.setAlignment(Qt.AlignCenter)
        placeholder_lbl.setObjectName("secondary_label")

        layout.addWidget(self._plan_tree, 1)
        layout.addWidget(placeholder_lbl)
        return container

    # ── History tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setFixedHeight(28)
        b_layout = QHBoxLayout(bar)
        b_layout.setContentsMargins(6, 2, 6, 2)
        b_layout.addStretch()
        btn_clear = QPushButton("Limpar Histórico")
        btn_clear.setFixedHeight(22)
        btn_clear.clicked.connect(self._clear_history)
        b_layout.addWidget(btn_clear)
        layout.addWidget(bar)

        self._history_list = QListWidget()
        self._history_list.setObjectName("history_list")
        self._history_list.setFont(QFont("Consolas", 11))
        self._history_list.itemDoubleClicked.connect(self._on_history_double_click)
        layout.addWidget(self._history_list, 1)
        return container

    # ── Public API ────────────────────────────────────────────────────────────

    def show_results(self, columns: List[str], rows: List[dict],
                     elapsed_ms: float):
        """Populate the results grid."""
        self._col_names = columns
        self._rows = rows

        self._model.clear()
        self._model.setHorizontalHeaderLabels(columns)

        mono = QFont("Consolas", 12)
        null_brush = QBrush(QColor("#888888"))

        for row in rows:
            items = []
            for col in columns:
                val = row.get(col)
                if val is None:
                    item = QStandardItem("NULL")
                    item.setForeground(null_brush)
                    item.setFont(QFont("Consolas", 12, italic=True))
                else:
                    item = QStandardItem(str(val))
                    item.setFont(mono)
                    # Right-align numbers
                    try:
                        float(str(val))
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    except (ValueError, TypeError):
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                items.append(item)
            self._model.appendRow(items)

        self._table.resizeColumnsToContents()
        count = len(rows)
        self._lbl_row_count.setText(f"{count} linha{'s' if count != 1 else ''}")
        self._lbl_elapsed.setText(f"{elapsed_ms:.0f} ms")
        self._tabs.setCurrentIndex(0)

    def show_message(self, msg: str, is_error: bool = False):
        """Append a message to the Messages tab."""
        ts = datetime.now().strftime("%H:%M:%S")
        color = "#f14c4c" if is_error else "#4ec9b0"
        self._messages.appendHtml(
            f'<span style="color:{color}">[{ts}] {msg}</span><br>'
        )
        if is_error:
            self._tabs.setCurrentIndex(1)

    def show_plan(self, plan_rows: List[dict]):
        """Populate the execution plan tree."""
        self._plan_tree.clear()
        for row in plan_rows:
            item = QTreeWidgetItem([
                str(row.get("operation", "")),
                str(row.get("cost", "")),
                str(row.get("rows", "")),
                str(row.get("width", "")),
            ])
            self._plan_tree.addTopLevelItem(item)
        self._tabs.setCurrentIndex(2)

    def add_history_entry(self, entry: dict):
        """
        entry = {
            ts: str, conn: str, db: str, sql: str,
            duration_ms: float, success: bool
        }
        """
        self._history.insert(0, entry)
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[:MAX_HISTORY]
        self._refresh_history_list()
        self._save_history()

    def clear_messages(self):
        self._messages.clear()

    # ── History helpers ───────────────────────────────────────────────────────

    def _refresh_history_list(self):
        self._history_list.clear()
        for entry in self._history:
            ts = entry.get("ts", "")
            conn = entry.get("conn", "")
            db = entry.get("db", "")
            sql_preview = entry.get("sql", "")[:60].replace("\n", " ")
            dur = entry.get("duration_ms", 0)
            success = entry.get("success", True)
            icon = "✓" if success else "✗"
            label = f"{icon} [{ts}] {conn}/{db}  {dur:.0f}ms  |  {sql_preview}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry.get("sql", ""))
            if not success:
                item.setForeground(QColor("#f14c4c"))
            self._history_list.addItem(item)

    def _on_history_double_click(self, item: QListWidgetItem):
        sql = item.data(Qt.UserRole)
        if sql:
            self.open_history_query.emit(sql)

    def _clear_history(self):
        self._history.clear()
        self._history_list.clear()
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
            self._refresh_history_list()
        except Exception:
            pass

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._col_names:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar CSV", "resultado.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=self._col_names)
                writer.writeheader()
                writer.writerows(self._rows)
            self.show_message(f"Exportado para {path}")
        except Exception as exc:
            self.show_message(f"Erro ao exportar: {exc}", is_error=True)

    def _export_excel(self):
        if not self._col_names:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Excel", "resultado.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(self._col_names)
            for row in self._rows:
                ws.append([row.get(c) for c in self._col_names])
            wb.save(path)
            self.show_message(f"Exportado para {path}")
        except ImportError:
            # Fallback: save as CSV
            self._export_csv()
            self.show_message("openpyxl não instalado — salvo como CSV.", is_error=False)
        except Exception as exc:
            self.show_message(f"Erro ao exportar: {exc}", is_error=True)
