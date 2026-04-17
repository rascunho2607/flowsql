from __future__ import annotations
"""
flow_builder_tab.py — Full FlowBuilder tab: palette | canvas | properties.
"""

import os
import re
from PyQt5.QtCore    import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QApplication, QFileDialog, QMessageBox,
)

from app.flow_canvas       import FlowCanvas
from app.node_palette      import NodePalette
from app.schema_explorer   import SchemaExplorer
from app.node_properties   import NodePropertiesPanel
from app.flow_toolbar      import FlowToolbar
from core.sql_generator    import SQLGenerator

try:
    from sqlalchemy import text as _sa_text
except ImportError:
    _sa_text = lambda s: s   # type: ignore[assignment]


def _apply_quick_filter(sql: str, qf: str) -> str:
    """Wrap sql with quick-filter modifiers (TOP N / DISTINCT / DESC)."""
    sql = sql.strip().rstrip(";")
    qf_upper = qf.strip().upper()

    distinct = "DISTINCT" in qf_upper
    desc     = "DESC" in qf_upper

    # Extract TOP N
    import re as _re
    m = _re.search(r"TOP\s+(\d+)", qf_upper)
    top_n = int(m.group(1)) if m else None

    # Build SELECT prefix: SELECT [DISTINCT] [TOP N]
    prefix_parts = ["SELECT"]
    if distinct:
        prefix_parts.append("DISTINCT")
    if top_n is not None:
        prefix_parts.append(f"TOP {top_n}")
    new_prefix = " ".join(prefix_parts) + " "

    # Replace existing SELECT prefix (optionally with DISTINCT already there)
    sql = _re.sub(r"(?i)^SELECT\s+(?:DISTINCT\s+)?", new_prefix, sql, count=1)

    if desc:
        if "ORDER BY" not in sql.upper():
            sql += "\nORDER BY 1 DESC"
        else:
            if not sql.upper().rstrip().endswith("DESC"):
                sql += " DESC"

    return sql


_DEFAULT_FLOW_DIR = os.path.join(os.path.expanduser("~"), ".flowsql", "flows")
_GEN = SQLGenerator()


class FlowBuilderTab(QWidget):
    """One complete Flow Builder tab instance."""

    # Ask main_window to open a new SQL editor tab with this SQL
    open_sql_in_editor = pyqtSignal(str)
    # Ask main_window to run SQL via the current connection
    execute_sql        = pyqtSignal(str)
    # Emitted whenever the canvas changes (forwarded from canvas.flow_changed)
    flow_changed       = pyqtSignal()

    def __init__(self, engine=None, conn_name: str = "",
                 db_name: str = "", dialect: str = "postgresql",
                 tab_name: str = "flow",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("flow_builder_tab")

        self._engine    = engine
        self._conn_name = conn_name
        self._db_name   = db_name
        self._dialect   = dialect
        self._tab_name  = tab_name
        self._snap      = True

        os.makedirs(_DEFAULT_FLOW_DIR, exist_ok=True)

        # ── Toolbar ───────────────────────────────────────────────────────
        self._toolbar = FlowToolbar(self)

        # ── Palette / Schema Explorer (left) ─────────────────────────────
        self._explorer = SchemaExplorer(self)

        # ── Canvas (centre) ───────────────────────────────────────────────
        self._canvas = FlowCanvas(self)

        # ── Properties (right) ────────────────────────────────────────────
        self._props = NodePropertiesPanel(self)

        # ── Layout ────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._explorer)
        splitter.addWidget(self._canvas)
        splitter.addWidget(self._props)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([170, 800, 210])
        splitter.setHandleWidth(2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._toolbar)
        root.addWidget(splitter)

        # ── Wire toolbar signals ──────────────────────────────────────────
        self._toolbar.execute_requested.connect(self._execute_flow)
        self._toolbar.save_requested.connect(self._save_flow)
        self._toolbar.load_requested.connect(self._load_flow)
        self._toolbar.undo_requested.connect(self._canvas.undo_stack.undo)
        self._toolbar.redo_requested.connect(self._canvas.undo_stack.redo)
        self._toolbar.zoom_in_requested.connect(self._canvas.zoom_in)
        self._toolbar.zoom_out_requested.connect(self._canvas.zoom_out)
        self._toolbar.zoom_fit_requested.connect(self._canvas.zoom_fit)
        self._toolbar.zoom_reset_requested.connect(self._canvas.zoom_reset)
        self._toolbar.copy_sql_requested.connect(self._copy_sql)
        self._toolbar.open_editor_requested.connect(self._send_to_editor)
        self._toolbar.clear_requested.connect(self._canvas.clear_canvas)

        # ── Wire canvas signals ───────────────────────────────────────────
        self._canvas.flow_changed.connect(self._on_flow_changed)
        self._canvas.node_selected.connect(self._props.show_node)
        self._canvas.zoom_changed.connect(self._on_zoom_changed)
        self._canvas.node_execute_requested.connect(self._run_node)

        # Undo stack availability
        stack = self._canvas.undo_stack
        stack.canUndoChanged.connect(
            lambda can: self._toolbar.set_undo_enabled(can, stack.undoText())
        )
        stack.canRedoChanged.connect(
            lambda can: self._toolbar.set_redo_enabled(can, stack.redoText())
        )

        # ── Wire properties signals ───────────────────────────────────────
        self._props.execute_sql_requested.connect(self.execute_sql)
        self._props.open_in_editor.connect(self.open_sql_in_editor)

        # ── Initial status ────────────────────────────────────────────────
        self._toolbar.update_status(1.0, self._snap, 0, conn_name)
        self._toolbar.set_undo_enabled(False)
        self._toolbar.set_redo_enabled(False)

        # ── Wire schema inspector (if connection available) ────────────────
        if engine is not None:
            try:
                from core.schema_inspector import SchemaInspector
                self._inspector = SchemaInspector(engine)
                self._canvas.set_inspector(self._inspector)
                self._explorer.set_connection(conn_name, self._inspector)
            except Exception:
                pass

        # ── Autosave timer (30 s debounce) ────────────────────────────────
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._canvas.flow_changed.connect(self._autosave_timer.start)

        # ── Session restore ───────────────────────────────────────────────
        path = self._autosave_path()
        if os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "Recuperar sessão",
                f"Existe uma sessão salva automaticamente para '{self._tab_name}'.\n"
                "Deseja recuperar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                try:
                    self._canvas.load_from_json(path)
                except Exception:
                    pass

    # ── Theme ──────────────────────────────────────────────────────────────
    def set_theme(self, theme: str):
        self._canvas.set_theme(theme)
        self._props.set_theme(theme)

    def set_engine(self, engine, conn_name: str = "", db_name: str = ""):
        """Update execution engine/context for this flow tab."""
        self._engine = engine
        self._conn_name = conn_name
        self._db_name = db_name
        if engine is not None:
            try:
                from core.schema_inspector import SchemaInspector
                self._inspector = SchemaInspector(engine)
                self._canvas.set_inspector(self._inspector)
                self._explorer.set_connection(conn_name, self._inspector)
            except Exception:
                pass

    # ── Autosave ───────────────────────────────────────────────────────────
    def _autosave_path(self) -> str:
        directory = os.path.expanduser("~/.flowsql/autosave")
        os.makedirs(directory, exist_ok=True)
        safe_name = re.sub(r"[^\w\-]", "_", self._tab_name or "flow")
        return os.path.join(directory, f"{safe_name}.autosave.json")

    def _do_autosave(self):
        try:
            self._canvas.save_to_json(self._autosave_path())
        except Exception:
            pass  # silent — autosave must never crash the app

    # ── SQL ────────────────────────────────────────────────────────────────
    def _current_sql(self) -> str:
        try:
            return self._canvas.generate_sql_for_selection(self._dialect)
        except Exception as exc:
            return f"-- Erro ao gerar SQL: {exc}"

    def _copy_sql(self):
        sql = self._current_sql()
        if sql:
            QApplication.clipboard().setText(sql)

    def _send_to_editor(self):
        sql = self._current_sql()
        if sql:
            self.open_sql_in_editor.emit(sql)

    # ── Execution ─────────────────────────────────────────────────────────
    def _execute_flow(self):
        sql = self._current_sql()
        if sql and not sql.startswith("--"):
            self.execute_sql.emit(sql)

    def _run_node(self, node):
        """Execute the SQL for a single node and display the result inline."""
        if self._engine is None:
            return
        try:
            # Generate SQL only from the sub-graph feeding this node so that
            # unconnected parts of the canvas do not pollute the result.
            sql = self._canvas.generate_sql_for_node(node, self._dialect)
            if not sql or sql.startswith("--"):
                if hasattr(node, "set_result"):
                    node.set_result(
                        ["Erro"],
                        [{"Erro": "Não foi possível gerar SQL. Verifique as conexões do fluxo."}],
                    )
                return
            if "FROM " not in sql.upper():
                if hasattr(node, "set_result"):
                    node.set_result(
                        ["Erro"],
                        [{"Erro": "Nenhuma tabela conectada ao fluxo. Adicione e conecte um TableNode ao SELECT."}],
                    )
                return
        except Exception as exc:
            if hasattr(node, "set_result"):
                node.set_result(["Erro"], [{"Erro": str(exc)}])
            return

        # Apply quick_filter if the node knows about it
        qf = getattr(node, "_data", {}).get("quick_filter", "nenhum")
        if qf and qf != "nenhum":
            sql = _apply_quick_filter(sql, qf)

        from PyQt5.QtCore import QThread, QObject, pyqtSlot as _pyqtSlot

        # ── QObject receiver that lives in the main thread ───────────────
        # Connecting a lambda to a thread signal uses DirectConnection (runs
        # in the worker thread).  Using a QObject with thread affinity in the
        # main thread forces PyQt5 to use QueuedConnection automatically, so
        # set_result / update() are always called from the GUI thread.
        class _Receiver(QObject):
            def __init__(self, target_node, parent=None):
                super().__init__(parent)
                self._node = target_node

            @_pyqtSlot(list, list)
            def on_done(self, cols, rows):
                self._node.set_result(cols, rows)

            @_pyqtSlot(str)
            def on_error(self, msg):
                self._node.set_result(["Erro"], [{"Erro": msg}])

        class _RunThread(QThread):
            done  = pyqtSignal(list, list)
            error = pyqtSignal(str)

            def __init__(self, engine, sql, parent=None):
                super().__init__(parent)
                self._engine = engine
                self._sql    = sql

            def run(self):
                try:
                    with self._engine.connect() as conn:
                        result = conn.execute(_sa_text(self._sql))
                        cols = list(result.keys())
                        rows = [dict(zip(cols, row)) for row in result.fetchall()]
                    self.done.emit(cols, rows)
                except Exception as exc:
                    self.error.emit(str(exc))

        recv   = _Receiver(node, self)   # parent=self → main thread
        thread = _RunThread(self._engine, sql, self)
        thread.done.connect(recv.on_done)
        thread.error.connect(recv.on_error)
        # Keep a reference so the GC does not collect the thread before it
        # finishes (which would silently swallow the done/error signal).
        if not hasattr(self, "_active_threads"):
            self._active_threads = []
        self._active_threads.append(thread)
        thread.start()
        thread.finished.connect(recv.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda: self._active_threads.remove(thread)
            if thread in self._active_threads else None
        )

    # ── Save / Load ───────────────────────────────────────────────────────
    def _save_flow(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Flow",
            _DEFAULT_FLOW_DIR,
            "FlowSQL (*.flowsql.json);;Todos (*)",
        )
        if not path:
            return
        if not path.endswith(".flowsql.json"):
            path += ".flowsql.json"
        try:
            self._canvas.save_to_json(path)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))

    def _load_flow(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir Flow",
            _DEFAULT_FLOW_DIR,
            "FlowSQL (*.flowsql.json);;Todos (*)",
        )
        if not path:
            return
        try:
            self._canvas.load_from_json(path)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao abrir", str(exc))

    # ── Canvas signal handlers ────────────────────────────────────────────
    @pyqtSlot()
    def _on_flow_changed(self):
        self.flow_changed.emit()
        sql = self._current_sql()
        self._props.set_sql(sql)
        node_count = len([
            item for item in self._canvas.scene().items()
            if hasattr(item, "node_type")
        ])
        self._toolbar.update_status(
            self._canvas.current_zoom(),
            self._snap,
            node_count,
            self._conn_name,
        )

    @pyqtSlot(float)
    def _on_zoom_changed(self, zoom: float):
        node_count = len([
            item for item in self._canvas.scene().items()
            if hasattr(item, "node_type")
        ])
        self._toolbar.update_status(zoom, self._snap, node_count, self._conn_name)
