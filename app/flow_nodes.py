from __future__ import annotations
"""
flow_nodes.py — All node types for the FlowSQL visual query builder.

Every node is a QGraphicsItem drawn purely with QPainter (no child widgets
on the canvas itself). Interactive editing happens in the Properties panel.
"""

import uuid
from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath,
)
from PyQt5.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneMouseEvent, QGraphicsSceneContextMenuEvent,
    QGraphicsProxyWidget,
    QComboBox, QLineEdit, QHBoxLayout, QApplication, QMenu,
)

# ── Colour palettes (updated by theme_manager at runtime) ─────────────────────
_THEME: dict = {
    "body_bg":    "#2d2d30",
    "body_border": "#555555",
    "header_bg":  "#3e3e42",
    "header_fg":  "#d4d4d4",
    "sel_border": "#0078d4",
    "sel_header": "#094771",
    "icon_color": "#a0a0a0",
    "label_fg":   "#a0a0a0",
    "value_fg":   "#d4d4d4",
    "type_fg":    "#666666",
    "port_border": "#555555",
    "port_fill":  "transparent",
    "port_conn":  "#0078d4",
    "conn_line":  "#555555",
    # FunctionNode header
    "func_header_bg": "#1c3a2a",
    "func_header_fg": "#6ee7b7",
    # ProcedureNode header
    "proc_header_bg": "#1e1b4b",
    "proc_header_fg": "#a5b4fc",
    # UnionNode header
    "union_header_bg": "#1c2333",
    "union_header_fg": "#93c5fd",
    # UpdateNode header
    "update_header_bg": "#431407",
    "update_header_fg": "#fdba74",
    # DeleteNode header
    "delete_header_bg": "#450a0a",
    "delete_header_fg": "#fca5a5",
}


def apply_node_theme(theme: str):
    """Called by ThemeManager / FlowCanvas when the theme changes."""
    global _THEME
    if theme == "dark":
        _THEME.update({
            "body_bg":    "#2d2d30",
            "body_border": "#555555",
            "header_bg":  "#3e3e42",
            "header_fg":  "#d4d4d4",
            "sel_border": "#0078d4",
            "sel_header": "#094771",
            "icon_color": "#a0a0a0",
            "label_fg":   "#a0a0a0",
            "value_fg":   "#d4d4d4",
            "type_fg":    "#666666",
            "port_border": "#555555",
            "port_fill":  "#2d2d30",
            "port_conn":  "#0078d4",
            "conn_line":  "#555555",
            "func_header_bg":  "#1c3a2a",
            "func_header_fg":  "#6ee7b7",
            "proc_header_bg":  "#1e1b4b",
            "proc_header_fg":  "#a5b4fc",
            "union_header_bg": "#1c2333",
            "union_header_fg": "#93c5fd",
            "update_header_bg": "#431407",
            "update_header_fg": "#fdba74",
            "delete_header_bg": "#450a0a",
            "delete_header_fg": "#fca5a5",
        })
    else:
        _THEME.update({
            "body_bg":    "#ffffff",
            "body_border": "#bbbbbb",
            "header_bg":  "#f0f0f0",
            "header_fg":  "#1e1e1e",
            "sel_border": "#0078d4",
            "sel_header": "#cce8ff",
            "icon_color": "#555555",
            "label_fg":   "#555555",
            "value_fg":   "#1e1e1e",
            "type_fg":    "#999999",
            "port_border": "#bbbbbb",
            "port_fill":  "#ffffff",
            "port_conn":  "#0078d4",
            "conn_line":  "#aaaaaa",
            "func_header_bg":  "#d1fae5",
            "func_header_fg":  "#065f46",
            "proc_header_bg":  "#ede9fe",
            "proc_header_fg":  "#3730a3",
            "union_header_bg": "#eff6ff",
            "union_header_fg": "#1d4ed8",
            "update_header_bg": "#fff7ed",
            "update_header_fg": "#9a3412",
            "delete_header_bg": "#fef2f2",
            "delete_header_fg": "#991b1b",
        })


# ── Dimensions ────────────────────────────────────────────────────────────────
NODE_WIDTH   = 220
HEADER_H     = 28
ROW_H        = 22
PORT_R       = 5       # radius
PORT_D       = PORT_R * 2
PADDING      = 10

# ── Header fonts ─────────────────────────────────────────────────────────────
_HEADER_FONT = QFont("Segoe UI", 9, QFont.Bold)
_LABEL_FONT  = QFont("Segoe UI", 8)
_VALUE_FONT  = QFont("Consolas", 8)
_ICON_FONT   = QFont("Segoe UI", 11)


# ── Port descriptor ───────────────────────────────────────────────────────────
class Port:
    """Logical port on a node."""
    def __init__(self, node: "BaseNode", port_id: str, side: str, row: int = 0,
                 label: str = "", col_type: str = "", port_kind: str = "data"):
        self.node = node
        self.port_id = port_id
        self.side = side          # "in" | "out"
        self.row = row            # vertical slot index
        self.label = label        # display name shown next to the port dot
        self.col_type = col_type  # SQL type ("int", "varchar", etc.)
        self.kind = port_kind     # "data" | "context" | "field"
        self.connected = False

    def scene_pos(self) -> QPointF:
        """Return scene position.  Delegates to the node's _port_local() so
        that nodes with custom geometry (SelectNode, JoinNode) keep connections
        aligned with their painted port dots."""
        node_pos = self.node.pos()
        local = self.node._port_local(self)
        return QPointF(node_pos.x() + local.x(), node_pos.y() + local.y())


# ── BaseNode ──────────────────────────────────────────────────────────────────
class BaseNode(QGraphicsObject):
    """
    Abstract base for all flow nodes.

    Subclasses must implement:
        icon()   → str   (single unicode character)
        label()  → str   (header text e.g. "TABLE")
        rows()   → list  (list of (label, value) tuples for body rendering)
        get_ast()→ dict
        to_dict()→ dict  (for serialisation)
        load_from_dict(data: dict)
    """

    node_selected   = pyqtSignal(object)   # emits self
    node_changed    = pyqtSignal(object)   # data changed → SQL regen
    position_changed = pyqtSignal(object)  # moved → update connections
    port_connected  = pyqtSignal(str)      # emits port_id after a connection is made
    execute_requested = pyqtSignal(object) # emits self → canvas runs SQL for this node

    def __init__(self, node_id: str = "", parent=None):
        super().__init__(parent)
        self.node_id   = node_id or str(uuid.uuid4())[:8]
        self.node_type = "base"
        self._selected = False
        self._data: dict = {}

        # Subclasses may override to use custom theme keys for header colour
        self._header_bg_key: str = "header_bg"
        self._header_fg_key: str = "header_fg"

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

        # Ports (populated by subclasses)
        self.in_ports:  list[Port] = []
        self.out_ports: list[Port] = []

        self._hover = False
        self._proxies: list[QGraphicsProxyWidget] = []   # inline editors

    # ── Inline proxy widget helpers ───────────────────────────────────────────
    def _open_proxy(self, widget: QWidget, local_rect: QRectF) -> QGraphicsProxyWidget:
        """Embed *widget* as a proxy at *local_rect* (local coords)."""
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(widget)
        proxy.setGeometry(local_rect)
        proxy.setZValue(10)
        self._proxies.append(proxy)
        return proxy

    def close_all_proxies(self):
        """Remove all embedded inline editors."""
        for px in list(self._proxies):
            px.setParent(None)
            if px.scene():
                px.scene().removeItem(px)
        self._proxies.clear()

    # ── Abstract interface ────────────────────────────────────────────────────
    def icon(self) -> str:      return "■"
    def label(self) -> str:     return "NODE"
    def rows(self) -> list:     return []
    def get_ast(self) -> dict:  return {"type": self.node_type}
    def to_dict(self) -> dict:
        return {
            "id":   self.node_id,
            "type": self.node_type,
            "x":    self.pos().x(),
            "y":    self.pos().y(),
            "data": dict(self._data),
        }
    def load_from_dict(self, data: dict): pass

    # ── Geometry ──────────────────────────────────────────────────────────────
    def _body_height(self) -> float:
        n_rows = len(self.rows())
        n_ports = max(len(self.in_ports), len(self.out_ports))
        n = max(n_rows, n_ports, 1)
        return HEADER_H + PADDING + n * ROW_H + PADDING

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_WIDTH, self._body_height())

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        rect = self.boundingRect()
        selected = self.isSelected()

        # ─ Shadow ─────────────────────────────────────────────────────────
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(rect.adjusted(3, 3, 3, 3), 4, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawPath(shadow_path)

        # ─ Body ───────────────────────────────────────────────────────────
        body_path = QPainterPath()
        body_path.addRoundedRect(rect, 4, 4)
        painter.setBrush(QColor(_THEME["body_bg"]))
        border_color = _THEME["sel_border"] if selected else _THEME["body_border"]
        border_width = 2 if selected else 1
        painter.setPen(QPen(QColor(border_color), border_width))
        painter.drawPath(body_path)

        # ─ Header ─────────────────────────────────────────────────────────
        header_rect = QRectF(0, 0, NODE_WIDTH, HEADER_H)
        header_path = QPainterPath()
        header_path.addRoundedRect(header_rect, 4, 4)
        # square off bottom corners
        header_path.addRect(QRectF(0, HEADER_H / 2, NODE_WIDTH, HEADER_H / 2))
        header_bg = _THEME["sel_header"] if selected else _THEME[self._header_bg_key]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(header_bg))
        painter.drawPath(header_path)

        # ─ Icon ───────────────────────────────────────────────────────────
        painter.setFont(_ICON_FONT)
        painter.setPen(QColor(_THEME["icon_color"]))
        painter.drawText(
            QRectF(PADDING, 0, 22, HEADER_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.icon(),
        )

        # ─ Header label ───────────────────────────────────────────────────
        painter.setFont(_HEADER_FONT)
        header_fg = _THEME[self._header_fg_key] if not selected else _THEME["header_fg"]
        painter.setPen(QColor(header_fg))
        painter.drawText(
            QRectF(PADDING + 22, 0, NODE_WIDTH - PADDING * 2 - 22, HEADER_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.label(),
        )

        # ─ Body rows ──────────────────────────────────────────────────────
        y0 = HEADER_H + PADDING
        for i, (lbl, val) in enumerate(self.rows()):
            ry = y0 + i * ROW_H
            # Label
            painter.setFont(_LABEL_FONT)
            painter.setPen(QColor(_THEME["label_fg"]))
            painter.drawText(
                QRectF(PADDING, ry, 70, ROW_H),
                Qt.AlignVCenter | Qt.AlignLeft,
                str(lbl) + ":",
            )
            # Value
            painter.setFont(_VALUE_FONT)
            painter.setPen(QColor(_THEME["value_fg"]))
            val_str = str(val) if val is not None else ""
            fm = QFontMetrics(_VALUE_FONT)
            val_str = fm.elidedText(val_str, Qt.ElideRight, NODE_WIDTH - 80 - PADDING)
            painter.drawText(
                QRectF(80, ry, NODE_WIDTH - 80 - PADDING, ROW_H),
                Qt.AlignVCenter | Qt.AlignLeft,
                val_str,
            )

        # ─ Ports ──────────────────────────────────────────────────────────
        self._paint_ports(painter)

    def _paint_ports(self, painter: QPainter):
        for port in self.in_ports + self.out_ports:
            local_pos = self._port_local(port)
            fill = _THEME["port_conn"] if port.connected else _THEME["port_fill"]
            # Use distinct shape for context ports (diamond-ish via larger dot)
            painter.setPen(QPen(QColor(_THEME["port_border"]), 1))
            painter.setBrush(QColor(fill) if fill != "transparent" else Qt.NoBrush)
            painter.drawEllipse(local_pos, PORT_R, PORT_R)

            # Draw port label for ports that have one
            if port.label:
                painter.setFont(_LABEL_FONT)
                painter.setPen(QColor(_THEME["label_fg"]))
                if port.side == "out":
                    # Right-aligned inside body, ending just before the port dot
                    label_rect = QRectF(PADDING, local_pos.y() - ROW_H / 2,
                                        NODE_WIDTH - PADDING * 2 - PORT_R - 4, ROW_H)
                    painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignRight, port.label)
                else:
                    # Left-aligned, starting after the port dot
                    label_rect = QRectF(PORT_R + 4, local_pos.y() - ROW_H / 2,
                                        NODE_WIDTH - PADDING * 2 - PORT_R - 4, ROW_H)
                    painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, port.label)

    def _port_local(self, port: Port) -> QPointF:
        x = 0 if port.side == "in" else NODE_WIDTH
        y = HEADER_H + PADDING + port.row * ROW_H + ROW_H / 2
        return QPointF(x, y)

    def port_local_pos(self, port_id: str) -> Optional[QPointF]:
        for p in self.in_ports + self.out_ports:
            if p.port_id == port_id:
                return self._port_local(p)
        return None

    def port_at(self, local_pos: QPointF) -> Optional[Port]:
        """Return the port whose hit-zone contains local_pos."""
        hit = PORT_R + 4
        for p in self.in_ports + self.out_ports:
            lp = self._port_local(p)
            if (local_pos - lp).manhattanLength() <= hit:
                return p
        return None

    # ── Item change ───────────────────────────────────────────────────────────
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.position_changed.emit(self)
        if change == QGraphicsItem.ItemSelectedHasChanged and value:
            self.node_selected.emit(self)
        return super().itemChange(change, value)

    # ── Hover ─────────────────────────────────────────────────────────────────
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    # ── Data helpers ──────────────────────────────────────────────────────────
    def set_data(self, key: str, value):
        self._data[key] = value
        self.prepareGeometryChange()
        self.update()
        self.node_changed.emit(self)

    def get_data(self, key: str, default=None):
        return self._data.get(key, default)


# ── Helper to create a single in/out port ────────────────────────────────────
def _add_port(node: BaseNode, side: str, row: int = 0, pid: str = "",
              label: str = "", col_type: str = "", port_kind: str = "data") -> Port:
    p = Port(node, pid or f"{side}_{row}", side, row,
             label=label, col_type=col_type, port_kind=port_kind)
    if side == "in":
        node.in_ports.append(p)
    else:
        node.out_ports.append(p)
    return p


def _add_field_port(node: BaseNode, side: str, col_name: str, col_type: str,
                    row: int, pid: str = "") -> Port:
    """Creates a port of kind='field' with label and type set."""
    return _add_port(node, side, row, pid or f"{side}_field_{row}",
                     label=col_name, col_type=col_type, port_kind="field")


# ──────────────────────────────────────────────────────────────────────────────
# Concrete node types
# ──────────────────────────────────────────────────────────────────────────────

class TableNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "table"
        self._data = {"name": "", "alias": ""}
        self._columns: list[dict] = []         # {"name": str, "type": str, "pk": bool}
        self._selected_cols: list[str] = []    # names of selected columns

        # Context port at row 0 (always present)
        _add_port(self, "out", 0, "out_ctx",
                  label="⬡ contexto", port_kind="context")

    def icon(self):  return "▦"
    def label(self): return "TABLE"

    def rows(self):
        # Body rendering is replaced entirely by port labels
        return []

    def set_schema_columns(self, columns: list[dict]):
        """Called when schema info is available. Rebuilds field ports."""
        self._columns = list(columns)
        self._rebuild_field_ports()

    def _rebuild_field_ports(self):
        """Remove all field ports and rebuild from _columns."""
        self.prepareGeometryChange()
        # Remove existing field ports (keep out_ctx at row 0)
        self.out_ports = [p for p in self.out_ports if p.port_id == "out_ctx"]
        # Add one field port per column (row 1+)
        for i, col in enumerate(self._columns):
            col_name = col.get("name", "")
            col_type = col.get("type", "")
            _add_field_port(self, "out", col_name, col_type, i + 1,
                            pid=f"out_field_{i}")
        self.update()

    def get_ast(self):
        return {
            "type":    "table",
            "name":    self._data.get("name", ""),
            "alias":   self._data.get("alias", ""),
            "columns": self._columns,
        }

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["columns"] = self._columns
        d["selected_cols"] = self._selected_cols
        return d

    def load_from_dict(self, data: dict):
        cols = data.get("columns", [])
        self._selected_cols = data.get("selected_cols", [])
        if cols:
            self.set_schema_columns(cols)


    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """Double-click on body → inline-edit table name."""
        local = event.pos()
        if local.y() > HEADER_H:
            self._open_name_editor()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _open_name_editor(self):
        self.close_all_proxies()
        le = QLineEdit()
        le.setText(self._data.get("name", ""))
        le.setPlaceholderText("nome da tabela…")
        le.selectAll()

        def _commit():
            text = le.text().strip()
            if text:
                self._data["name"] = text
                self.node_changed.emit(self)
                self.update()
            self.close_all_proxies()

        le.returnPressed.connect(_commit)
        le.editingFinished.connect(lambda: (_commit() if self._proxies else None))
        body_top = HEADER_H + PADDING
        self._open_proxy(le, QRectF(PADDING, body_top, NODE_WIDTH - PADDING * 2, ROW_H))
        le.setFocus()


class JoinNode(BaseNode):
    """
    JOIN node showing each ON-pair as a visual "card":
      [left-field port] [op badge] [right-field port]

    • No "tabela A/B" context ports — field ports only + one out_ctx output.
    • Connecting a TableNode field port auto-fills the qualified column name
      (table.column) from the source port's parent node.
    • Cards grow 2-at-a-time as connections are made.
    • Double-click on the op badge → cycle operator inline.
    • Double-click on the header → choose join type inline.
    """

    _JOIN_TYPES = ["INNER", "LEFT", "RIGHT", "FULL OUTER", "CROSS"]
    _OPS        = ["=", "<>", ">", "<", ">=", "<=", "LIKE", "IS NULL", "IS NOT NULL"]

    _CARD_H   = 48   # px per pair card
    _CARD_PAD = 4    # vertical gap between cards

    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "join"
        self._data = {
            "join_type":   "INNER",
            "alias":       "",
            "pairs":       [],
            "left_table":  "",   # mãe/contexto (via in_ctx ou primeiro campo esq.)
            "right_table": "",   # nova tabela sendo joinada (campos dir.)
        }

        # Context input: recebe a tabela mãe do nó anterior
        _add_port(self, "in",  0, "in_ctx",  label="contexto", port_kind="context")
        # Single output context port (what flows to the next node)
        _add_port(self, "out", 0, "out_ctx", label="resultado", port_kind="context")

        # Build the first empty pair slot
        self._rebuild_pair_ports()
        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "⋈"
    def label(self): return f"JOIN  [{self._data.get('join_type', 'INNER')}]"

    # ── Where cards start (immediately below header) ───────────────────────
    @property
    def _cards_top(self) -> float:
        return HEADER_H + PADDING

    # ── Port management ────────────────────────────────────────────────────
    def _n_pair_cards(self) -> int:
        return len(self._data.get("pairs", [])) + 1   # filled + 1 open slot

    def _rebuild_pair_ports(self):
        self.prepareGeometryChange()
        pairs = self._data.get("pairs", [])
        n     = len(pairs)

        # Remove existing pair ports (keep out_ctx)
        self.in_ports = [p for p in self.in_ports
                         if not (p.port_id.startswith("in_left_") or
                                 p.port_id.startswith("in_right_"))]

        # Each card occupies 2 rows starting at row 0
        for i in range(n + 1):
            _add_port(self, "in", i * 2,     f"in_left_{i}",  label="", port_kind="field")
            _add_port(self, "in", i * 2 + 1, f"in_right_{i}", label="", port_kind="field")
        self.update()

    def _on_port_connected(self, port_id: str):
        if not (port_id.startswith("in_left_") or port_id.startswith("in_right_")):
            return
        try:
            idx = int(port_id.split("_")[-1])
        except (ValueError, IndexError):
            return

        pairs = self._data.setdefault("pairs", [])
        while len(pairs) <= idx:
            pairs.append({"left_field": "", "right_field": "", "op": "="})

        # When the last slot has at least one connection → grow a new card
        last = len(pairs) - 1
        lp = next((p for p in self.in_ports if p.port_id == f"in_left_{last}"),  None)
        rp = next((p for p in self.in_ports if p.port_id == f"in_right_{last}"), None)
        if lp and rp and (lp.connected or rp.connected):
            self._rebuild_pair_ports()

    def _on_field_port_connected(self, port_id: str, from_port: "Port"):
        """Called by canvas after a field connection is established.

        Reads the source port's label (column name) and its parent node's
        table name to build a qualified name: ``table.column``.
        """
        # Context connection → captura o nome da tabela mãe
        if port_id == "in_ctx":
            table_name = getattr(from_port.node, "_data", {}).get("name", "")
            if table_name:
                self._data["left_table"] = table_name
            self.update()
            return

        try:
            idx = int(port_id.split("_")[-1])
        except (ValueError, IndexError):
            return

        pairs = self._data.setdefault("pairs", [])
        while len(pairs) <= idx:
            pairs.append({"left_field": "", "right_field": "", "op": "="})

        # Build qualified name "table.column" from source port
        col_name   = from_port.label or from_port.port_id
        table_name = getattr(from_port.node, "_data", {}).get("name", "")
        qualified  = f"{table_name}.{col_name}" if table_name else col_name

        if port_id.startswith("in_left_"):
            pairs[idx]["left_field"] = qualified
            # Infere left_table do primeiro campo esq. se ainda não definida
            if table_name and not self._data.get("left_table"):
                self._data["left_table"] = table_name
        else:
            pairs[idx]["right_field"] = qualified
            # right_table sempre é derivada dos campos dir.
            if table_name:
                self._data["right_table"] = table_name
        self.update()

    # ── Geometry (no ctx-port row area) ──────────────────────────────────
    def _body_height(self) -> float:
        return self._cards_top + self._n_pair_cards() * self._CARD_H + PADDING

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_WIDTH, self._body_height())

    # ── Paint ─────────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        h = self._body_height()
        rect = QRectF(0, 0, NODE_WIDTH, h)
        selected = self.isSelected()

        # Shadow
        shadow = QPainterPath()
        shadow.addRoundedRect(rect.adjusted(3, 3, 3, 3), 4, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawPath(shadow)

        # Body
        body = QPainterPath()
        body.addRoundedRect(rect, 4, 4)
        painter.setBrush(QColor(_THEME["body_bg"]))
        painter.setPen(QPen(QColor(_THEME["sel_border"] if selected else _THEME["body_border"]),
                            2 if selected else 1))
        painter.drawPath(body)

        # Header
        hr = QRectF(0, 0, NODE_WIDTH, HEADER_H)
        hp = QPainterPath()
        hp.addRoundedRect(hr, 4, 4)
        hp.addRect(QRectF(0, HEADER_H / 2, NODE_WIDTH, HEADER_H / 2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_THEME["sel_header"] if selected else _THEME[self._header_bg_key]))
        painter.drawPath(hp)

        painter.setFont(_ICON_FONT)
        painter.setPen(QColor(_THEME["icon_color"]))
        painter.drawText(QRectF(PADDING, 0, 22, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.icon())

        painter.setFont(_HEADER_FONT)
        painter.setPen(QColor(_THEME["header_fg"] if selected else _THEME[self._header_fg_key]))
        painter.drawText(QRectF(PADDING + 22, 0, NODE_WIDTH - PADDING * 2 - 22, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.label())

        # Pair cards (start right below header)
        pairs    = self._data.get("pairs", [])
        n_cards  = self._n_pair_cards()
        ctx_y    = self._cards_top
        card_bg  = QColor(_THEME["header_bg"])
        op_color = QColor(_THEME["sel_border"])

        fm   = QFontMetrics(_LABEL_FONT)
        op_w = fm.horizontalAdvance("IS NOT NULL") + 8

        for i in range(n_cards):
            cy   = ctx_y + i * self._CARD_H
            pair = pairs[i] if i < len(pairs) else {}
            lf   = pair.get("left_field",  "") or "(campo esq.)"
            rf   = pair.get("right_field", "") or "(campo dir.)"
            op   = pair.get("op", "=")

            # Card background
            card_rect = QRectF(PADDING, cy, NODE_WIDTH - PADDING * 2,
                               self._CARD_H - self._CARD_PAD)
            painter.setPen(Qt.NoPen)
            painter.setBrush(card_bg)
            rounded = QPainterPath()
            rounded.addRoundedRect(card_rect, 3, 3)
            painter.drawPath(rounded)

            rh = (self._CARD_H - self._CARD_PAD) / 2
            text_w = NODE_WIDTH - PADDING * 2 - op_w - PORT_R * 2 - 12

            # Left field (top sub-row)
            painter.setFont(_LABEL_FONT)
            painter.setPen(QColor(_THEME["value_fg"]))
            lf_rect = QRectF(PADDING + PORT_R + 6, cy, text_w, rh)
            painter.drawText(lf_rect, Qt.AlignVCenter | Qt.AlignLeft,
                             fm.elidedText(lf, Qt.ElideRight, int(lf_rect.width())))

            # Right field (bottom sub-row)
            rf_rect = QRectF(PADDING + PORT_R + 6, cy + rh, text_w, rh)
            painter.drawText(rf_rect, Qt.AlignVCenter | Qt.AlignLeft,
                             fm.elidedText(rf, Qt.ElideRight, int(rf_rect.width())))

            # Op badge (right of card, vertically centred)
            op_x    = NODE_WIDTH - PADDING - op_w
            op_rect = QRectF(op_x, cy + 4, op_w, self._CARD_H - self._CARD_PAD - 8)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_THEME["body_bg"]))
            painter.drawRoundedRect(op_rect, 3, 3)
            painter.setFont(QFont("Consolas", 8, QFont.Bold))
            painter.setPen(op_color)
            painter.drawText(op_rect, Qt.AlignCenter, op)

        # Ports (uses _port_local for correct positions)
        self._paint_ports(painter)

    # ── Port local positions ─────────────────────────────────────────────
    def _port_local(self, port: "Port") -> QPointF:
        ctx_y = self._cards_top
        if port.port_id == "in_ctx":
            # Porta de contexto no topo esquerdo (área do header)
            return QPointF(0, HEADER_H / 2)
        if port.port_id.startswith("in_left_"):
            try:
                i = int(port.port_id.split("_")[-1])
            except (ValueError, IndexError):
                i = 0
            y = ctx_y + i * self._CARD_H + (self._CARD_H - self._CARD_PAD) / 4
            return QPointF(0, y)
        if port.port_id.startswith("in_right_"):
            try:
                i = int(port.port_id.split("_")[-1])
            except (ValueError, IndexError):
                i = 0
            y = ctx_y + i * self._CARD_H + (self._CARD_H - self._CARD_PAD) * 3 / 4
            return QPointF(0, y)
        # out_ctx: right side, vertically centred
        return QPointF(NODE_WIDTH, self._body_height() / 2)

    # ── Double-click ─────────────────────────────────────────────────────
    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        ctx_y = self._cards_top
        pairs = self._data.get("pairs", [])

        # Header → change join type
        if local.y() <= HEADER_H:
            self._open_join_type_combo()
            event.accept()
            return

        # Op badge on a card → change operator
        fm   = QFontMetrics(_LABEL_FONT)
        op_w = fm.horizontalAdvance("IS NOT NULL") + 8
        op_x = NODE_WIDTH - PADDING - op_w
        for i in range(len(pairs)):
            cy   = ctx_y + i * self._CARD_H
            cy_e = cy + self._CARD_H - self._CARD_PAD
            if op_x <= local.x() <= NODE_WIDTH - PADDING and cy <= local.y() <= cy_e:
                self._open_op_combo(i, QRectF(op_x, cy + 4, op_w,
                                              self._CARD_H - self._CARD_PAD - 8))
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _open_op_combo(self, pair_idx: int, rect: QRectF):
        self.close_all_proxies()
        cb = QComboBox()
        cb.addItems(self._OPS)
        pairs = self._data.get("pairs", [])
        if pair_idx < len(pairs):
            cur = pairs[pair_idx].get("op", "=")
            idx = cb.findText(cur)
            if idx >= 0:
                cb.setCurrentIndex(idx)

        def _commit():
            if pair_idx < len(self._data.get("pairs", [])):
                self._data["pairs"][pair_idx]["op"] = cb.currentText()
                self.node_changed.emit(self)
                self.update()
            self.close_all_proxies()

        cb.activated.connect(lambda _: _commit())
        self._open_proxy(cb, rect)
        cb.setFocus()
        cb.showPopup()

    def _open_join_type_combo(self):
        self.close_all_proxies()
        cb = QComboBox()
        cb.addItems(self._JOIN_TYPES)
        cur = self._data.get("join_type", "INNER")
        idx = cb.findText(cur)
        if idx >= 0:
            cb.setCurrentIndex(idx)

        def _commit():
            self._data["join_type"] = cb.currentText()
            self.node_changed.emit(self)
            self.update()
            self.close_all_proxies()

        cb.activated.connect(lambda _: _commit())
        self._open_proxy(cb, QRectF(PADDING + 22, 2,
                                    NODE_WIDTH - PADDING * 2 - 22, HEADER_H - 4))
        cb.setFocus()
        cb.showPopup()

    # ── rows() / get_ast() / to_dict() ───────────────────────────────────
    def rows(self):
        return []   # paint() handles all visual rendering

    def get_ast(self):
        """Return AST fragment; ASTBuilder reads this via to_dict()."""
        pairs = self._data.get("pairs", [])
        on_parts: list[str]  = []
        left_tables:  set[str] = set()
        right_tables: set[str] = set()
        for p in pairs:
            lf = p.get("left_field", "")
            rf = p.get("right_field", "")
            op = p.get("op", "=")
            if lf and rf:
                on_parts.append(f"{lf} {op} {rf}")
            if lf and "." in lf:
                left_tables.add(lf.split(".")[0])
            if rf and "." in rf:
                right_tables.add(rf.split(".")[0])
        on_str = " AND ".join(on_parts)
        # left_table: explícita (in_ctx ou campo esq.) ou inferida
        left_table  = self._data.get("left_table",  "") or next(iter(left_tables),  "")
        # right_table: explícita (campo dir.) ou inferida
        right_table = self._data.get("right_table", "") or next(iter(right_tables), "")
        return {
            "type":        "join",
            "join_type":   self._data.get("join_type", "INNER"),
            "left_table":  left_table,
            "right_table": right_table,
            "table":       right_table,   # compat retroativo
            "alias":       self._data.get("alias", ""),
            "on":          on_str,
            "pairs":       pairs,
        }

    def to_dict(self) -> dict:
        d = super().to_dict()
        ast = self.get_ast()
        d["data"].update({
            "join_type":   ast["join_type"],
            "left_table":  ast["left_table"],
            "right_table": ast["right_table"],
            "table":       ast["table"],
            "alias":       ast["alias"],
            "on":          ast["on"],
            "pairs":       list(self._data.get("pairs", [])),
        })
        return d


# ─────────────────────────────────────────────────────────────────────────────
class SelectNode(BaseNode):
    """Resizable SELECT node with inline result display and quick-filter presets."""

    _QUICK_FILTERS = [
        "nenhum",
        "TOP 10",
        "TOP 100",
        "TOP 1000",
        "TOP 10000",
        "DISTINCT",
        "TOP 10 DISTINCT",
        "TOP 100 DISTINCT",
        "TOP 1000 DISTINCT",
    ]
    _FILTER_BAR_H = 26
    _RUN_BTN_W    = 80

    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "select"
        self._data = {
            "distinct":     False,
            "fields":       [],        # [] = all columns
            "quick_filter": "TOP 100",
            "result_rows":  [],
            "result_cols":  [],
            "w":            240,
            "h":            160,
        }
        self._available_columns: list[dict] = []
        self._result_dialog = None   # keep reference to prevent GC

        # Resize state
        self._resizing:      bool    = False
        self._resize_corner: str     = ""   # "br" | "mr" | "mb"
        self._resize_start:  QPointF = QPointF()
        self._resize_w0:     float   = 240.0
        self._resize_h0:     float   = 140.0

        _add_port(self, "in",  0, "in_ctx",  label="entrada", port_kind="context")
        _add_port(self, "out", 0, "out_ctx", label="saída",   port_kind="context")

        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "◻"
    def label(self): return "SELECT / RESULTADO"

    def _on_port_connected(self, port_id: str):
        pass  # available columns set externally via _available_columns

    def set_result(self, cols: list, rows: list):
        self._data["result_cols"] = list(cols)
        self._data["result_rows"] = list(rows)
        self.prepareGeometryChange()
        self.update()

    def rows(self):
        result = [("distinct", "✓" if self._data.get("distinct") else "✗")]
        qf = self._data.get("quick_filter", "nenhum")
        if qf and qf != "nenhum":
            result.append(("filtro", qf))
        for f in self._data.get("fields", []):
            result.append(("col", f))
        return result

    def get_ast(self):
        return {
            "type":         "select",
            "fields":       self._data.get("fields", []),
            "distinct":     self._data.get("distinct", False),
            "quick_filter": self._data.get("quick_filter", "nenhum"),
        }

    # ── Geometry ──────────────────────────────────────────────────────────────
    def _body_height(self) -> float:
        return float(self._data.get("h", 160))

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._data.get("w", 240), self._data.get("h", 160))

    def _content_top(self) -> float:
        """Y pixel where body content starts (below header + filter bar)."""
        return float(HEADER_H + self._FILTER_BAR_H)

    # ── Resize handle positions (local coords) ────────────────────────────────
    def _handle_br(self) -> QPointF:
        return QPointF(self._data["w"], self._data["h"])

    def _handle_mr(self) -> QPointF:
        return QPointF(self._data["w"], self._data["h"] / 2)

    def _handle_mb(self) -> QPointF:
        return QPointF(self._data["w"] / 2, self._data["h"])

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        w = self._data.get("w", 240)
        h = self._data.get("h", 160)
        rect = QRectF(0, 0, w, h)
        selected = self.isSelected()

        # Shadow
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(rect.adjusted(3, 3, 3, 3), 4, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawPath(shadow_path)

        # Body
        body_path = QPainterPath()
        body_path.addRoundedRect(rect, 4, 4)
        painter.setBrush(QColor(_THEME["body_bg"]))
        border_color = _THEME["sel_border"] if selected else _THEME["body_border"]
        painter.setPen(QPen(QColor(border_color), 2 if selected else 1))
        painter.drawPath(body_path)

        # Header
        hr = QRectF(0, 0, w, HEADER_H)
        hp = QPainterPath()
        hp.addRoundedRect(hr, 4, 4)
        hp.addRect(QRectF(0, HEADER_H / 2, w, HEADER_H / 2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_THEME["sel_header"] if selected else _THEME[self._header_bg_key]))
        painter.drawPath(hp)

        # Icon
        painter.setFont(_ICON_FONT)
        painter.setPen(QColor(_THEME["icon_color"]))
        painter.drawText(QRectF(PADDING, 0, 22, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.icon())

        # Header label
        painter.setFont(_HEADER_FONT)
        header_fg = _THEME[self._header_fg_key] if not selected else _THEME["header_fg"]
        painter.setPen(QColor(header_fg))
        painter.drawText(QRectF(PADDING + 22, 0, w - PADDING * 2 - 22, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.label())

        # ── Filter bar (below header) ──────────────────────────────────────
        fb_y = HEADER_H
        fb_h = self._FILTER_BAR_H
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_THEME["header_bg"]))
        painter.drawRect(QRectF(0, fb_y, w, fb_h))

        # Separator line
        painter.setPen(QPen(QColor(_THEME["body_border"]), 1))
        painter.drawLine(QPointF(0, fb_y), QPointF(w, fb_y))
        painter.drawLine(QPointF(0, fb_y + fb_h), QPointF(w, fb_y + fb_h))

        # Filter label
        qf = self._data.get("quick_filter", "nenhum")
        qf_text = qf if qf != "nenhum" else "sem filtro"
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor(_THEME["value_fg"]))
        painter.drawText(QRectF(PADDING, fb_y, w - PADDING - self._RUN_BTN_W - 4, fb_h),
                         Qt.AlignVCenter | Qt.AlignLeft, qf_text)

        # ▶ Run button on the right of filter bar
        run_x = w - self._RUN_BTN_W - 2
        run_rect = QRectF(run_x, fb_y + 3, self._RUN_BTN_W - 2, fb_h - 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#22c55e"))
        rounded_run = QPainterPath()
        rounded_run.addRoundedRect(run_rect, 3, 3)
        painter.drawPath(rounded_run)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(run_rect, Qt.AlignCenter, "▶")

        # ── Body rows (distinct + field list) ─────────────────────────────
        y0 = self._content_top() + PADDING
        for i, (lbl, val) in enumerate(self.rows()):
            ry = y0 + i * ROW_H
            if ry + ROW_H > h - PADDING:
                break
            painter.setFont(_LABEL_FONT)
            painter.setPen(QColor(_THEME["label_fg"]))
            painter.drawText(QRectF(PADDING, ry, 70, ROW_H),
                             Qt.AlignVCenter | Qt.AlignLeft, str(lbl) + ":")
            painter.setFont(_VALUE_FONT)
            painter.setPen(QColor(_THEME["value_fg"]))
            fm = QFontMetrics(_VALUE_FONT)
            val_str = fm.elidedText(str(val), Qt.ElideRight, int(w - 80 - PADDING))
            painter.drawText(QRectF(80, ry, w - 80 - PADDING, ROW_H),
                             Qt.AlignVCenter | Qt.AlignLeft, val_str)

        # ── Inline result mini-table ───────────────────────────────────────
        result_cols = self._data.get("result_cols", [])
        result_rows = self._data.get("result_rows", [])
        body_rows_h = self._content_top() + PADDING + len(self.rows()) * ROW_H + PADDING
        if result_cols and h > body_rows_h + 20:
            table_y = body_rows_h
            max_data_rows = max(0, int((h - table_y - PADDING) // 18))
            col_w = max(40, int((w - PADDING * 2) // max(len(result_cols), 1)))

            # Header row
            painter.setFont(_VALUE_FONT)
            painter.setBrush(QColor(_THEME["header_bg"]))
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(PADDING, table_y, w - PADDING * 2, 18))
            painter.setPen(QColor(_THEME["label_fg"]))
            for ci, col in enumerate(result_cols):
                cx = PADDING + ci * col_w
                fm = QFontMetrics(_VALUE_FONT)
                painter.drawText(QRectF(cx + 2, table_y, col_w - 4, 18),
                                 Qt.AlignVCenter | Qt.AlignLeft,
                                 fm.elidedText(str(col), Qt.ElideRight, int(col_w - 4)))

            # Data rows
            for ri, row in enumerate(result_rows[:max_data_rows]):
                ry2 = table_y + 18 + ri * 18
                bg = QColor(_THEME["body_bg"]) if ri % 2 == 0 else QColor(_THEME["body_bg"]).lighter(115)
                painter.setPen(Qt.NoPen)
                painter.setBrush(bg)
                painter.drawRect(QRectF(PADDING, ry2, w - PADDING * 2, 18))
                painter.setPen(QColor(_THEME["value_fg"]))
                painter.setFont(_VALUE_FONT)
                for ci, col in enumerate(result_cols):
                    cx = PADDING + ci * col_w
                    cell_val = str(row.get(col, "")) if isinstance(row, dict) else (
                        str(row[ci]) if ci < len(row) else "")
                    fm = QFontMetrics(_VALUE_FONT)
                    painter.drawText(QRectF(cx + 2, ry2, col_w - 4, 18),
                                     Qt.AlignVCenter | Qt.AlignLeft,
                                     fm.elidedText(cell_val, Qt.ElideRight, int(col_w - 4)))

        # Ports
        self._paint_ports_for_width(painter, w)

        # Resize handles (when selected)
        if selected:
            handle_color = QColor(_THEME["sel_border"])
            painter.setPen(QPen(handle_color, 1))
            painter.setBrush(handle_color)
            for pt in (self._handle_br(), self._handle_mr(), self._handle_mb()):
                painter.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))

    def _paint_ports_for_width(self, painter: QPainter, w: float):
        """Paint ports using current node width."""
        for port in self.in_ports + self.out_ports:
            x = 0 if port.side == "in" else w
            y = self._content_top() + PADDING + port.row * ROW_H + ROW_H / 2
            local_pos = QPointF(x, y)
            fill = _THEME["port_conn"] if port.connected else _THEME["port_fill"]
            painter.setPen(QPen(QColor(_THEME["port_border"]), 1))
            painter.setBrush(QColor(fill) if fill != "transparent" else Qt.NoBrush)
            painter.drawEllipse(local_pos, PORT_R, PORT_R)
            if port.label:
                painter.setFont(_LABEL_FONT)
                painter.setPen(QColor(_THEME["label_fg"]))
                if port.side == "out":
                    label_rect = QRectF(PADDING, y - ROW_H / 2,
                                        w - PADDING * 2 - PORT_R - 4, ROW_H)
                    painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignRight, port.label)
                else:
                    label_rect = QRectF(PORT_R + 4, y - ROW_H / 2,
                                        w - PADDING * 2 - PORT_R - 4, ROW_H)
                    painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, port.label)

    # Override scene_pos to use variable width for out ports
    def _port_local(self, port: "Port") -> QPointF:
        x = 0 if port.side == "in" else self._data.get("w", 240)
        y = self._content_top() + PADDING + port.row * ROW_H + ROW_H / 2
        return QPointF(x, y)

    # ── Resize mouse handling ─────────────────────────────────────────────────
    def _handle_at(self, local: QPointF) -> str:
        """Return 'br', 'mr', 'mb' if local is near a resize handle, else ''."""
        hit = 10
        for name, pt in [("br", self._handle_br()),
                         ("mr", self._handle_mr()),
                         ("mb", self._handle_mb())]:
            if (local - pt).manhattanLength() <= hit:
                return name
        return ""

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        w = self._data.get("w", 240)
        # Check ▶ run button in filter bar
        fb_y = HEADER_H
        fb_h = self._FILTER_BAR_H
        run_x = w - self._RUN_BTN_W - 2
        if (run_x <= local.x() <= w - 2 and fb_y <= local.y() <= fb_y + fb_h):
            self.execute_requested.emit(self)
            event.accept()
            return
        handle = self._handle_at(local)
        if handle and self.isSelected():
            self._resizing = True
            self._resize_corner = handle
            self._resize_start = local
            self._resize_w0 = float(self._data["w"])
            self._resize_h0 = float(self._data["h"])
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        w = self._data.get("w", 240)
        fb_y = HEADER_H
        fb_h = self._FILTER_BAR_H
        # Double-click on filter bar (not the ▶ button) → open filter combo
        run_x = w - self._RUN_BTN_W - 2
        if fb_y <= local.y() <= fb_y + fb_h and local.x() < run_x:
            self._open_filter_combo(w, fb_y, fb_h)
            event.accept()
            return
        # Double-click on result area → open expanded dialog
        result_top = self._content_top() + PADDING + len(self.rows()) * ROW_H + PADDING
        if local.y() >= result_top and self._data.get("result_cols"):
            self._show_result_dialog()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        """Right-click → copy result / error or open expanded view."""
        cols = self._data.get("result_cols", [])
        rows = self._data.get("result_rows", [])
        if not cols:
            super().contextMenuEvent(event)
            return
        menu = QMenu()
        act_copy = menu.addAction("Copiar resultado (TSV)")
        act_copy_err = None
        if cols == ["Erro"]:
            act_copy_err = menu.addAction("Copiar mensagem de erro")
        act_expand = menu.addAction("Expandir resultado…")
        action = menu.exec_(event.screenPos().toPoint())
        if action == act_copy:
            lines = ["\t".join(str(c) for c in cols)]
            for row in rows:
                if isinstance(row, dict):
                    lines.append("\t".join(str(row.get(c, "")) for c in cols))
            QApplication.clipboard().setText("\n".join(lines))
        elif act_copy_err and action == act_copy_err:
            msg = rows[0].get("Erro", "") if rows else ""
            QApplication.clipboard().setText(str(msg))
        elif action == act_expand:
            self._show_result_dialog()
        event.accept()

    def _open_filter_combo(self, w: float, fb_y: float, fb_h: float):
        self.close_all_proxies()
        cb = QComboBox()
        cb.addItems(self._QUICK_FILTERS)
        cur = self._data.get("quick_filter", "nenhum")
        idx = cb.findText(cur)
        if idx >= 0:
            cb.setCurrentIndex(idx)

        def _commit():
            self._data["quick_filter"] = cb.currentText()
            self.node_changed.emit(self)
            self.update()
            self.close_all_proxies()

        cb.activated.connect(lambda _: _commit())
        self._open_proxy(cb, QRectF(PADDING, fb_y + 2,
                                    w - self._RUN_BTN_W - PADDING * 2 - 6, fb_h - 4))
        cb.setFocus()
        cb.showPopup()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._resizing:
            delta = event.pos() - self._resize_start
            new_w = self._resize_w0
            new_h = self._resize_h0
            if self._resize_corner in ("br", "mr"):
                new_w = max(200.0, self._resize_w0 + delta.x())
            if self._resize_corner in ("br", "mb"):
                new_h = max(100.0, self._resize_h0 + delta.y())
            self.prepareGeometryChange()
            self._data["w"] = new_w
            self._data["h"] = new_h
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._resizing:
            self._resizing = False
            self.node_changed.emit(self)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _show_result_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel
        cols = self._data.get("result_cols", [])
        rows = self._data.get("result_rows", [])
        dlg = QDialog()
        dlg.setWindowTitle(self.label())
        dlg.resize(600, 400)
        lo = QVBoxLayout(dlg)
        if not cols:
            lo.addWidget(QLabel("Sem dados — execute o flow primeiro."))
        else:
            tbl = QTableWidget(len(rows), len(cols))
            tbl.setHorizontalHeaderLabels([str(c) for c in cols])
            for ri, row in enumerate(rows):
                for ci, col in enumerate(cols):
                    val = row.get(col, "") if isinstance(row, dict) else ""
                    tbl.setItem(ri, ci, QTableWidgetItem(str(val)))
            lo.addWidget(tbl)
        self._result_dialog = dlg
        dlg.show()


class WhereNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "where"
        self._data = {"operator": "AND", "conditions": []}
        # conditions: list of {"field": str, "op": str, "value": str, "value_is_field": bool}
        self._available_columns: list[dict] = []  # populated from upstream context

        # Fixed context ports
        _add_port(self, "in",  0, "in_ctx",  label="contexto", port_kind="context")
        _add_port(self, "out", 0, "out_ctx", label="filtrado",  port_kind="context")

        # Build initial condition ports (one open slot)
        self._rebuild_condition_ports()

        # React to incoming connections
        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "∿"
    def label(self): return "WHERE"

    def _rebuild_condition_ports(self):
        """Remove all condition ports and rebuild: one per condition + one open slot."""
        self.prepareGeometryChange()
        conditions = self._data.get("conditions", [])

        # Remove existing condition ports
        self.in_ports = [p for p in self.in_ports
                         if not (p.port_id.startswith("in_field_") or
                                 p.port_id.startswith("in_value_"))]

        # Re-add ports for each condition + one extra empty field slot
        n = len(conditions)
        for i in range(n + 1):
            _add_port(self, "in", 1 + i * 2,     f"in_field_{i}",
                      label="", port_kind="field")
            _add_port(self, "in", 1 + i * 2 + 1, f"in_value_{i}",
                      label="val", port_kind="field")

        self.update()

    def _on_port_connected(self, port_id: str):
        if port_id == "in_ctx":
            # Context connection: available columns will be set externally
            return

        if port_id.startswith("in_field_"):
            try:
                idx = int(port_id.split("_")[-1])
            except (ValueError, IndexError):
                return
            conditions = self._data.setdefault("conditions", [])
            while len(conditions) <= idx:
                conditions.append({"field": "", "op": "=", "value": "", "value_is_field": False})
            # If this is the last condition's field, add a new open slot
            if idx >= len(conditions) - 1:
                self._rebuild_condition_ports()

        elif port_id.startswith("in_value_"):
            try:
                idx = int(port_id.split("_")[-1])
            except (ValueError, IndexError):
                return
            conditions = self._data.setdefault("conditions", [])
            while len(conditions) <= idx:
                conditions.append({"field": "", "op": "=", "value": "", "value_is_field": False})
            conditions[idx]["value_is_field"] = True

    def rows(self):
        op = self._data.get("operator", "AND")
        rows = [("op", op)]
        for cond in self._data.get("conditions", []):
            field = cond.get("field", "")
            op_str = cond.get("op", "=")
            val = cond.get("value", "")
            rows.append((field, f"{op_str} {val}".strip()))
        return rows

    def get_ast(self):
        return {
            "type":       "where",
            "conditions": self._data.get("conditions", []),
            "operator":   self._data.get("operator", "AND"),
        }


class GroupByNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "group_by"
        self._data = {"fields": []}
        _add_port(self, "in",  0, "in")
        _add_port(self, "out", 0, "out")

    def icon(self):  return "≡"
    def label(self): return "GROUP BY"

    def rows(self):
        return [(f"[{i+1}]", f) for i, f in enumerate(self._data.get("fields", []))]

    def get_ast(self):
        return {"type": "group_by", "fields": self._data.get("fields", [])}


class HavingNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "having"
        self._data = {"conditions": [], "operator": "AND"}
        _add_port(self, "in",  0, "in")
        _add_port(self, "out", 0, "out")

    def icon(self):  return "▲"
    def label(self): return "HAVING"

    def rows(self):
        op = self._data.get("operator", "AND")
        rows = [("op", op)]
        for i, c in enumerate(self._data.get("conditions", [])):
            rows.append((f"[{i+1}]", c))
        return rows

    def get_ast(self):
        return {
            "type":       "having",
            "conditions": self._data.get("conditions", []),
            "operator":   self._data.get("operator", "AND"),
        }


class OrderByNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "order_by"
        self._data = {"fields": []}
        _add_port(self, "in",  0, "in")
        _add_port(self, "out", 0, "out")

    def icon(self):  return "↕"
    def label(self): return "ORDER BY"

    def rows(self):
        rows = []
        for entry in self._data.get("fields", []):
            if isinstance(entry, dict):
                rows.append((entry.get("name", ""), entry.get("direction", "ASC")))
            else:
                rows.append((str(entry), "ASC"))
        return rows

    def get_ast(self):
        return {"type": "order_by", "fields": self._data.get("fields", [])}


class LimitNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "limit"
        self._data = {"value": 100, "offset": 0}
        _add_port(self, "in",  0, "in")
        _add_port(self, "out", 0, "out")

    def icon(self):  return "#"
    def label(self): return "LIMIT"

    def rows(self):
        return [
            ("LIMIT",  self._data.get("value", 100)),
            ("OFFSET", self._data.get("offset", 0)),
        ]

    def get_ast(self):
        return {
            "type":   "limit",
            "value":  self._data.get("value", 100),
            "offset": self._data.get("offset", 0),
        }


class AggregateNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "aggregate"
        self._data = {"func": "COUNT", "field": "*", "alias": ""}
        _add_port(self, "in",  0, "in")
        _add_port(self, "out", 0, "out")

    def icon(self):  return "∑"
    def label(self): return "AGGREGATE"

    def rows(self):
        return [
            ("func",  self._data.get("func", "COUNT")),
            ("campo", self._data.get("field", "*")),
            ("alias", self._data.get("alias", "")),
        ]

    def get_ast(self):
        return {
            "type":  "aggregate",
            "func":  self._data.get("func", "COUNT"),
            "field": self._data.get("field", "*"),
            "alias": self._data.get("alias", ""),
        }


class CaseNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "case"
        self._data = {"whens": [], "else_value": "", "alias": ""}
        _add_port(self, "in",  0, "in")
        _add_port(self, "out", 0, "out")

    def icon(self):  return "?"
    def label(self): return "CASE / IF"

    def rows(self):
        rows = []
        for when in self._data.get("whens", []):
            rows.append((f"WHEN {when.get('when','')}", f"THEN {when.get('then','')}"))
        rows.append(("ELSE", self._data.get("else_value", "")))
        if self._data.get("alias"):
            rows.append(("AS", self._data["alias"]))
        return rows

    def get_ast(self):
        return {
            "type":       "case",
            "whens":      self._data.get("whens", []),
            "else_value": self._data.get("else_value", ""),
            "alias":      self._data.get("alias", ""),
        }


class ResultNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "result"
        self._data = {"row_count": None, "elapsed_ms": None}
        _add_port(self, "in", 0, "in")

    def icon(self):  return "✓"
    def label(self): return "RESULTADO"

    def rows(self):
        rc  = self._data.get("row_count")
        ela = self._data.get("elapsed_ms")
        return [
            ("linhas", rc if rc is not None else "—"),
            ("tempo",  f"{ela} ms" if ela is not None else "—"),
        ]

    def get_ast(self):
        return None

    def set_result(self, row_count: int, elapsed_ms: float):
        self._data["row_count"] = row_count
        self._data["elapsed_ms"] = round(elapsed_ms, 1)
        self.update()


# ─────────────────────────────────────────────────────────────────────────────
# FunctionNode
# ─────────────────────────────────────────────────────────────────────────────
_FUNC_NAMES = [
    "SUM", "COUNT", "AVG", "MAX", "MIN", "COALESCE", "CONCAT",
    "UPPER", "LOWER", "LENGTH", "ROUND", "CAST",
    "DATE_TRUNC", "EXTRACT", "NULLIF", "ISNULL",
]


class FunctionNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "function"
        self._header_bg_key = "func_header_bg"
        self._header_fg_key = "func_header_fg"
        self._data = {
            "mode":         "simple",
            "func":         "SUM",
            "formula":      "",
            "alias":        "",
            "input_fields": [],
        }

        _add_port(self, "in",  0, "in_ctx",    label="contexto", port_kind="context")
        _add_port(self, "out", 0, "out_field", label="SUM(...)",  port_kind="field")

        self._rebuild_input_ports()
        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "ƒ"
    def label(self): return "FUNÇÃO"

    def _out_label(self) -> str:
        alias = self._data.get("alias", "")
        if alias:
            return alias
        if self._data.get("mode") == "formula":
            return "expr"
        return self._data.get("func", "SUM") + "(...)"

    def _rebuild_input_ports(self):
        if self._data.get("mode") == "formula":
            # In formula mode remove all dynamic input ports
            self.in_ports = [p for p in self.in_ports
                             if not p.port_id.startswith("in_field_")]
            self.prepareGeometryChange()
            self.update()
            return

        self.prepareGeometryChange()
        self.in_ports = [p for p in self.in_ports
                         if not p.port_id.startswith("in_field_")]
        fields = self._data.get("input_fields", [])
        n = len(fields)
        for i in range(n + 1):
            _add_port(self, "in", i + 1, f"in_field_{i}",
                      label="", port_kind="field")
        # Update out_field label
        for p in self.out_ports:
            if p.port_id == "out_field":
                p.label = self._out_label()
        self.update()

    def _on_port_connected(self, port_id: str):
        if not port_id.startswith("in_field_"):
            return
        try:
            idx = int(port_id.split("_")[-1])
        except (ValueError, IndexError):
            return
        fields = self._data.setdefault("input_fields", [])
        while len(fields) <= idx:
            fields.append("")
        if idx >= len(fields) - 1:
            self._rebuild_input_ports()

    def rows(self):
        mode = self._data.get("mode", "simple")
        alias = self._data.get("alias", "")
        if mode == "formula":
            formula = self._data.get("formula", "")
            display = (formula[:30] + "…") if len(formula) > 30 else formula
            return [("formula", display), ("alias", alias)]
        func   = self._data.get("func", "SUM")
        fields = self._data.get("input_fields", [])
        result = [("func", func)]
        result += [(f"[{i}]", f) for i, f in enumerate(fields) if f]
        result.append(("alias", alias))
        return result

    def get_ast(self):
        mode  = self._data.get("mode", "simple")
        alias = self._data.get("alias", "")
        if mode == "formula":
            return {"type": "function", "formula": self._data.get("formula", ""), "alias": alias}
        return {
            "type":   "function",
            "func":   self._data.get("func", "SUM"),
            "fields": self._data.get("input_fields", []),
            "alias":  alias,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ProcedureNode
# ─────────────────────────────────────────────────────────────────────────────

class ProcedureNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "procedure"
        self._header_bg_key = "proc_header_bg"
        self._header_fg_key = "proc_header_fg"
        self._data = {
            "name":       "",
            "params_in":  [],   # [{"name": str, "type": str, "value": str}]
            "params_out": [],   # [{"name": str, "type": str}]
        }

    def icon(self):  return "⚙"
    def label(self): return "PROCEDURE"

    def set_procedure_schema(self, name: str, params_in: list, params_out: list):
        self._data["name"]       = name
        self._data["params_in"]  = list(params_in)
        self._data["params_out"] = list(params_out)
        self._build_ports_from_schema()
        self.prepareGeometryChange()
        self.update()

    def _build_ports_from_schema(self):
        self.in_ports  = []
        self.out_ports = []
        for i, p in enumerate(self._data.get("params_in", [])):
            _add_port(self, "in", i, f"in_{i}",
                      label=f"{p['name']} ({p['type']})", port_kind="field")
        for i, p in enumerate(self._data.get("params_out", [])):
            _add_port(self, "out", i, f"out_{i}",
                      label=f"{p['name']} ({p['type']})", port_kind="field")

    def rows(self):
        name      = self._data.get("name", "")
        p_in      = self._data.get("params_in",  [])
        p_out     = self._data.get("params_out", [])
        result    = [("proc", name)]
        result   += [(f"IN  {p['name']}", p.get("type","")) for p in p_in]
        result   += [(f"OUT {p['name']}", p.get("type","")) for p in p_out]
        return result

    def get_ast(self):
        return {
            "type":       "procedure",
            "name":       self._data.get("name", ""),
            "params_in":  self._data.get("params_in",  []),
            "params_out": self._data.get("params_out", []),
        }


# ─────────────────────────────────────────────────────────────────────────────
# UnionNode
# ─────────────────────────────────────────────────────────────────────────────

class UnionNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "union"
        self._header_bg_key = "union_header_bg"
        self._header_fg_key = "union_header_fg"
        self._data = {"union_type": "UNION", "input_count": 2}

        _add_port(self, "out", 0, "out_ctx", label="unido", port_kind="context")
        self._rebuild_union_ports()
        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "⊔"
    def label(self): return "UNION"

    def _rebuild_union_ports(self):
        self.prepareGeometryChange()
        n = self._data.get("input_count", 2)
        self.in_ports = []
        for i in range(n + 1):   # n connected + 1 open slot
            _add_port(self, "in", i, f"in_{i}",
                      label=f"query {i + 1}", port_kind="context")
        self.update()

    def _on_port_connected(self, port_id: str):
        if not port_id.startswith("in_"):
            return
        try:
            idx = int(port_id.split("_")[-1])
        except (ValueError, IndexError):
            return
        n = self._data.get("input_count", 2)
        # If the last "open slot" was just connected, expand
        if idx >= n:
            self._data["input_count"] = idx + 1
            self._rebuild_union_ports()

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = OK)."""
        # Check if connected upstream contexts have different column counts
        # (requires canvas-level wiring not available on the node itself—
        #  this is a hint for the flow executor to check)
        return []

    def rows(self):
        n = self._data.get("input_count", 2)
        return [
            ("tipo",    self._data.get("union_type", "UNION")),
            (f"{n} entradas", ""),
        ]

    def get_ast(self):
        return {
            "type":        "union",
            "union_type":  self._data.get("union_type", "UNION"),
            "input_count": self._data.get("input_count", 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# UpdateNode
# ─────────────────────────────────────────────────────────────────────────────

class UpdateNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "update"
        self._header_bg_key = "update_header_bg"
        self._header_fg_key = "update_header_fg"
        self._data = {"sets": [], "confirm": False}
        # sets: list of {"col": str, "val": str, "val_is_field": bool}

        _add_port(self, "in",  0, "in_ctx",  label="contexto",   port_kind="context")
        _add_port(self, "out", 0, "out_ctx", label="atualizado",  port_kind="context")

        self._rebuild_set_ports()
        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "✎"
    def label(self): return "UPDATE"

    def _rebuild_set_ports(self):
        self.prepareGeometryChange()
        sets = self._data.get("sets", [])
        self.in_ports = [p for p in self.in_ports
                         if not p.port_id.startswith("in_set_")]
        for i, s in enumerate(sets):
            col = s.get("col", "")
            lbl = f"SET {col}" if col else f"SET [{i}]"
            _add_port(self, "in", 1 + i, f"in_set_{i}",
                      label=lbl, port_kind="field")
        # Always one open slot at end
        n = len(sets)
        _add_port(self, "in", 1 + n, f"in_set_{n}",
                  label="SET (novo)", port_kind="field")
        self.update()

    def _on_port_connected(self, port_id: str):
        if not port_id.startswith("in_set_"):
            return
        try:
            idx = int(port_id.split("_")[-1])
        except (ValueError, IndexError):
            return
        sets = self._data.setdefault("sets", [])
        while len(sets) <= idx:
            sets.append({"col": "", "val": "", "val_is_field": False})
        self._rebuild_set_ports()

    def _on_field_port_connected(self, port_id: str, from_port: "Port"):
        """Called by AddConnectionCommand to supply the from_port object."""
        if not port_id.startswith("in_set_"):
            return
        try:
            idx = int(port_id.split("_")[-1])
        except (ValueError, IndexError):
            return
        sets = self._data.setdefault("sets", [])
        while len(sets) <= idx:
            sets.append({"col": "", "val": "", "val_is_field": False})
        if from_port.label:
            sets[idx]["col"] = from_port.label
        self._rebuild_set_ports()

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self._data.get("confirm"):
            errors.append("confirme antes de executar")
        for i, s in enumerate(self._data.get("sets", [])):
            if not s.get("col"):
                errors.append(f"coluna vazia no SET {i}")
        return errors

    def rows(self):
        confirm = self._data.get("confirm", False)
        result = [("confirmar", "✓" if confirm else "✗")]
        for s in self._data.get("sets", []):
            if s.get("col"):
                result.append((f"SET {s['col']}", f"= {s.get('val', '')}"))
        return result

    def get_ast(self):
        return {
            "type":    "update",
            "sets":    self._data.get("sets", []),
            "confirm": self._data.get("confirm", False),
        }


# ─────────────────────────────────────────────────────────────────────────────
# DeleteNode
# ─────────────────────────────────────────────────────────────────────────────

class DeleteNode(BaseNode):
    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "delete"
        self._header_bg_key = "delete_header_bg"
        self._header_fg_key = "delete_header_fg"
        self._data = {"confirm": False}

        _add_port(self, "in",  0, "in_ctx",  label="contexto", port_kind="context")
        _add_port(self, "out", 0, "out_ctx", label="deletado",  port_kind="context")

    def icon(self):  return "✕"
    def label(self): return "DELETE"

    def validate(self) -> list[str]:
        if not self._data.get("confirm"):
            return ["confirme antes de executar"]
        return []

    def rows(self):
        confirm = self._data.get("confirm", False)
        return [
            ("confirmar", "✓" if confirm else "✗"),
            ("ATENÇÃO",   "irreversível"),
        ]

    def get_ast(self):
        return {
            "type":    "delete",
            "confirm": self._data.get("confirm", False),
        }


# ── Factory ───────────────────────────────────────────────────────────────────
_NODE_REGISTRY: dict[str, type] = {    "table":     TableNode,
    "join":      JoinNode,
    "select":    SelectNode,
    "where":     WhereNode,
    "group_by":  GroupByNode,
    "having":    HavingNode,
    "order_by":  OrderByNode,
    "limit":     LimitNode,
    "aggregate": AggregateNode,
    "case":      CaseNode,
    "result":    ResultNode,
    "function":  FunctionNode,
    "procedure": ProcedureNode,
    "union":     UnionNode,
    "update":    UpdateNode,
    "delete":    DeleteNode,
}


def create_node(node_type: str, node_id: str = "") -> BaseNode:
    cls = _NODE_REGISTRY.get(node_type, BaseNode)
    return cls(node_id=node_id)


def node_from_dict(data: dict) -> BaseNode:
    """Deserialise a node from its saved dict."""
    node = create_node(data.get("type", ""), data.get("id", ""))
    node._data = dict(data.get("data", {}))
    node.setPos(data.get("x", 0), data.get("y", 0))
    return node
