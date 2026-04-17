from __future__ import annotations
"""
flow_tab_manager.py — Multi-tab manager for FlowBuilderTab instances.

Provides:
  • QTabBar at top with inline rename (double-click) and a × close button per tab
  • "+" button at the far right of the tab bar to add a new flow
  • QStackedWidget below holding one FlowBuilderTab per tab
  • Dirty tracking: appends " ●" to the tab label when the flow has unsaved changes
  • Minimum 1 tab: close button is disabled (hidden) when only one tab remains
"""

import json
import os
import re
import tempfile

from PyQt5.QtCore import Qt, pyqtSignal, QSize, QEvent, QObject, QTimer, QPoint
from PyQt5.QtGui  import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QTabBar,
    QPushButton, QLineEdit, QSizePolicy, QApplication,
    QMenu, QToolTip, QFileDialog,
)

from app.flow_builder_tab import FlowBuilderTab

_TAB_FONT      = QFont("Segoe UI", 9)
_CLOSE_W       = 20   # width of each × close button
_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")


class _TabBarFilter(QObject):
    """Event filter on QTabBar for context menus and rich tooltips."""

    def __init__(self, manager: "FlowTabManager") -> None:
        super().__init__(manager)
        self._mgr = manager

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is not self._mgr._tab_bar:
            return super().eventFilter(obj, event)

        t = event.type()

        if t == QEvent.ContextMenu:
            idx = self._mgr._tab_bar.tabAt(event.pos())
            if idx >= 0:
                self._mgr._show_tab_context_menu(idx, event.globalPos())
            return True

        if t == QEvent.ToolTip:
            idx = self._mgr._tab_bar.tabAt(event.pos())
            if idx >= 0:
                self._mgr._show_tab_tooltip(idx, event.globalPos())
                return True

        return super().eventFilter(obj, event)


class FlowTabManager(QWidget):
    """Hosts multiple FlowBuilderTab instances in a custom tab layout."""

    # Forwarded from the active tab
    open_sql_in_editor = pyqtSignal(str)
    execute_sql        = pyqtSignal(str)

    def __init__(
        self,
        engine=None,
        conn_name: str = "",
        db_name:   str = "",
        dialect:   str = "postgresql",
        parent=None,
    ):
        super().__init__(parent)
        self._engine    = engine
        self._conn_name = conn_name
        self._db_name   = db_name
        self._dialect   = dialect

        self._count = 0                        # monotonically increasing tab counter
        self._dirty: dict[int, bool]     = {}  # index → dirty flag
        self._base_names: dict[int, str] = {}  # index → clean name (without " ●")
        self._executing: dict[int, bool] = {}  # index → spinner active
        self._sql_cache: dict[int, str]  = {}  # index → cached generated SQL
        self._rename_edit: QLineEdit | None = None   # inline rename editor
        self._rename_idx:  int             = -1

        # Spinner state
        self._spinner_frame = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(200)
        self._spinner_timer.timeout.connect(self._tick_spinner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tab bar row ───────────────────────────────────────────────────
        tab_row = QWidget()
        tab_row.setObjectName("flow_tab_row")
        tab_row_lo = QHBoxLayout(tab_row)
        tab_row_lo.setContentsMargins(0, 0, 0, 0)
        tab_row_lo.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setObjectName("flow_tab_bar")
        self._tab_bar.setFont(_TAB_FONT)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setMovable(True)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabBarDoubleClicked.connect(self._start_rename)
        self._tab_bar.tabMoved.connect(self._on_tab_moved)
        tab_row_lo.addWidget(self._tab_bar, 1)

        # Install event filter for context menu and rich tooltips
        self._tab_filter = _TabBarFilter(self)
        self._tab_bar.installEventFilter(self._tab_filter)

        btn_add = QPushButton("+")
        btn_add.setObjectName("flow_tab_add_btn")
        btn_add.setFixedSize(28, 26)
        btn_add.setFont(QFont("Segoe UI", 11, QFont.Bold))
        btn_add.setToolTip("Novo Flow")
        btn_add.clicked.connect(lambda: self.add_flow())
        tab_row_lo.addWidget(btn_add)

        root.addWidget(tab_row)

        # ── Stacked pages ─────────────────────────────────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Create the first tab
        self.add_flow()

    # ── Public API ────────────────────────────────────────────────────────────

    def add_flow(self, name: str = "") -> FlowBuilderTab:
        """Create a new FlowBuilderTab, add a tab, return the widget."""
        self._count += 1
        tab_name = name or f"Flow {self._count}"
        tab = FlowBuilderTab(
            engine    = self._engine,
            conn_name = self._conn_name,
            db_name   = self._db_name,
            dialect   = self._dialect,
            tab_name  = tab_name,
            parent    = self,
        )
        # Wire signals upward
        tab.open_sql_in_editor.connect(self.open_sql_in_editor)
        tab.execute_sql.connect(self.execute_sql)

        # Track dirty state
        idx = self._tab_bar.count()
        tab.flow_changed.connect(lambda _idx=idx: self._mark_dirty(_idx))

        # Spinner: start when this tab's SQL is executed
        tab.execute_sql.connect(lambda _sql, _idx=idx: self._start_spinner(_idx))

        # SQL cache: invalidate when this tab changes
        tab.flow_changed.connect(lambda _idx=idx: self._sql_cache.pop(_idx, None))

        self._stack.addWidget(tab)

        new_idx = self._tab_bar.addTab(tab_name)
        self._base_names[new_idx] = tab_name
        self._dirty[new_idx]      = False

        # × close button
        close_btn = self._make_close_btn(new_idx)
        self._tab_bar.setTabButton(new_idx, QTabBar.RightSide, close_btn)

        self._tab_bar.setCurrentIndex(new_idx)
        self._update_close_buttons()
        return tab

    def current_flow(self) -> FlowBuilderTab | None:
        """Return the currently visible FlowBuilderTab."""
        w = self._stack.currentWidget()
        return w if isinstance(w, FlowBuilderTab) else None

    # ── Tab helpers ───────────────────────────────────────────────────────────

    def _make_close_btn(self, idx: int) -> QPushButton:
        btn = QPushButton("×")
        btn.setFixedSize(_CLOSE_W, _CLOSE_W)
        btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        btn.setObjectName("flow_tab_close_btn")
        btn.setFlat(True)
        btn.setToolTip("Fechar aba")
        btn.clicked.connect(lambda: self._close_tab_by_widget(btn))
        return btn

    def _close_tab_by_widget(self, btn: QPushButton):
        # Find which tab index this close button belongs to
        for idx in range(self._tab_bar.count()):
            w = self._tab_bar.tabButton(idx, QTabBar.RightSide)
            if w is btn:
                self._close_tab(idx)
                return

    def _close_tab(self, idx: int):
        if self._tab_bar.count() <= 1:
            return  # minimum 1 tab
        # Remove the page from QStackedWidget
        page = self._stack.widget(idx)
        self._stack.removeWidget(page)
        page.setParent(None)
        page.deleteLater()
        # Remove from tab bar
        self._tab_bar.removeTab(idx)
        # Rebuild internal dicts (indices shift after removal)
        self._rebuild_index_maps()
        self._update_close_buttons()

    def _rebuild_index_maps(self):
        """Re-index _dirty, _base_names, _executing and _sql_cache after a tab change."""
        new_dirty: dict[int, bool] = {}
        new_names: dict[int, str]  = {}
        new_exec:  dict[int, bool] = {}
        new_cache: dict[int, str]  = {}
        for i in range(self._tab_bar.count()):
            new_dirty[i] = self._dirty.get(i, False)
            new_names[i] = self._base_names.get(
                i, self._tab_bar.tabText(i).rstrip(" ●").strip()
            )
            new_exec[i]  = self._executing.get(i, False)
            new_cache[i] = self._sql_cache.get(i, "")
        self._dirty      = new_dirty
        self._base_names = new_names
        self._executing  = new_exec
        self._sql_cache  = new_cache

    def _update_close_buttons(self):
        """Show/hide close buttons — hidden when only 1 tab remains."""
        only_one = self._tab_bar.count() <= 1
        for idx in range(self._tab_bar.count()):
            btn = self._tab_bar.tabButton(idx, QTabBar.RightSide)
            if btn:
                btn.setVisible(not only_one)

    # ── Tab switching ─────────────────────────────────────────────────────────
    def _on_tab_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)

    def _on_tab_moved(self, from_idx: int, to_idx: int):
        """Keep QStackedWidget in sync when the user drags a tab to a new position."""
        widget = self._stack.widget(from_idx)
        self._stack.removeWidget(widget)
        self._stack.insertWidget(to_idx, widget)
        self._rebuild_index_maps()

    # ── Inline rename ─────────────────────────────────────────────────────────
    def _start_rename(self, idx: int):
        if idx < 0:
            return
        # Position a QLineEdit over the tab
        rect = self._tab_bar.tabRect(idx)
        edit = QLineEdit(self._base_names.get(idx, ""), self._tab_bar)
        edit.setGeometry(rect.adjusted(4, 2, -_CLOSE_W - 4, -2))
        edit.setFont(_TAB_FONT)
        edit.selectAll()
        edit.show()
        edit.setFocus()
        self._rename_edit = edit
        self._rename_idx  = idx
        edit.returnPressed.connect(self._commit_rename)
        edit.editingFinished.connect(self._commit_rename)

    def _commit_rename(self):
        if self._rename_edit is None or self._rename_idx < 0:
            return
        new_name = self._rename_edit.text().strip() or \
                   self._base_names.get(self._rename_idx, f"Flow {self._rename_idx + 1}")
        self._rename_edit.hide()
        self._rename_edit.setParent(None)
        self._rename_edit.deleteLater()
        self._rename_edit = None
        idx = self._rename_idx
        self._rename_idx  = -1

        self._base_names[idx] = new_name
        dirty = self._dirty.get(idx, False)
        display = new_name + (" ●" if dirty else "")
        self._tab_bar.setTabText(idx, display)

        # Update the underlying FlowBuilderTab's _tab_name
        page = self._stack.widget(idx)
        if isinstance(page, FlowBuilderTab):
            page._tab_name = new_name

    # ── Dirty tracking ────────────────────────────────────────────────────────
    def _mark_dirty(self, idx: int):
        if idx >= self._tab_bar.count():
            return
        if not self._dirty.get(idx, False):
            self._dirty[idx] = True
            base = self._base_names.get(idx, self._tab_bar.tabText(idx))
            self._tab_bar.setTabText(idx, base + " ●")

    def mark_clean(self, idx: int):
        """Call after an explicit save to clear the dirty indicator."""
        if idx >= self._tab_bar.count():
            return
        self._dirty[idx] = False
        base = self._base_names.get(idx, self._tab_bar.tabText(idx).replace(" ●", "").strip())
        self._tab_bar.setTabText(idx, base)

    # ── Execution spinner (Task 4.3) ──────────────────────────────────────────

    def _start_spinner(self, idx: int) -> None:
        """Begin animating the spinner on tab `idx`."""
        if idx >= self._tab_bar.count():
            return
        self._executing[idx] = True
        if not self._spinner_timer.isActive():
            self._spinner_timer.start()

    def stop_spinner(self, idx: int) -> None:
        """Stop the spinner on tab `idx` (call when execution finishes)."""
        if idx >= self._tab_bar.count():
            return
        self._executing[idx] = False
        # If no tabs are still executing, stop the timer
        if not any(self._executing.values()):
            self._spinner_timer.stop()
        # Restore the tab label
        base  = self._base_names.get(idx, f"Flow {idx + 1}")
        dirty = self._dirty.get(idx, False)
        self._tab_bar.setTabText(idx, base + (" ●" if dirty else ""))

    def _tick_spinner(self) -> None:
        self._spinner_frame = (self._spinner_frame + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_frame]
        for idx, active in self._executing.items():
            if active and idx < self._tab_bar.count():
                base  = self._base_names.get(idx, f"Flow {idx + 1}")
                dirty = self._dirty.get(idx, False)
                self._tab_bar.setTabText(idx, f"{frame} {base}" + (" ●" if dirty else ""))

    # ── Context menu on tabs (Task 4.2) ───────────────────────────────────────

    def _show_tab_context_menu(self, idx: int, global_pos: QPoint) -> None:
        menu = QMenu(self)
        count = self._tab_bar.count()

        act_close        = menu.addAction("Fechar")
        act_close.setEnabled(count > 1)
        act_close_others = menu.addAction("Fechar Outros")
        act_close_others.setEnabled(count > 1)
        act_close_right  = menu.addAction("Fechar Todos à Direita")
        act_close_right.setEnabled(idx < count - 1)
        act_rename       = menu.addAction("Renomear\tF2")
        act_dup          = menu.addAction("Duplicar Flow")
        menu.addSeparator()
        act_export = menu.addAction("Exportar Flow...")

        chosen = menu.exec_(global_pos)
        if chosen is None:
            return
        if chosen is act_close:
            self._close_tab(idx)
        elif chosen is act_close_others:
            self._close_others(idx)
        elif chosen is act_close_right:
            self._close_right(idx)
        elif chosen is act_rename:
            self._start_rename(idx)
        elif chosen is act_dup:
            self.duplicate_flow(idx)
        elif chosen is act_export:
            self._export_flow(idx)

    def _close_others(self, keep_idx: int) -> None:
        """Close all tabs except the one at keep_idx."""
        # Close tabs to the right first (indices stay stable)
        while self._tab_bar.count() > keep_idx + 1:
            self._close_tab(self._tab_bar.count() - 1)
        # Close tabs to the left (keep_idx slides down)
        while keep_idx > 0 and self._tab_bar.count() > 1:
            self._close_tab(0)
            keep_idx -= 1

    def _close_right(self, from_idx: int) -> None:
        """Close every tab to the right of from_idx."""
        while self._tab_bar.count() > from_idx + 1:
            self._close_tab(self._tab_bar.count() - 1)

    def _export_flow(self, idx: int) -> None:
        page = self._stack.widget(idx)
        if not isinstance(page, FlowBuilderTab):
            return
        canvas = page._canvas
        data = {
            "version": "1.0",
            "nodes":       [n.to_dict() for n in canvas._nodes],
            "connections": [c.to_dict() for c in canvas._connections],
        }
        base_name = self._base_names.get(idx, f"Flow {idx + 1}")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Flow", f"{base_name}.json", "JSON (*.json)"
        )
        if path:
            from pathlib import Path
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    # ── Rich tooltip on tabs (Task 4.4) ───────────────────────────────────────

    def _show_tab_tooltip(self, idx: int, global_pos: QPoint) -> None:
        page = self._stack.widget(idx)
        if not isinstance(page, FlowBuilderTab):
            return
        canvas    = page._canvas
        n_nodes   = len(canvas._nodes)
        n_conns   = len(canvas._connections)
        base_name = self._base_names.get(idx, f"Flow {idx + 1}")

        # Use cached SQL; regenerate when cache is empty
        sql = self._sql_cache.get(idx, "")
        if not sql and n_nodes > 0:
            try:
                sql = canvas.generate_sql(getattr(page, "_dialect", "postgresql"))
                self._sql_cache[idx] = sql
            except Exception:
                sql = ""

        if sql and not sql.startswith("--"):
            preview = sql[:120].replace("\n", " ").strip()
            if len(sql) > 120:
                preview += "…"
            valid_icon = "✅ Válido"
        else:
            preview    = ""
            valid_icon = "⚠️ Vazio" if n_nodes == 0 else "⚠️ Erro"

        tip_lines = [
            f"<b>Flow: {base_name}</b>",
            f"📊 {n_nodes} nós | 🔗 {n_conns} conexões",
            valid_icon,
        ]
        if preview:
            tip_lines.append(f"<code>{preview}</code>")

        QToolTip.showText(global_pos, "<br>".join(tip_lines), self._tab_bar)

    # ── Duplicate flow (Task 4.5) ──────────────────────────────────────────────

    def duplicate_flow(self, idx: int) -> "FlowBuilderTab | None":
        """Create a copy of the flow at `idx` and open it in a new tab."""
        page = self._stack.widget(idx)
        if not isinstance(page, FlowBuilderTab):
            return None

        canvas    = page._canvas
        base_name = self._base_names.get(idx, f"Flow {idx + 1}")

        # Serialise the original canvas in memory via a temp file
        data = {
            "version": "1.0",
            "nodes":       [n.to_dict() for n in canvas._nodes],
            "connections": [c.to_dict() for c in canvas._connections],
        }
        new_tab = self.add_flow(f"{base_name} (cópia)")

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            new_tab._canvas.load_from_json(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # Mark the copy as dirty (unsaved)
        new_idx = self._tab_bar.currentIndex()
        self._mark_dirty(new_idx)
        return new_tab
