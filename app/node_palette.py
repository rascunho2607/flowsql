from __future__ import annotations
"""
node_palette.py — Left-side panel listing all draggable node types.
"""

import json

from PyQt5.QtCore import Qt, QMimeData, QByteArray, QPoint
from PyQt5.QtGui import QDrag, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QScrollArea, QFrame, QSizePolicy,
)

# ── Node catalogue  ──────────────────────────────────────────────────────────
_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Dados", [
        ("table",     "▦  Table"),
        ("result",    "✓  Result"),
    ]),
    ("Relacional", [
        ("join",      "⋈  JOIN"),
    ]),
    ("Seleção", [
        ("select",    "◻  SELECT"),
        ("where",     "∿  WHERE"),
        ("group_by",  "≡  GROUP BY"),
        ("having",    "▲  HAVING"),
        ("order_by",  "↕  ORDER BY"),
        ("limit",     "#  LIMIT"),
    ]),
    ("Funções", [
        ("aggregate", "∑  Aggregate"),
        ("case",      "?  CASE / IF"),
    ]),
    ("Combinar", [
        ("union",     "⊔  UNION"),
    ]),
    ("Calcular", [
        ("function",  "ƒ  Função"),
    ]),
    ("Escrita", [
        ("update",    "✎  UPDATE"),
        ("delete",    "✕  DELETE"),
    ]),
    ("Organização", [
        ("note",      "✎  Nota / Sticky"),
        ("group",     "⬡  Grupo"),
    ]),
]

_TITLE_FONT = QFont("Segoe UI", 9, QFont.Bold)
_GROUP_FONT = QFont("Segoe UI", 8, QFont.Bold)
_ITEM_FONT  = QFont("Consolas", 9)


class _PaletteItem(QLabel):
    """Single draggable node entry."""

    def __init__(self, node_type: str, display: str, parent=None,
                 mime_override: bytes | None = None):
        super().__init__(display, parent)
        self._node_type    = node_type
        self._mime_payload = mime_override or node_type.encode()
        self.setFont(_ITEM_FONT)
        self.setObjectName("palette_item")
        self.setCursor(Qt.OpenHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(26)
        self.setContentsMargins(8, 0, 8, 0)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self._drag_start).manhattanLength() < 6:
            return
        mime = QMimeData()
        mime.setData(
            "application/x-flowsql-node",
            QByteArray(self._mime_payload),
        )
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


class NodePalette(QWidget):
    """Left-side panel with searchable list of node types."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("node_palette")
        self.setFixedWidth(160)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header = QLabel("  Nós")
        header.setObjectName("palette_header")
        header.setFixedHeight(28)
        header.setFont(_TITLE_FONT)
        root.addWidget(header)

        # ── Search ────────────────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar nó...")
        self._search.setObjectName("palette_search")
        self._search.setContentsMargins(4, 2, 4, 2)
        self._search.textChanged.connect(self._filter)
        root.addWidget(self._search)

        # ── Scrollable list ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(0)

        self._items: list[tuple[str, _PaletteItem, QLabel]] = []  # (type, item, group_lbl)
        self._group_labels: list[QLabel] = []

        for group_name, entries in _GROUPS:
            grp_lbl = QLabel(f"  {group_name}")
            grp_lbl.setFont(_GROUP_FONT)
            grp_lbl.setObjectName("palette_group")
            grp_lbl.setFixedHeight(22)
            self._list_layout.addWidget(grp_lbl)
            self._group_labels.append(grp_lbl)

            for node_type, display in entries:
                item = _PaletteItem(node_type, display)
                self._list_layout.addWidget(item)
                self._items.append((node_type, item, grp_lbl))

        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        # Schema section (populated at runtime via load_schema())
        self._schema_widgets: list[QWidget] = []

    # ── Filter ────────────────────────────────────────────────────────────────
    def _filter(self, text: str):
        text = text.strip().lower()
        visible_groups: set[QLabel] = set()

        for node_type, item, grp_lbl in self._items:
            match = (not text) or (text in item.text().lower()) or (text in node_type)
            item.setVisible(match)
            if match:
                visible_groups.add(grp_lbl)

        for lbl in self._group_labels:
            lbl.setVisible(lbl in visible_groups)

    # ── Schema loading ────────────────────────────────────────────────────────
    def load_schema(self, inspector) -> None:
        """Populate the 'Schema' section from a SchemaInspector instance.

        Expects inspector to have .get_functions() -> list[str]
        and .get_procedures() -> list[str].
        """
        # Remove previously added schema widgets
        for w in self._schema_widgets:
            self._list_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._schema_widgets.clear()

        # Insert before the trailing stretch (count()-1)
        insert_pos = self._list_layout.count() - 1

        def _add_section(title: str, entries: list[tuple[str, str, bytes]]):
            nonlocal insert_pos
            if not entries:
                return
            grp = QLabel(f"  {title}")
            grp.setFont(_GROUP_FONT)
            grp.setObjectName("palette_group")
            grp.setFixedHeight(22)
            self._list_layout.insertWidget(insert_pos, grp)
            self._schema_widgets.append(grp)
            insert_pos += 1
            for node_type, display, payload in entries:
                item = _PaletteItem(node_type, display, mime_override=payload)
                self._list_layout.insertWidget(insert_pos, item)
                self._schema_widgets.append(item)
                insert_pos += 1

        # Functions subsection
        try:
            funcs = inspector.get_functions()
        except Exception:
            funcs = []
        func_entries = [
            ("function", f"ƒ  {name}",
             json.dumps({"type": "function", "name": name}).encode())
            for name in funcs
        ]

        # Procedures subsection
        try:
            procs = inspector.get_procedures()
        except Exception:
            procs = []
        proc_entries = [
            ("procedure", f"⚙  {name}",
             json.dumps({"type": "procedure", "name": name}).encode())
            for name in procs
        ]

        # Add a top-level "Schema" label if either has content
        if func_entries or proc_entries:
            schema_hdr = QLabel("  Schema")
            schema_hdr.setFont(_TITLE_FONT)
            schema_hdr.setObjectName("palette_group")
            schema_hdr.setFixedHeight(22)
            self._list_layout.insertWidget(insert_pos, schema_hdr)
            self._schema_widgets.append(schema_hdr)
            insert_pos += 1

        _add_section("Funções do banco", func_entries)
        _add_section("Procedures",       proc_entries)
