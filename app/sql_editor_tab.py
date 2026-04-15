from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QApplication, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor

from app.sql_editor_widget import SqlEditorWidget
from app.results_panel import ResultsPanel
from app.editor_toolbar import EditorToolbar
from core.query_executor import QueryExecutor


class SqlEditorTab(QWidget):
    """
    A single editor tab: EditorToolbar + SqlEditorWidget (top) + ResultsPanel (bottom).
    Manages its own QueryExecutor thread.
    """

    # Emitted when tab title should change (unsaved changes indicator)
    title_changed = pyqtSignal(str)
    # Emitted when user opens a history query → should open in new tab
    open_query_in_new_tab = pyqtSignal(str)

    def __init__(
        self,
        tab_name: str,
        engine=None,
        conn_name: str = "",
        db_name: str = "",
        initial_sql: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._tab_name = tab_name
        self._engine = engine
        self._conn_name = conn_name
        self._db_name = db_name
        self._executor: Optional[QueryExecutor] = None
        self._modified = False
        self._theme = "dark"

        self._build_ui()

        if initial_sql:
            self._editor.setPlainText(initial_sql)

        self._editor.document().contentsChanged.connect(self._on_content_changed)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Editor toolbar
        self._toolbar = EditorToolbar(self)
        self._toolbar.execute_requested.connect(self._run_query)
        self._toolbar.cancel_requested.connect(self._cancel_query)
        self._toolbar.format_requested.connect(self._format_sql)
        self._toolbar.explain_requested.connect(self._explain_query)
        self._toolbar.flow_builder_requested.connect(self._open_flow_builder)
        self._toolbar.comment_requested.connect(lambda: self._editor.comment_selection())
        self._toolbar.indent_requested.connect(lambda: self._editor._indent_selection())
        layout.addWidget(self._toolbar)

        # Splitter: editor top, results bottom
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setHandleWidth(4)

        # SQL editor
        self._editor = SqlEditorWidget()
        self._editor.execute_requested.connect(self._run_query)
        self._editor.cursorPositionChanged.connect(self._update_cursor_label)
        self._splitter.addWidget(self._editor)

        # Results panel
        self._results = ResultsPanel()
        self._results.open_history_query.connect(self.open_query_in_new_tab)
        self._splitter.addWidget(self._results)

        self._splitter.setSizes([600, 200])
        self._splitter.setCollapsible(0, False)
        layout.addWidget(self._splitter, 1)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def tab_name(self) -> str:
        return self._tab_name

    @property
    def is_modified(self) -> bool:
        return self._modified

    def set_engine(self, engine, conn_name: str = "", db_name: str = ""):
        self._engine = engine
        self._conn_name = conn_name
        self._db_name = db_name
        self._update_cursor_label()

    def set_theme(self, theme: str):
        self._theme = theme
        self._editor.set_theme(theme)

    def set_schema_words(self, words: list):
        self._editor.set_schema_words(words)

    def set_object_words(self, words: list):
        self._editor.set_object_words(words)

    def set_autocomplete_enabled(self, enabled: bool):
        self._editor.set_autocomplete_enabled(enabled)

    def set_syntax_check_enabled(self, enabled: bool):
        self._editor.set_syntax_check_enabled(enabled)

    def set_object_check_enabled(self, enabled: bool):
        self._editor.set_object_check_enabled(enabled)

    def set_autocorrect_syntax_enabled(self, enabled: bool):
        self._editor.set_autocorrect_syntax_enabled(enabled)

    def set_autocorrect_objects_enabled(self, enabled: bool):
        self._editor.set_autocorrect_objects_enabled(enabled)

    def get_sql(self) -> str:
        return self._editor.toPlainText()

    def set_sql(self, sql: str):
        self._editor.setPlainText(sql)

    # ── Query execution ───────────────────────────────────────────────────────

    def _run_query(self, sql: str = ""):
        if not sql:
            sql = self._editor._get_selected_or_all()
        if not sql.strip():
            return
        if self._engine is None:
            QMessageBox.warning(
                self, "Sem conexão",
                "Selecione uma conexão antes de executar uma consulta."
            )
            return

        # Already running
        if self._executor and self._executor.isRunning():
            return

        self._results.clear_messages()
        self._toolbar.set_executing(True)
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        self._executor = QueryExecutor(self._engine, sql, parent=self)
        self._executor.columns_ready.connect(self._on_columns_ready)
        self._executor.result_ready.connect(self._on_result_ready)
        self._executor.error_occurred.connect(self._on_error)
        self._executor.execution_time.connect(self._on_execution_time)
        self._executor.message.connect(self._on_message)
        self._executor.finished.connect(self._on_executor_finished)
        self._executor.start()

    def _cancel_query(self):
        if self._executor and self._executor.isRunning():
            self._executor.cancel()

    # ── Executor signals ──────────────────────────────────────────────────────

    def _on_columns_ready(self, columns: list):
        self._pending_columns = columns

    def _on_result_ready(self, rows: list):
        cols = getattr(self, "_pending_columns", [])
        elapsed = getattr(self, "_pending_elapsed", 0.0)
        if cols or rows:
            self._results.show_results(cols, rows, elapsed)

    def _on_error(self, msg: str):
        self._results.show_message(msg, is_error=True)
        self._add_history(False)

    def _on_execution_time(self, ms: float):
        self._pending_elapsed = ms

    def _on_message(self, msg: str):
        self._results.show_message(msg, is_error=False)

    def _on_executor_finished(self):
        self._toolbar.set_executing(False)
        QApplication.restoreOverrideCursor()

        elapsed = getattr(self, "_pending_elapsed", 0.0)
        rows = getattr(self, "_pending_columns", [])
        self._add_history(True)

    def _add_history(self, success: bool):
        entry = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "conn": self._conn_name,
            "db": self._db_name,
            "sql": self._editor._get_selected_or_all(),
            "duration_ms": getattr(self, "_pending_elapsed", 0.0),
            "success": success,
        }
        self._results.add_history_entry(entry)

    # ── SQL formatting ────────────────────────────────────────────────────────

    def _format_sql(self):
        """Basic SQL formatter — uppercase keywords, consistent indentation."""
        sql = self._editor.toPlainText()
        if not sql.strip():
            return
        try:
            formatted = self._basic_format(sql)
            self._editor.setPlainText(formatted)
        except Exception:
            pass

    @staticmethod
    def _basic_format(sql: str) -> str:
        from app.sql_editor_widget import SQL_KEYWORDS
        # Uppercase keywords
        def replace_kw(m):
            w = m.group(0)
            if w.upper() in SQL_KEYWORDS:
                return w.upper()
            return w
        sql = re.sub(r"\b\w+\b", replace_kw, sql)

        # Add newline before major clauses
        major = ["SELECT", "FROM", "WHERE", "JOIN", "INNER JOIN", "LEFT JOIN",
                 "RIGHT JOIN", "FULL JOIN", "ORDER BY", "GROUP BY", "HAVING",
                 "UNION", "INSERT", "UPDATE", "DELETE", "SET", "VALUES"]
        for kw in sorted(major, key=len, reverse=True):
            sql = re.sub(rf"\s+{re.escape(kw)}\s+", f"\n{kw}\n    ", sql, flags=re.IGNORECASE)

        lines = [line.rstrip() for line in sql.splitlines() if line.strip()]
        return "\n".join(lines)

    # ── Explain ───────────────────────────────────────────────────────────────

    def _explain_query(self):
        if self._engine is None:
            return
        sql = self._editor._get_selected_or_all().strip()
        if not sql:
            return
        db_type = self._engine.dialect.name
        if db_type == "postgresql":
            explain_sql = f"EXPLAIN ANALYZE {sql}"
        elif db_type in ("mysql",):
            explain_sql = f"EXPLAIN {sql}"
        elif db_type == "mssql":
            # MSSQL uses SET SHOWPLAN_TEXT ON — just show the query plan
            explain_sql = f"SET SHOWPLAN_ALL ON;\n{sql}\nSET SHOWPLAN_ALL OFF;"
        else:
            self._results.show_message("EXPLAIN não suportado para este banco de dados.")
            return
        self._run_query(explain_sql)

    def _open_flow_builder(self):
        QMessageBox.information(
            self, "Flow Builder",
            "Flow Builder será implementado na Fase 3.\n\n"
            f"SQL atual:\n{self._editor._get_selected_or_all()[:200]}..."
        )

    # ── Cursor label ──────────────────────────────────────────────────────────

    def _update_cursor_label(self):
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self._toolbar.update_cursor_pos(line, col, self._conn_name, self._db_name)

    # ── Modified state ────────────────────────────────────────────────────────

    def _on_content_changed(self):
        if not self._modified:
            self._modified = True
            self.title_changed.emit(f"*{self._tab_name}")

    def mark_saved(self):
        self._modified = False
        self.title_changed.emit(self._tab_name)
