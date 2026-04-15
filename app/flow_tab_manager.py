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

import re

from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui  import QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QTabBar,
    QPushButton, QLineEdit, QSizePolicy, QApplication,
)

from app.flow_builder_tab import FlowBuilderTab

_TAB_FONT  = QFont("Segoe UI", 9)
_CLOSE_W   = 20   # width of each × close button


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
        self._dirty: dict[int, bool] = {}      # index → dirty flag
        self._base_names: dict[int, str] = {}  # index → clean name (without " ●")
        self._rename_edit: QLineEdit | None = None   # inline rename editor
        self._rename_idx:  int             = -1

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
        self._tab_bar.setMovable(False)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabBarDoubleClicked.connect(self._start_rename)
        tab_row_lo.addWidget(self._tab_bar, 1)

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
        """Re-index _dirty and _base_names after a tab removal."""
        new_dirty: dict[int, bool] = {}
        new_names: dict[int, str]  = {}
        for i in range(self._tab_bar.count()):
            new_dirty[i] = self._dirty.get(i, False)
            new_names[i] = self._base_names.get(i, self._tab_bar.tabText(i).rstrip(" ●").strip())
        self._dirty      = new_dirty
        self._base_names = new_names

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
