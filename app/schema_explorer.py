from __future__ import annotations
"""
schema_explorer.py — Combined left-side panel with two tabs:
  "Nós"    — the existing NodePalette
  "Schema" — live tree view of tables / functions / procedures from the DB,
             all items draggable onto the FlowCanvas.
"""

import json

from PyQt5.QtCore import Qt, QMimeData, QByteArray, QThread, pyqtSignal, QObject
from PyQt5.QtGui  import QDrag, QFont, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTabBar,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QSizePolicy, QFrame,
)

from app.node_palette import NodePalette

_TITLE_FONT = QFont("Segoe UI", 9, QFont.Bold)
_LABEL_FONT = QFont("Segoe UI", 8)

# Mime type for schema items (functions/procedures with rich params)
MIME_SCHEMA = "application/x-flowsql-schema"
MIME_NODE   = "application/x-flowsql-node"


# ── Background loader ─────────────────────────────────────────────────────────

class _ColumnLoader(QObject):
    """Loads a single table's columns in a worker thread."""
    done = pyqtSignal(str, list)   # table_name, columns

    def __init__(self, inspector, table_name: str):
        super().__init__()
        self._inspector  = inspector
        self._table_name = table_name

    def run(self):
        cols = self._inspector.get_columns(self._table_name)
        self.done.emit(self._table_name, cols)


class _LoadColumnsThread(QThread):
    done = pyqtSignal(str, list)

    def __init__(self, inspector, table_name: str, parent=None):
        super().__init__(parent)
        self._inspector  = inspector
        self._table_name = table_name

    def run(self):
        cols = self._inspector.get_columns(self._table_name)
        self.done.emit(self._table_name, cols)


# ── Draggable tree ────────────────────────────────────────────────────────────

class _SchemaTree(QTreeWidget):
    """QTreeWidget whose items carry drag-mime data set as item data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAnimated(True)
        self.setIndentation(14)
        self.setFont(_LABEL_FONT)
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 8:
            super().mouseMoveEvent(event)
            return

        item = self.itemAt(self._drag_start_pos)
        if item is None:
            super().mouseMoveEvent(event)
            return

        mime_type    = item.data(0, Qt.UserRole + 1)
        mime_payload = item.data(0, Qt.UserRole + 2)
        if not mime_type or not mime_payload:
            super().mouseMoveEvent(event)
            return

        mime = QMimeData()
        mime.setData(mime_type, QByteArray(mime_payload if isinstance(mime_payload, bytes)
                                           else mime_payload.encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


# ── Schema tab content ────────────────────────────────────────────────────────

class _SchemaTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(2)

        # Connection info label
        self._conn_label = QLabel("— sem conexão —")
        self._conn_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._conn_label.setObjectName("palette_header")
        self._conn_label.setFixedHeight(22)
        self._conn_label.setContentsMargins(6, 0, 6, 0)
        lo.addWidget(self._conn_label)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrar...")
        self._search.setObjectName("palette_search")
        self._search.textChanged.connect(self._filter)
        lo.addWidget(self._search)

        # Tree
        self._tree = _SchemaTree(self)
        lo.addWidget(self._tree, 1)

        # Top-level groups
        self._tables_item = QTreeWidgetItem(self._tree, ["Tabelas"])
        self._tables_item.setFont(0, QFont("Segoe UI", 8, QFont.Bold))
        self._funcs_item  = QTreeWidgetItem(self._tree, ["Funções"])
        self._funcs_item.setFont(0, QFont("Segoe UI", 8, QFont.Bold))
        self._procs_item  = QTreeWidgetItem(self._tree, ["Procedures"])
        self._procs_item.setFont(0, QFont("Segoe UI", 8, QFont.Bold))

        self._tree.expandItem(self._tables_item)

        # Wire lazy column loading
        self._inspector = None
        self._col_threads: list[QThread] = []
        self._table_items: dict[str, QTreeWidgetItem] = {}
        self._tree.itemExpanded.connect(self._on_item_expanded)

    # ── Public ────────────────────────────────────────────────────────────────
    def set_connection(self, name: str, inspector) -> None:
        self._inspector = inspector
        self._conn_label.setText(name or "— sem conexão —")
        self._populate()

    def _populate(self):
        if self._inspector is None:
            return

        # Clear children (keep group items)
        self._tables_item.takeChildren()
        self._funcs_item.takeChildren()
        self._procs_item.takeChildren()
        self._table_items.clear()

        # Tables (names only; columns loaded lazily on expand)
        for tname in self._inspector.get_tables():
            item = QTreeWidgetItem(self._tables_item, [f"▦ {tname}"])
            item.setFont(0, _LABEL_FONT)
            # Drag: "table:{name}"
            item.setData(0, Qt.UserRole + 1, MIME_NODE)
            item.setData(0, Qt.UserRole + 2, f"table:{tname}")
            # Placeholder child so expand arrow appears
            item.addChild(QTreeWidgetItem(["⟳ carregando..."]))
            self._table_items[tname] = item

        # Functions
        try:
            funcs = self._inspector.get_functions()
        except Exception:
            funcs = []
        for fname in funcs:
            item = QTreeWidgetItem(self._funcs_item, [f"ƒ {fname}"])
            item.setFont(0, _LABEL_FONT)
            payload = json.dumps({"type": "function", "name": fname})
            item.setData(0, Qt.UserRole + 1, MIME_SCHEMA)
            item.setData(0, Qt.UserRole + 2, payload)

        # Procedures
        try:
            procs = self._inspector.get_procedures()
        except Exception:
            procs = []
        for pname in procs:
            item = QTreeWidgetItem(self._procs_item, [f"⚙ {pname}"])
            item.setFont(0, _LABEL_FONT)
            # Params loaded lazily when user drops; use simple JSON for now
            payload = json.dumps({"type": "procedure", "name": pname})
            item.setData(0, Qt.UserRole + 1, MIME_SCHEMA)
            item.setData(0, Qt.UserRole + 2, payload)

    # ── Lazy column loading ───────────────────────────────────────────────────
    def _on_item_expanded(self, item: QTreeWidgetItem):
        # Is this a table item?
        tname = None
        for name, ti in self._table_items.items():
            if ti is item:
                tname = name
                break
        if tname is None or self._inspector is None:
            return
        # Already loaded if first child is not a placeholder
        if item.childCount() > 0:
            first = item.child(0)
            if first and first.text(0) != "⟳ carregando...":
                return

        # Kick off thread
        thread = _LoadColumnsThread(self._inspector, tname, self)
        thread.done.connect(self._on_columns_loaded)
        thread.finished.connect(lambda: self._col_threads.remove(thread)
                                if thread in self._col_threads else None)
        self._col_threads.append(thread)
        thread.start()

    def _on_columns_loaded(self, table_name: str, cols: list):
        item = self._table_items.get(table_name)
        if item is None:
            return
        item.takeChildren()
        for col in cols:
            name = col.get("name", "")
            ctype = col.get("type", "")
            is_pk = col.get("pk", False)
            is_fk = col.get("fk", False)
            icon  = "🔑" if is_pk else ("→" if is_fk else "·")
            text  = f"{icon} {name}"
            child = QTreeWidgetItem(item, [text])
            child.setToolTip(0, f"{name}: {ctype}")
            child.setFont(0, QFont("Consolas", 8))
            # Column drag: "field:{table}.{col}"
            child.setData(0, Qt.UserRole + 1, MIME_NODE)
            child.setData(0, Qt.UserRole + 2, f"field:{table_name}.{name}")

    # ── Filter ────────────────────────────────────────────────────────────────
    def _filter(self, text: str):
        text = text.strip().lower()
        def _show_recursive(item: QTreeWidgetItem, parent_match: bool) -> bool:
            match = parent_match or (not text) or (text in item.text(0).lower())
            any_child_match = False
            for i in range(item.childCount()):
                child = item.child(i)
                child_match = _show_recursive(child, match)
                any_child_match = any_child_match or child_match
            visible = match or any_child_match
            item.setHidden(not visible)
            return visible

        for i in range(self._tree.topLevelItemCount()):
            _show_recursive(self._tree.topLevelItem(i), False)


# ── SchemaExplorer ────────────────────────────────────────────────────────────

class SchemaExplorer(QWidget):
    """Left-side 170px-wide panel combining node palette and schema tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schema_explorer")
        self.setFixedWidth(170)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tab bar ───────────────────────────────────────────────────────
        self._tab_bar = QTabBar()
        self._tab_bar.setObjectName("explorer_tab_bar")
        self._tab_bar.addTab("  Nós  ")
        self._tab_bar.addTab("  Schema  ")
        self._tab_bar.setExpanding(True)
        self._tab_bar.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tab_bar)

        # ── Stacked content ───────────────────────────────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # "Nós" page — NodePalette (width unrestricted; parent clips to 170)
        self._palette = NodePalette()
        self._palette.setFixedWidth(170)
        self._stack.addWidget(self._palette)

        # "Schema" page
        self._schema_tab = _SchemaTab()
        self._stack.addWidget(self._schema_tab)

        self._stack.setCurrentIndex(0)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_connection(self, name: str, inspector) -> None:
        """Populate the Schema tab; call after a connection is established."""
        self._schema_tab.set_connection(name, inspector)
        # Also populate the NodePalette's schema section
        self._palette.load_schema(inspector)

    # ── Tab switch ────────────────────────────────────────────────────────────
    def _on_tab_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)
