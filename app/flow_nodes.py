from __future__ import annotations
"""
flow_nodes.py — All node types for the FlowSQL visual query builder.

Every node is a QGraphicsItem drawn purely with QPainter (no child widgets
on the canvas itself). Interactive editing happens in the Properties panel.
"""

import uuid
from enum import Enum
from typing import Optional

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath,
)
from PyQt5.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneMouseEvent, QGraphicsSceneContextMenuEvent,
    QGraphicsProxyWidget,
    QComboBox, QLineEdit, QTextEdit, QHBoxLayout, QApplication, QMenu,
)

# ── ThemeColors: typed constants for all palette entries ──────────────────────
class ThemeColors(str, Enum):
    """Strongly-typed keys for the _THEME palette.

    Each member's value is the key used inside ``_THEME``.  This allows
    IDE auto-complete and avoids bare string literals scattered across the
    codebase.
    """
    BODY_BG         = "body_bg"
    BODY_BORDER     = "body_border"
    HEADER_BG       = "header_bg"
    HEADER_FG       = "header_fg"
    SEL_BORDER      = "sel_border"
    SEL_HEADER      = "sel_header"
    ICON_COLOR      = "icon_color"
    LABEL_FG        = "label_fg"
    VALUE_FG        = "value_fg"
    TYPE_FG         = "type_fg"
    PORT_BORDER     = "port_border"
    PORT_FILL       = "port_fill"
    PORT_CONN       = "port_conn"
    CONN_LINE       = "conn_line"
    FUNC_HEADER_BG  = "func_header_bg"
    FUNC_HEADER_FG  = "func_header_fg"
    PROC_HEADER_BG  = "proc_header_bg"
    PROC_HEADER_FG  = "proc_header_fg"
    UNION_HEADER_BG = "union_header_bg"
    UNION_HEADER_FG = "union_header_fg"
    UPDATE_HEADER_BG = "update_header_bg"
    UPDATE_HEADER_FG = "update_header_fg"
    DELETE_HEADER_BG = "delete_header_bg"
    DELETE_HEADER_FG = "delete_header_fg"
    # NoteNode
    NOTE_HEADER_BG  = "note_header_bg"
    NOTE_HEADER_FG  = "note_header_fg"
    NOTE_BODY_BG    = "note_body_bg"
    NOTE_BODY_FG    = "note_body_fg"
    # GroupNode
    GROUP_HEADER_BG = "group_header_bg"
    GROUP_HEADER_FG = "group_header_fg"
    GROUP_BODY_BG   = "group_body_bg"
    GROUP_BORDER    = "group_border"
    # High-contrast overrides (applied when theme == "high-contrast")
    HC_BODY_BG      = "hc_body_bg"
    HC_BODY_BORDER  = "hc_body_border"
    HC_HEADER_FG    = "hc_header_fg"

    def __str__(self) -> str:   # allow direct use as dict key
        return self.value


def tc(key: "ThemeColors | str") -> str:
    """Resolve a ThemeColors member (or plain string) to the ``_THEME`` value."""
    k = str(key)
    return _THEME.get(k, "#ff00ff")   # magenta fallback makes missing keys obvious


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
    # NoteNode
    "note_header_bg": "#78716c",
    "note_header_fg": "#fef3c7",
    "note_body_bg":   "#fef3c7",
    "note_body_fg":   "#292524",
    # GroupNode
    "group_header_bg": "#1e293b",
    "group_header_fg": "#94a3b8",
    "group_body_bg":   "#1e293b",
    "group_border":    "#334155",
    # High-contrast (only populated on "high-contrast" theme)
    "hc_body_bg":     "",
    "hc_body_border": "",
    "hc_header_fg":   "",
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
            # NoteNode
            "note_header_bg": "#78716c",
            "note_header_fg": "#fef3c7",
            "note_body_bg":   "#fef3c7",
            "note_body_fg":   "#292524",
            # GroupNode
            "group_header_bg": "#1e293b",
            "group_header_fg": "#94a3b8",
            "group_body_bg":   "#1e293b",
            "group_border":    "#334155",
            # High-contrast
            "hc_body_bg":     "",
            "hc_body_border": "",
            "hc_header_fg":   "",
        })
    elif theme == "high-contrast":
        _THEME.update({
            "body_bg":    "#000000",
            "body_border": "#ffffff",
            "header_bg":  "#000000",
            "header_fg":  "#ffffff",
            "sel_border": "#ffff00",
            "sel_header": "#003366",
            "icon_color": "#ffffff",
            "label_fg":   "#ffffff",
            "value_fg":   "#ffffff",
            "type_fg":    "#aaaaaa",
            "port_border": "#ffffff",
            "port_fill":  "#000000",
            "port_conn":  "#00ff00",
            "conn_line":  "#ffffff",
            "func_header_bg":  "#000000",
            "func_header_fg":  "#00ff88",
            "proc_header_bg":  "#000000",
            "proc_header_fg":  "#aaaaff",
            "union_header_bg": "#000000",
            "union_header_fg": "#88bbff",
            "update_header_bg": "#000000",
            "update_header_fg": "#ffaa44",
            "delete_header_bg": "#000000",
            "delete_header_fg": "#ff4444",
            "note_header_bg":  "#333300",
            "note_header_fg":  "#ffff00",
            "note_body_bg":    "#111100",
            "note_body_fg":    "#ffff88",
            "group_header_bg": "#001133",
            "group_header_fg": "#88aaff",
            "group_body_bg":   "#000011",
            "group_border":    "#4488ff",
            "hc_body_bg":      "#000000",
            "hc_body_border":  "#ffffff",
            "hc_header_fg":    "#ffffff",
        })
    else:  # light
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
            # NoteNode
            "note_header_bg": "#d6b47c",
            "note_header_fg": "#292524",
            "note_body_bg":   "#fef3c7",
            "note_body_fg":   "#292524",
            # GroupNode
            "group_header_bg": "#e2e8f0",
            "group_header_fg": "#334155",
            "group_body_bg":   "#f8fafc",
            "group_border":    "#94a3b8",
            # High-contrast (empty in light mode)
            "hc_body_bg":     "",
            "hc_body_border": "",
            "hc_header_fg":   "",
        })


# ── Dimensions ────────────────────────────────────────────────────────────────
NODE_WIDTH    = 220
HEADER_H      = 28
ROW_H         = 22
PORT_R        = 5       # radius
PORT_D        = PORT_R * 2
PADDING       = 10
SEARCH_BAR_H  = 24     # TableNode inline column-filter bar

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
        self._hovered_port: Optional[Port] = None   # port under mouse cursor
        self._drop_target_port: Optional[Port] = None  # highlighted while dragging
        self._highlighted_ports: set[Port] = set()  # all compatible ports (canvas-managed)
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
            QRectF(PADDING + 22, 0, NODE_WIDTH - PADDING * 2 - 22 - 16, HEADER_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.label(),
        )

        # ─ Validation badge ───────────────────────────────────────────────
        self._draw_header_badge(painter)

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

            # ─ Compatible-port halo (canvas-managed, all droppable targets) ──
            if port in self._highlighted_ports:
                halo = QColor(_THEME["port_conn"])
                halo.setAlphaF(0.5)
                painter.setPen(Qt.NoPen)
                painter.setBrush(halo)
                painter.drawEllipse(local_pos, PORT_R + 6, PORT_R + 6)

            # ─ Drop-target ring (bright green, drawn first) ───────────────
            if port is self._drop_target_port:
                ring = QColor("#22c55e")
                ring.setAlphaF(0.9)
                painter.setPen(QPen(ring, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(local_pos, PORT_R + 5, PORT_R + 5)

            # ─ Hover glow ─────────────────────────────────────────────────
            if port is self._hovered_port:
                glow = QColor(_THEME["port_conn"])
                glow.setAlphaF(0.3)
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(local_pos, PORT_R + 4, PORT_R + 4)

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

    def hoverMoveEvent(self, event):
        new_port = self.port_at(event.pos())
        if new_port is not self._hovered_port:
            self._hovered_port = new_port
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        if self._hovered_port is not None:
            self._hovered_port = None
            self.update()
        super().hoverLeaveEvent(event)

    # ── Validation ────────────────────────────────────────────────────────────
    def validate(self) -> Optional[list[str]]:
        """Return list of errors (empty = valid), or None if not implemented."""
        return None

    def validate_warnings(self) -> list[str]:
        """Return list of non-blocking warnings."""
        return []

    def _badge_color(self) -> QColor:
        """Determine badge color from validation state."""
        errors = self.validate()
        if errors is None:
            return QColor("#9ca3af")   # gray  – not implemented
        if errors:
            return QColor("#ef4444")   # red   – blocking errors
        if self.validate_warnings():
            return QColor("#eab308")   # yellow – only warnings
        return QColor("#22c55e")       # green  – all good

    def _draw_header_badge(self, painter: QPainter, header_w: float = NODE_WIDTH):
        """Draw 8 px validation-state badge at top-right of header."""
        color = self._badge_color()
        cx = header_w - PADDING - 4.0
        cy = HEADER_H / 2.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(cx, cy), 4.0, 4.0)

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
        self._column_filter: str = ""          # live column-search text

        # Context port — placed at header level via _port_local override
        _add_port(self, "out", 0, "out_ctx",
                  label="⬡ contexto", port_kind="context")

    def icon(self):  return "▦"
    def label(self): return "TABLE"

    def rows(self):
        return []   # paint() handles the column list directly

    # ── Validation ────────────────────────────────────────────────────────────
    def validate(self) -> list[str]:
        if not self._data.get("name", "").strip():
            return ["nome da tabela não definido"]
        return []

    # ── Schema / port management ──────────────────────────────────────────────
    def set_schema_columns(self, columns: list[dict]):
        """Called when schema info is available. Rebuilds field ports."""
        self._columns = list(columns)
        self._rebuild_field_ports(self._column_filter)

    def _rebuild_field_ports(self, filter_text: str = ""):
        """Remove all field ports and rebuild, applying *filter_text* as a
        case-insensitive substring filter over column names."""
        self.prepareGeometryChange()
        self.out_ports = [p for p in self.out_ports if p.port_id == "out_ctx"]
        ft = filter_text.lower().strip()
        visible = [col for col in self._columns
                   if not ft or ft in col.get("name", "").lower()]
        for row_idx, col in enumerate(visible):
            col_name = col.get("name", "")
            col_type = col.get("type", "")
            # Stable port ID uses original column index for serialisation compat
            orig_idx = self._columns.index(col)
            _add_field_port(self, "out", col_name, col_type, row_idx,
                            pid=f"out_field_{orig_idx}")
        self.update()

    # ── Geometry ──────────────────────────────────────────────────────────────
    def _body_height(self) -> float:
        n_field = len([p for p in self.out_ports if p.port_id != "out_ctx"])
        n = max(n_field, 1)
        indicator = ROW_H if (self._column_filter and self._columns) else 0
        return HEADER_H + SEARCH_BAR_H + PADDING + n * ROW_H + indicator + PADDING

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_WIDTH, self._body_height())

    # ── Port positions ────────────────────────────────────────────────────────
    def _port_local(self, port: Port) -> QPointF:
        if port.port_id == "out_ctx":
            return QPointF(NODE_WIDTH, HEADER_H / 2)
        # Field ports: 0-based row below the search bar
        y = HEADER_H + SEARCH_BAR_H + PADDING + port.row * ROW_H + ROW_H / 2
        return QPointF(NODE_WIDTH, y)

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        rect = self.boundingRect()
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

        # Header background
        header_path = QPainterPath()
        header_path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, HEADER_H), 4, 4)
        header_path.addRect(QRectF(0, HEADER_H / 2, NODE_WIDTH, HEADER_H / 2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_THEME["sel_header"] if selected
                                else _THEME[self._header_bg_key]))
        painter.drawPath(header_path)

        # Icon
        painter.setFont(_ICON_FONT)
        painter.setPen(QColor(_THEME["icon_color"]))
        painter.drawText(QRectF(PADDING, 0, 22, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.icon())

        # Header label (narrowed to leave room for the badge)
        painter.setFont(_HEADER_FONT)
        header_fg = _THEME[self._header_fg_key] if not selected else _THEME["header_fg"]
        painter.setPen(QColor(header_fg))
        painter.drawText(
            QRectF(PADDING + 22, 0, NODE_WIDTH - PADDING * 2 - 22 - 16, HEADER_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.label(),
        )

        # Validation badge
        self._draw_header_badge(painter)

        # ── Search bar ────────────────────────────────────────────────────
        sb_y = float(HEADER_H)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_THEME["header_bg"]))
        painter.drawRect(QRectF(0, sb_y, NODE_WIDTH, SEARCH_BAR_H))

        # Separator lines (top and bottom of search bar)
        painter.setPen(QPen(QColor(_THEME["body_border"]), 1))
        painter.drawLine(QPointF(0, sb_y), QPointF(NODE_WIDTH, sb_y))
        painter.drawLine(QPointF(0, sb_y + SEARCH_BAR_H),
                         QPointF(NODE_WIDTH, sb_y + SEARCH_BAR_H))

        # Magnifying-glass icon
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(_THEME["icon_color"]))
        painter.drawText(QRectF(PADDING, sb_y, 18, SEARCH_BAR_H),
                         Qt.AlignVCenter | Qt.AlignLeft, "⌕")

        # Filter text or greyed-out placeholder
        painter.setFont(_LABEL_FONT)
        if self._column_filter:
            painter.setPen(QColor(_THEME["value_fg"]))
            display_text = self._column_filter
        else:
            painter.setPen(QColor(_THEME["type_fg"]))
            display_text = "Filtrar colunas..."
        painter.drawText(
            QRectF(PADDING + 20, sb_y, NODE_WIDTH - PADDING * 2 - 20, SEARCH_BAR_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            display_text,
        )

        # ── Column port type labels ───────────────────────────────────────
        for port in self.out_ports:
            if port.port_id == "out_ctx":
                continue
            lp = self._port_local(port)
            # Column name (from port label, rendered right-of the port dot)
            painter.setFont(_LABEL_FONT)
            painter.setPen(QColor(_THEME["label_fg"]))
            name_rect = QRectF(PORT_R + 4, lp.y() - ROW_H / 2,
                               NODE_WIDTH - PORT_R - 4 - PADDING - 2, ROW_H)
            painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, port.label)

            # SQL type (greyed out, right-aligned)
            if port.col_type:
                painter.setPen(QColor(_THEME["type_fg"]))
                type_rect = QRectF(PADDING, lp.y() - ROW_H / 2,
                                   NODE_WIDTH - PADDING - PORT_R - 6, ROW_H)
                fm = QFontMetrics(_LABEL_FONT)
                painter.drawText(type_rect, Qt.AlignVCenter | Qt.AlignRight,
                                 fm.elidedText(port.col_type, Qt.ElideRight,
                                               int(type_rect.width() // 2)))

        # ── "X of Y columns" indicator (only when filter is active) ──────
        if self._column_filter and self._columns:
            n_visible = len([p for p in self.out_ports if p.port_id != "out_ctx"])
            n_total   = len(self._columns)
            body_top  = HEADER_H + SEARCH_BAR_H + PADDING
            ind_y = body_top + max(n_visible, 1) * ROW_H + PADDING / 4
            painter.setFont(_LABEL_FONT)
            painter.setPen(QColor(_THEME["type_fg"]))
            painter.drawText(
                QRectF(PADDING, ind_y, NODE_WIDTH - PADDING * 2, ROW_H),
                Qt.AlignVCenter | Qt.AlignHCenter,
                f"Mostrando {n_visible} de {n_total} colunas",
            )

        # Ports (glow handled inside _paint_ports)
        self._paint_ports(painter)

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        # Search bar area → open column-filter editor
        if HEADER_H <= local.y() <= HEADER_H + SEARCH_BAR_H:
            self._open_search_editor()
            event.accept()
            return
        # Body below search bar → edit table name
        if local.y() > HEADER_H + SEARCH_BAR_H:
            self._open_name_editor()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _open_search_editor(self):
        """Embed a QLineEdit inside the search bar for real-time column filtering."""
        self.close_all_proxies()
        le = QLineEdit()
        le.setText(self._column_filter)
        le.setPlaceholderText("Filtrar colunas...")
        le.selectAll()

        def _apply(text: str):
            self._column_filter = text.strip()
            self._rebuild_field_ports(self._column_filter)

        def _commit():
            _apply(le.text())
            self.close_all_proxies()

        le.textChanged.connect(_apply)
        le.returnPressed.connect(_commit)
        le.editingFinished.connect(lambda: (_commit() if self._proxies else None))
        self._open_proxy(
            le,
            QRectF(PADDING + 18, HEADER_H + 2,
                   NODE_WIDTH - PADDING * 2 - 18, SEARCH_BAR_H - 4),
        )
        le.setFocus()

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
        body_top = HEADER_H + SEARCH_BAR_H + PADDING
        self._open_proxy(le, QRectF(PADDING, body_top, NODE_WIDTH - PADDING * 2, ROW_H))
        le.setFocus()

    # ── Serialisation ─────────────────────────────────────────────────────────
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

        # Resolve key flags from source node's column metadata
        is_pk = False
        is_fk = False
        source_cols: list[dict] = getattr(from_port.node, "_columns", [])
        for src_col in source_cols:
            if src_col.get("name") == col_name:
                is_pk = bool(src_col.get("pk", False))
                is_fk = bool(src_col.get("fk", False))
                break

        if port_id.startswith("in_left_"):
            pairs[idx]["left_field"]  = qualified
            pairs[idx]["left_is_pk"]  = is_pk
            pairs[idx]["left_is_fk"]  = is_fk
            # Infere left_table do primeiro campo esq. se ainda não definida
            if table_name and not self._data.get("left_table"):
                self._data["left_table"] = table_name
        else:
            pairs[idx]["right_field"] = qualified
            pairs[idx]["right_is_pk"] = is_pk
            pairs[idx]["right_is_fk"] = is_fk
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
        painter.drawText(QRectF(PADDING + 22, 0, NODE_WIDTH - PADDING * 2 - 22 - 16, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.label())

        # Validation badge
        self._draw_header_badge(painter)

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

            # Key-icon widths (shown when the flag is set)
            key_font = QFont("Segoe UI", 8)
            km_left = QFontMetrics(key_font)
            pk_icon_w = km_left.horizontalAdvance("🔑") + 2
            fk_icon_w = km_left.horizontalAdvance("🔗") + 2

            def _draw_field_row(lbl: str, is_pk: bool, is_fk: bool,
                                row_x: float, row_y: float, row_w: float, row_h: float):
                icon_x = row_x
                if is_pk:
                    painter.setFont(key_font)
                    painter.setPen(QColor("#eab308"))   # gold
                    painter.drawText(QRectF(icon_x, row_y, pk_icon_w, row_h),
                                     Qt.AlignVCenter | Qt.AlignLeft, "🔑")
                    icon_x += pk_icon_w
                if is_fk:
                    painter.setFont(key_font)
                    painter.setPen(QColor("#60a5fa"))   # blue
                    painter.drawText(QRectF(icon_x, row_y, fk_icon_w, row_h),
                                     Qt.AlignVCenter | Qt.AlignLeft, "🔗")
                    icon_x += fk_icon_w
                avail = row_w - (icon_x - row_x)
                painter.setFont(_LABEL_FONT)
                painter.setPen(QColor(_THEME["value_fg"]))
                painter.drawText(QRectF(icon_x, row_y, max(0.0, avail), row_h),
                                 Qt.AlignVCenter | Qt.AlignLeft,
                                 fm.elidedText(lbl, Qt.ElideRight, int(max(0.0, avail))))

            text_x = PADDING + PORT_R + 6
            text_w = NODE_WIDTH - PADDING * 2 - op_w - PORT_R * 2 - 12

            # Left field (top sub-row)
            _draw_field_row(lf,
                            pair.get("left_is_pk", False),
                            pair.get("left_is_fk", False),
                            text_x, cy, text_w, rh)

            # Right field (bottom sub-row)
            _draw_field_row(rf,
                            pair.get("right_is_pk", False),
                            pair.get("right_is_fk", False),
                            text_x, cy + rh, text_w, rh)

            # Op badge — styled as a dropdown (border + arrow)
            op_x    = NODE_WIDTH - PADDING - op_w
            op_rect = QRectF(op_x, cy + 4, op_w, self._CARD_H - self._CARD_PAD - 8)
            # Border + slight background
            painter.setBrush(QColor(_THEME["body_bg"]))
            painter.setPen(QPen(op_color, 1))
            painter.drawRoundedRect(op_rect, 3, 3)
            # Op text (left portion)
            arrow_w  = 12
            text_rect  = QRectF(op_rect.x() + 4, op_rect.y(),
                                op_rect.width() - arrow_w - 4, op_rect.height())
            arrow_rect = QRectF(op_rect.right() - arrow_w, op_rect.y(),
                                arrow_w, op_rect.height())
            painter.setFont(QFont("Consolas", 8, QFont.Bold))
            painter.setPen(op_color)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, op)
            # Dropdown chevron
            painter.setFont(QFont("Segoe UI", 7))
            painter.setPen(QColor(_THEME["label_fg"]))
            painter.drawText(arrow_rect, Qt.AlignCenter, "▾")

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

    def validate(self) -> list[str]:
        errors: list[str] = []
        for i, pair in enumerate(self._data.get("pairs", [])):
            lf = pair.get("left_field", "")
            rf = pair.get("right_field", "")
            if bool(lf) != bool(rf):
                missing = "esq." if rf and not lf else "dir."
                errors.append(f"par {i + 1}: campo {missing} vazio")
        return errors

    def validate_warnings(self) -> list[str]:
        if self._data.get("join_type") == "CROSS":
            return []   # CROSS JOIN doesn't need an ON clause
        has_pair = any(
            p.get("left_field") and p.get("right_field")
            for p in self._data.get("pairs", [])
        )
        if not has_pair:
            return ["sem cláusula ON definida"]
        return []

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
            "pinned":       False,     # 1.5 – pin: suppress auto-expand
        }
        self._available_columns: list[dict] = []
        self._result_dialog = None   # keep reference to prevent GC

        # Resize state
        self._resizing:      bool    = False
        self._resize_corner: str     = ""   # "br" | "mr" | "mb"
        self._resize_start:  QPointF = QPointF()
        self._resize_w0:     float   = 240.0
        self._resize_h0:     float   = 140.0

        # 1.5 – virtual scroll
        self._scroll_offset:   int = 0       # first visible data row index (vertical)
        self._h_scroll_offset: int = 0       # first visible column index (horizontal)

        # 1.6 – pulse animation
        self._pulse_opacity: float = 0.0
        self._pulse_step:    int   = 0     # direction: +1 fade-in, -1 fade-out
        self._pulse_timer:   QTimer = QTimer()
        self._pulse_timer.setInterval(16)  # ~60 fps
        self._pulse_timer.timeout.connect(self._tick_pulse)

        _add_port(self, "in",  0, "in_ctx",  label="entrada", port_kind="context")
        _add_port(self, "out", 0, "out_ctx", label="saída",   port_kind="context")

        self.port_connected.connect(self._on_port_connected)

    def icon(self):  return "◻"
    def label(self): return "SELECT / RESULTADO"

    def _on_port_connected(self, port_id: str):
        pass  # available columns set externally via _available_columns

    def set_result(self, cols: list, rows: list):
        # Auto-expand height only when not pinned
        if cols and not self._data.get("pinned", False):
            content_top = HEADER_H + self._FILTER_BAR_H + PADDING
            field_rows_h = len(self._data.get("fields", [])) * ROW_H + PADDING
            max_show = min(len(rows), 10) if rows else 1
            min_h = content_top + field_rows_h + PADDING + 18 + max_show * 18 + PADDING
            if self._data.get("h", 160) < min_h:
                self._data["h"] = float(min_h)
        self.prepareGeometryChange()
        self._data["result_cols"] = list(cols)
        self._data["result_rows"] = list(rows)
        self._scroll_offset   = 0   # reset scroll on new data
        self._h_scroll_offset = 0
        self.update()
        if self.scene():
            self.scene().update(self.sceneBoundingRect())

    def rows(self):
        # distinct / filtro already shown in filter bar — only list explicit columns
        result = []
        for f in self._data.get("fields", []):
            result.append(("col", f))
        return result

    def validate(self) -> list[str]:
        return []   # SELECT is always structurally valid

    def get_ast(self):
        return {
            "type":         "select",
            "fields":       self._data.get("fields", []),
            "distinct":     self._data.get("distinct", False),
            "quick_filter": self._data.get("quick_filter", "nenhum"),
        }

    # ── Pulse animation helpers ────────────────────────────────────────────────
    def _tick_pulse(self):
        """Advance the pulse opacity by one frame (called by QTimer ~60 fps)."""
        step = 0.08   # opacity delta per frame (300 ms / 16 ms ≈ 19 frames)
        if self._pulse_step > 0:
            self._pulse_opacity = min(1.0, self._pulse_opacity + step)
            if self._pulse_opacity >= 1.0:
                self._pulse_step = -1
        else:
            self._pulse_opacity = max(0.0, self._pulse_opacity - step)
            if self._pulse_opacity <= 0.0:
                self._pulse_timer.stop()
                self._pulse_opacity = 0.0
        self.update()

    def _start_pulse(self):
        self._pulse_opacity = 0.0
        self._pulse_step    = 1
        if not self._pulse_timer.isActive():
            self._pulse_timer.start()

    # ── Pin / scroll geometry helpers ─────────────────────────────────────────
    def _pin_rect(self, w: float, result_top: float) -> QRectF:
        """Small 16×16 clickable pin icon area inside the result panel."""
        return QRectF(w - PADDING - 16, result_top + 2, 16, 16)

    def _scrollbar_rect(self, w: float, table_top: float, table_h: float) -> QRectF:
        """Thin 6-px vertical scrollbar on the right edge of the result area."""
        return QRectF(w - PADDING - 6, table_top, 6, table_h)

    def _h_scrollbar_rect(self, w: float, bottom: float) -> QRectF:
        """Thin 6-px horizontal scrollbar along the bottom of the result area."""
        return QRectF(PADDING, bottom - 8, w - PADDING * 2, 6)

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
        painter.drawText(QRectF(PADDING + 22, 0, w - PADDING * 2 - 22 - 16, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.label())

        # Validation badge
        self._draw_header_badge(painter, w)

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

        # Filter dropdown area — bordered box with chevron
        qf = self._data.get("quick_filter", "nenhum")
        qf_text = qf if qf != "nenhum" else "sem filtro"
        dd_x = PADDING
        dd_w = w - PADDING * 2 - self._RUN_BTN_W - 6
        dd_rect = QRectF(dd_x, fb_y + 3, dd_w, fb_h - 6)
        painter.setPen(QPen(QColor(_THEME["body_border"]), 1))
        painter.setBrush(QColor(_THEME["body_bg"]))
        painter.drawRoundedRect(dd_rect, 3, 3)
        # Chevron on the right
        chev_w = 16
        painter.setFont(QFont("Segoe UI", 7))
        painter.setPen(QColor(_THEME["label_fg"]))
        painter.drawText(QRectF(dd_x + dd_w - chev_w, fb_y + 3, chev_w, fb_h - 6),
                         Qt.AlignCenter, "▾")
        # Label text
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor(_THEME["value_fg"]))
        painter.drawText(QRectF(dd_x + 5, fb_y + 3, dd_w - chev_w - 6, fb_h - 6),
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
        pinned      = self._data.get("pinned", False)

        # Placeholder when no results yet
        if not result_cols:
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor(_THEME["label_fg"]))
            painter.drawText(
                QRectF(PADDING, body_rows_h, w - PADDING * 2, h - body_rows_h - PADDING),
                Qt.AlignTop | Qt.AlignHCenter,
                "▶ execute para ver resultados",
            )

        if result_cols and h > body_rows_h + 20:
            table_y   = body_rows_h
            row_h_px  = 18
            # Reserve 8px at bottom for horizontal scrollbar when needed
            h_sb_reserve = 8
            table_h   = h - table_y - PADDING - h_sb_reserve
            # virtual scroll: how many data rows fit (excluding header row)
            max_data_rows = max(0, int((table_h - row_h_px) // row_h_px))
            total_rows    = len(result_rows)
            total_cols    = len(result_cols)
            # clamp scroll offsets
            max_v_offset = max(0, total_rows - max_data_rows)
            self._scroll_offset = max(0, min(self._scroll_offset, max_v_offset))
            scroll_offset = self._scroll_offset

            sb_w = 6   # vertical scrollbar width
            has_v_sb = total_rows > max_data_rows and max_data_rows > 0

            # Fixed column width — each col is MIN_COL_W wide so that horizontal
            # scroll becomes useful when there are many columns
            MIN_COL_W = 70
            col_w     = MIN_COL_W
            # How many columns fit in the visible area
            v_sb_space = sb_w + 2 if has_v_sb else 0
            visible_area_w = w - PADDING * 2 - v_sb_space
            max_vis_cols   = max(1, int(visible_area_w // col_w))
            max_h_offset   = max(0, total_cols - max_vis_cols)
            self._h_scroll_offset = max(0, min(self._h_scroll_offset, max_h_offset))
            h_scroll_offset = self._h_scroll_offset
            has_h_sb = total_cols > max_vis_cols

            visible_cols = result_cols[h_scroll_offset: h_scroll_offset + max_vis_cols]

            col_area_w = w - PADDING * 2 - v_sb_space

            # ── Pin button ────────────────────────────────────────────────
            pin_rect = self._pin_rect(w, table_y)
            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor(_THEME["label_fg"]))
            painter.setBrush(Qt.NoBrush)
            painter.drawText(pin_rect, Qt.AlignCenter, "📌" if pinned else "⊙")

            # ── Column header row ─────────────────────────────────────────
            painter.setFont(_VALUE_FONT)
            painter.setBrush(QColor(_THEME["header_bg"]))
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(PADDING, table_y, col_area_w, row_h_px))
            painter.setPen(QColor(_THEME["label_fg"]))
            fm_v = QFontMetrics(_VALUE_FONT)
            for ci, col in enumerate(visible_cols):
                cx = PADDING + ci * col_w
                painter.drawText(
                    QRectF(cx + 2, table_y, col_w - 4, row_h_px),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    fm_v.elidedText(str(col), Qt.ElideRight, int(col_w - 4)),
                )

            # ── Data rows (virtual: only the visible slice) ───────────────
            visible_rows = result_rows[scroll_offset: scroll_offset + max_data_rows]
            for ri, row in enumerate(visible_rows):
                ry2 = table_y + row_h_px + ri * row_h_px
                bg = (QColor(_THEME["body_bg"]) if ri % 2 == 0
                      else QColor(_THEME["body_bg"]).lighter(115))
                painter.setPen(Qt.NoPen)
                painter.setBrush(bg)
                painter.drawRect(QRectF(PADDING, ry2, col_area_w, row_h_px))
                painter.setPen(QColor(_THEME["value_fg"]))
                painter.setFont(_VALUE_FONT)
                for ci, col in enumerate(visible_cols):
                    cx = PADDING + ci * col_w
                    cell_val = (str(row.get(col, "")) if isinstance(row, dict)
                                else (str(row[h_scroll_offset + ci])
                                      if h_scroll_offset + ci < len(row) else ""))
                    painter.drawText(
                        QRectF(cx + 2, ry2, col_w - 4, row_h_px),
                        Qt.AlignVCenter | Qt.AlignLeft,
                        fm_v.elidedText(cell_val, Qt.ElideRight, int(col_w - 4)),
                    )

            # Zero-rows message
            if not result_rows:
                painter.setFont(QFont("Segoe UI", 8))
                painter.setPen(QColor(_THEME["label_fg"]))
                painter.drawText(
                    QRectF(PADDING, table_y + row_h_px, col_area_w, 20),
                    Qt.AlignVCenter | Qt.AlignHCenter,
                    "0 linhas retornadas",
                )

            # ── Vertical scrollbar ────────────────────────────────────────
            if has_v_sb:
                sb_rect = self._scrollbar_rect(w, table_y + row_h_px,
                                               table_h - row_h_px)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(_THEME["body_border"]))
                painter.drawRoundedRect(sb_rect, 3, 3)
                thumb_ratio = max_data_rows / total_rows
                thumb_h     = max(12.0, sb_rect.height() * thumb_ratio)
                thumb_top   = sb_rect.top() + (sb_rect.height() - thumb_h) * (
                    scroll_offset / max(1, max_v_offset)
                )
                painter.setBrush(QColor(_THEME["sel_border"]))
                painter.drawRoundedRect(
                    QRectF(sb_rect.x(), thumb_top, sb_rect.width(), thumb_h), 3, 3
                )

            # ── Horizontal scrollbar ──────────────────────────────────────
            if has_h_sb:
                hb_rect = self._h_scrollbar_rect(w, table_y + table_h + row_h_px)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(_THEME["body_border"]))
                painter.drawRoundedRect(hb_rect, 3, 3)
                h_thumb_ratio = max_vis_cols / total_cols
                h_thumb_w     = max(12.0, hb_rect.width() * h_thumb_ratio)
                h_thumb_left  = hb_rect.left() + (hb_rect.width() - h_thumb_w) * (
                    h_scroll_offset / max(1, max_h_offset)
                )
                painter.setBrush(QColor(_THEME["sel_border"]))
                painter.drawRoundedRect(
                    QRectF(h_thumb_left, hb_rect.y(), h_thumb_w, hb_rect.height()), 3, 3
                )

        # ── Pulse overlay on ▶ run button ─────────────────────────────────
        if self._pulse_opacity > 0.0:
            run_x    = w - self._RUN_BTN_W - 2
            run_rect = QRectF(run_x, HEADER_H + 3, self._RUN_BTN_W - 2,
                              self._FILTER_BAR_H - 6)
            pulse_c  = QColor(255, 255, 255, int(self._pulse_opacity * 200))
            painter.setPen(Qt.NoPen)
            painter.setBrush(pulse_c)
            pulse_path = QPainterPath()
            pulse_path.addRoundedRect(run_rect, 3, 3)
            painter.drawPath(pulse_path)

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

            # ─ Drop-target ring ────────────────────────────────────────────
            if port is self._drop_target_port:
                ring = QColor("#22c55e")
                ring.setAlphaF(0.9)
                painter.setPen(QPen(ring, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(local_pos, PORT_R + 5, PORT_R + 5)

            # ─ Hover glow ─────────────────────────────────────────────────
            if port is self._hovered_port:
                glow = QColor(_THEME["port_conn"])
                glow.setAlphaF(0.3)
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(local_pos, PORT_R + 4, PORT_R + 4)

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

    def hoverMoveEvent(self, event):
        local = event.pos()
        handle = self._handle_at(local)
        cursor_map = {
            "br": Qt.SizeFDiagCursor,
            "mr": Qt.SizeHorCursor,
            "mb": Qt.SizeVerCursor,
        }
        if handle:
            self.setCursor(cursor_map[handle])
        else:
            self.unsetCursor()
            # Still process port hover glow via parent
            new_port = self.port_at(local)
            if new_port is not self._hovered_port:
                self._hovered_port = new_port
                self.update()

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        if self._hovered_port is not None:
            self._hovered_port = None
            self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        w = self._data.get("w", 240)
        # Check ▶ run button in filter bar
        fb_y = HEADER_H
        fb_h = self._FILTER_BAR_H
        run_x = w - self._RUN_BTN_W - 2
        if (run_x <= local.x() <= w - 2 and fb_y <= local.y() <= fb_y + fb_h):
            self._start_pulse()                 # 1.6 – pulse animation
            self.execute_requested.emit(self)
            event.accept()
            return
        # Check pin button (only visible when results exist)
        result_cols = self._data.get("result_cols", [])
        if result_cols:
            body_rows_h = self._content_top() + PADDING + len(self.rows()) * ROW_H + PADDING
            h = self._data.get("h", 160)
            if h > body_rows_h + 20:
                pin_r = self._pin_rect(w, body_rows_h)
                if pin_r.contains(local):
                    self._data["pinned"] = not self._data.get("pinned", False)
                    self.update()
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

    def wheelEvent(self, event):
        """Virtual scroll through result rows (vertical) or columns (Shift+wheel)."""
        result_rows = self._data.get("result_rows", [])
        result_cols = self._data.get("result_cols", [])
        if not result_rows and not result_cols:
            super().wheelEvent(event)
            return
        delta = -1 if event.delta() > 0 else 1
        if event.modifiers() & Qt.ShiftModifier:
            # Horizontal scroll
            self._h_scroll_offset = max(0, self._h_scroll_offset + delta)
        else:
            # Vertical scroll
            self._scroll_offset = max(0, self._scroll_offset + delta)
        self.update()
        event.accept()

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


# ─────────────────────────────────────────────────────────────────────────────
# NoteNode  (Task 5.1)
# ─────────────────────────────────────────────────────────────────────────────

_NOTE_BODY_FONT   = QFont("Segoe UI", 9)
_NOTE_BODY_FONT.setItalic(True)

_NOTE_MIN_W = 180
_NOTE_MIN_H = 80
_NOTE_HEADER_H = 22   # slimmer than SQL nodes — no validation badge


class NoteNode(BaseNode):
    """Sticky-note node for visual canvas comments.

    • No SQL ports — does not participate in the query flow.
    • Z-value sits above connections but below SQL nodes.
    • Double-click opens a multi-line QTextEdit proxy.
    • Resizable via bottom-right, right, and bottom handles (like SelectNode).
    • Header uses a warm amber colour to be visually distinct from SQL nodes.
    """

    node_type = "note"

    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "note"
        self._data: dict = {
            "text":  "",
            "color": "#fef3c7",   # post-it yellow (can be overridden)
            "w":     200.0,
            "h":     120.0,
        }
        self._header_bg_key = "note_header_bg"
        self._header_fg_key = "note_header_fg"

        # Sits above connections (z=1) but below SQL nodes (default z=0 for QGraphicsObject)
        self.setZValue(0.5)

        # Resize state
        self._resizing:      bool    = False
        self._resize_corner: str     = ""
        self._resize_start:  QPointF = QPointF()
        self._resize_w0:     float   = 200.0
        self._resize_h0:     float   = 120.0

    # ── Abstract interface ────────────────────────────────────────────────────
    def icon(self) -> str:   return "✎"
    def label(self) -> str:  return "NOTA"
    def rows(self) -> list:  return []

    def validate(self) -> list[str]:
        return []   # notes have no validation constraints

    def get_ast(self) -> dict:
        return {"type": "note"}   # no SQL contribution

    def to_dict(self) -> dict:
        d = super().to_dict()
        return d   # _data already contains text/color/w/h

    def load_from_dict(self, data: dict):
        pass   # _data restored by node_from_dict caller

    # ── Geometry ──────────────────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        w = float(self._data.get("w", 200))
        h = float(self._data.get("h", 120))
        return QRectF(0, 0, max(w, _NOTE_MIN_W), max(h, _NOTE_MIN_H))

    def _handle_br(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width(), r.height())

    def _handle_mr(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width(), r.height() / 2)

    def _handle_mb(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width() / 2, r.height())

    def _handle_at(self, local: QPointF) -> str:
        hit = 10
        for name, pt in [("br", self._handle_br()),
                          ("mr", self._handle_mr()),
                          ("mb", self._handle_mb())]:
            if (local - pt).manhattanLength() <= hit:
                return name
        return ""

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        rect   = self.boundingRect()
        w      = rect.width()
        h      = rect.height()
        selected = self.isSelected()

        # ── Shadow ────────────────────────────────────────────────────────
        shadow = QPainterPath()
        shadow.addRoundedRect(rect.adjusted(3, 3, 3, 3), 4, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawPath(shadow)

        # ── Body (post-it colour) ─────────────────────────────────────────
        color_hex = self._data.get("color", "#fef3c7")
        body_color = QColor(color_hex)
        body_path = QPainterPath()
        body_path.addRoundedRect(rect, 4, 4)
        border_col = _THEME["sel_border"] if selected else _THEME["note_header_bg"]
        painter.setPen(QPen(QColor(border_col), 2 if selected else 1))
        painter.setBrush(body_color)
        painter.drawPath(body_path)

        # ── Header strip ──────────────────────────────────────────────────
        hdr_rect = QRectF(0, 0, w, _NOTE_HEADER_H)
        hdr_path = QPainterPath()
        hdr_path.addRoundedRect(hdr_rect, 4, 4)
        hdr_path.addRect(QRectF(0, _NOTE_HEADER_H / 2, w, _NOTE_HEADER_H / 2))
        hdr_col = _THEME["sel_header"] if selected else _THEME["note_header_bg"]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(hdr_col))
        painter.drawPath(hdr_path)

        # Header label (no validation badge, no icon)
        painter.setFont(_HEADER_FONT)
        painter.setPen(QColor(_THEME["note_header_fg"] if not selected
                              else _THEME["header_fg"]))
        painter.drawText(
            QRectF(PADDING, 0, w - PADDING * 2, _NOTE_HEADER_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.label(),
        )

        # ── Body text ─────────────────────────────────────────────────────
        text = self._data.get("text", "")
        text_rect = QRectF(PADDING, _NOTE_HEADER_H + PADDING / 2,
                           w - PADDING * 2, h - _NOTE_HEADER_H - PADDING)
        painter.setFont(_NOTE_BODY_FONT)
        painter.setPen(QColor(_THEME["note_body_fg"]))
        if text:
            painter.drawText(text_rect,
                             Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                             text)
        else:
            painter.setPen(QColor(_THEME["note_body_fg"] + "88"))   # 53 % opacity
            painter.drawText(text_rect,
                             Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                             "Duplo-clique para editar…")

        # ── Resize handles (when selected) ────────────────────────────────
        if selected:
            handle_color = QColor(_THEME["sel_border"])
            painter.setPen(QPen(handle_color, 1))
            painter.setBrush(handle_color)
            for pt in (self._handle_br(), self._handle_mr(), self._handle_mb()):
                painter.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))

    # ── Mouse: resize ─────────────────────────────────────────────────────────
    def hoverMoveEvent(self, event):
        handle = self._handle_at(event.pos())
        cursor_map = {
            "br": Qt.SizeFDiagCursor,
            "mr": Qt.SizeHorCursor,
            "mb": Qt.SizeVerCursor,
        }
        if handle:
            self.setCursor(cursor_map[handle])
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        handle = self._handle_at(event.pos())
        if handle and self.isSelected():
            self._resizing = True
            self._resize_corner = handle
            self._resize_start  = event.pos()
            r = self.boundingRect()
            self._resize_w0 = r.width()
            self._resize_h0 = r.height()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._resizing:
            delta = event.pos() - self._resize_start
            new_w = self._data.get("w", 200.0)
            new_h = self._data.get("h", 120.0)
            if self._resize_corner in ("br", "mr"):
                new_w = max(float(_NOTE_MIN_W), self._resize_w0 + delta.x())
            if self._resize_corner in ("br", "mb"):
                new_h = max(float(_NOTE_MIN_H), self._resize_h0 + delta.y())
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

    # ── Double-click: open inline text editor ─────────────────────────────────
    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        # Only open editor inside body area (below header)
        if local.y() <= _NOTE_HEADER_H:
            event.accept()
            return
        self._open_text_editor()
        event.accept()

    def _open_text_editor(self):
        """Embed a QTextEdit proxy for multi-line note text editing."""
        self.close_all_proxies()
        r = self.boundingRect()
        te = QTextEdit()
        te.setPlainText(self._data.get("text", ""))
        te.setFont(_NOTE_BODY_FONT)
        te.setFrameShape(QTextEdit.NoFrame)
        body_color = self._data.get("color", "#fef3c7")
        te.setStyleSheet(
            f"background: {body_color}; color: {_THEME['note_body_fg']}; padding: 0;"
        )

        def _commit():
            text = te.toPlainText()
            if text != self._data.get("text", ""):
                self._data["text"] = text
                self.node_changed.emit(self)
                self.update()
            self.close_all_proxies()

        # Commit when editor loses focus
        te.focusOutEvent_orig = te.focusOutEvent

        def _focus_out(ev):
            te.focusOutEvent_orig(ev)
            if self._proxies:
                _commit()

        te.focusOutEvent = _focus_out

        proxy_rect = QRectF(
            PADDING,
            _NOTE_HEADER_H + PADDING / 2,
            r.width() - PADDING * 2,
            r.height() - _NOTE_HEADER_H - PADDING,
        )
        self._open_proxy(te, proxy_rect)
        te.setFocus()


# ─────────────────────────────────────────────────────────────────────────────
# GroupNode  (Task 5.2)
# ─────────────────────────────────────────────────────────────────────────────

_GROUP_MIN_W = 240
_GROUP_MIN_H = 100
_GROUP_HEADER_H = 28
_GROUP_COLLAPSE_BTN_W = 20   # width of the ▶/▼ collapse toggle button area


class GroupNode(BaseNode):
    """Container that can collapse its child nodes into a single representative block.

    Architecture
    ─────────────
    ``node_ids``   — list of node_id strings belonging to this group.

    When *collapsed*:
        • Children are hidden (``setVisible(False)``).
        • The group's bounding box shrinks to a single compact rectangle.
        • In/Out ports are mapped from the sub-graph's boundary ports.

    When *expanded*:
        • Children are shown again at their original positions.
        • The group paints a translucent lasso-style background behind them.

    The canvas (FlowCanvas) is responsible for:
        • Keeping children's scene-pos in sync when the group is moved.
        • Routing connections through the group ports when collapsed.

    The double-click toggle is self-contained — it calls
    ``_sync_children(scene)`` which looks up each node_id in the scene.

    Serialisation
    ─────────────
    ``to_dict()`` stores ``node_ids`` and ``collapsed`` so the canvas can
    restore the exact state.
    """

    node_type = "group"

    def __init__(self, node_id: str = "", parent=None):
        super().__init__(node_id, parent)
        self.node_type = "group"
        self._data: dict = {
            "label":     "Grupo",
            "node_ids":  [],   # list[str] of child node IDs
            "collapsed": False,
            "w":         300.0,
            "h":         200.0,
        }
        self._header_bg_key = "group_header_bg"
        self._header_fg_key = "group_header_fg"

        # GroupNode sits below all SQL nodes so children render on top
        self.setZValue(-1.0)

        # Collapse/expand input/output context ports
        _add_port(self, "in",  0, "grp_in",  label="in",  port_kind="context")
        _add_port(self, "out", 0, "grp_out", label="out", port_kind="context")

        # Resize state
        self._resizing:      bool    = False
        self._resize_corner: str     = ""
        self._resize_start:  QPointF = QPointF()
        self._resize_w0:     float   = 300.0
        self._resize_h0:     float   = 200.0

    # ── Abstract interface ────────────────────────────────────────────────────
    def icon(self) -> str:   return "⬡"
    def label(self) -> str:  return self._data.get("label", "Grupo")
    def rows(self) -> list:
        n = len(self._data.get("node_ids", []))
        collapsed = self._data.get("collapsed", False)
        return [
            ("nós",    str(n)),
            ("estado", "colapsado" if collapsed else "expandido"),
        ]

    def validate(self) -> list[str]:
        return []

    def get_ast(self) -> dict:
        return {
            "type":      "group",
            "label":     self._data.get("label", ""),
            "node_ids":  list(self._data.get("node_ids", [])),
            "collapsed": self._data.get("collapsed", False),
        }

    def to_dict(self) -> dict:
        return super().to_dict()   # _data already contains all needed fields

    def load_from_dict(self, data: dict):
        pass

    # ── Child management ──────────────────────────────────────────────────────
    def add_node_id(self, node_id: str) -> None:
        ids: list[str] = self._data.setdefault("node_ids", [])
        if node_id not in ids:
            ids.append(node_id)
            self.node_changed.emit(self)

    def remove_node_id(self, node_id: str) -> None:
        ids: list[str] = self._data.get("node_ids", [])
        if node_id in ids:
            ids.remove(node_id)
            self.node_changed.emit(self)

    def is_collapsed(self) -> bool:
        return bool(self._data.get("collapsed", False))

    # ── Expand / Collapse ─────────────────────────────────────────────────────
    def toggle_collapse(self) -> None:
        """Toggle between collapsed and expanded states.

        Must be called with the QGraphicsScene available via ``self.scene()``.
        """
        scene = self.scene()
        if scene is None:
            return
        collapsed = not self.is_collapsed()
        self._data["collapsed"] = collapsed
        self._sync_children(scene, visible=not collapsed)
        self.prepareGeometryChange()
        self.update()
        self.node_changed.emit(self)

    def _sync_children(self, scene, *, visible: bool) -> None:
        """Show or hide all child nodes (and their connections) in *scene*."""
        node_ids: set[str] = set(self._data.get("node_ids", []))
        for item in scene.items():
            if isinstance(item, BaseNode) and item.node_id in node_ids:
                item.setVisible(visible)

    # ── Geometry ──────────────────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        if self.is_collapsed():
            return QRectF(0, 0,
                          max(float(_GROUP_MIN_W), NODE_WIDTH),
                          float(_GROUP_HEADER_H + PADDING * 2 + ROW_H * 2))
        w = float(self._data.get("w", 300))
        h = float(self._data.get("h", 200))
        return QRectF(0, 0, max(w, _GROUP_MIN_W), max(h, _GROUP_MIN_H))

    def _handle_br(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width(), r.height())

    def _handle_mr(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width(), r.height() / 2)

    def _handle_mb(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width() / 2, r.height())

    def _handle_at(self, local: QPointF) -> str:
        if self.is_collapsed():
            return ""   # no resize when collapsed
        hit = 10
        for name, pt in [("br", self._handle_br()),
                          ("mr", self._handle_mr()),
                          ("mb", self._handle_mb())]:
            if (local - pt).manhattanLength() <= hit:
                return name
        return ""

    def _collapse_btn_rect(self) -> QRectF:
        """Rectangle for the ▶/▼ button on the right of the header."""
        r = self.boundingRect()
        return QRectF(r.width() - _GROUP_COLLAPSE_BTN_W - PADDING / 2,
                      (float(_GROUP_HEADER_H) - 16) / 2,
                      float(_GROUP_COLLAPSE_BTN_W), 16.0)

    def _port_local(self, port: Port) -> QPointF:
        r = self.boundingRect()
        h = r.height()
        if port.side == "in":
            return QPointF(0, float(_GROUP_HEADER_H) + PADDING + ROW_H / 2)
        return QPointF(r.width(), float(_GROUP_HEADER_H) + PADDING + ROW_H / 2)

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        rect     = self.boundingRect()
        w        = rect.width()
        h        = rect.height()
        selected = self.isSelected()
        collapsed = self.is_collapsed()

        # ── Background ────────────────────────────────────────────────────
        body_path = QPainterPath()
        body_path.addRoundedRect(rect, 6, 6)
        if collapsed:
            body_bg = QColor(_THEME["group_body_bg"])
        else:
            body_bg = QColor(_THEME["group_body_bg"])
            body_bg.setAlphaF(0.35)   # translucent lasso in expanded state
        border_col = _THEME["sel_border"] if selected else _THEME["group_border"]
        painter.setPen(QPen(QColor(border_col), 2 if selected else 1,
                            Qt.SolidLine if collapsed else Qt.DashLine))
        painter.setBrush(body_bg)
        painter.drawPath(body_path)

        # ── Header ────────────────────────────────────────────────────────
        hdr_rect = QRectF(0, 0, w, float(_GROUP_HEADER_H))
        hdr_path = QPainterPath()
        hdr_path.addRoundedRect(hdr_rect, 6, 6)
        hdr_path.addRect(QRectF(0, float(_GROUP_HEADER_H) / 2, w,
                                float(_GROUP_HEADER_H) / 2))
        hdr_col = _THEME["sel_header"] if selected else _THEME["group_header_bg"]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(hdr_col))
        painter.drawPath(hdr_path)

        # Header icon
        painter.setFont(_ICON_FONT)
        painter.setPen(QColor(_THEME["icon_color"]))
        painter.drawText(
            QRectF(PADDING, 0, 22, float(_GROUP_HEADER_H)),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.icon(),
        )

        # Header label
        painter.setFont(_HEADER_FONT)
        painter.setPen(QColor(_THEME["group_header_fg"] if not selected
                              else _THEME["header_fg"]))
        btn_r = self._collapse_btn_rect()
        label_w = btn_r.left() - PADDING - 22 - PADDING
        painter.drawText(
            QRectF(PADDING + 22, 0, label_w, float(_GROUP_HEADER_H)),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.label(),
        )

        # ▶/▼ collapse toggle button
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(_THEME["group_header_fg"]))
        painter.drawText(btn_r, Qt.AlignCenter,
                         "▶" if collapsed else "▼")

        # ── Body: show row info when collapsed, empty when expanded ───────
        if collapsed:
            y0 = float(_GROUP_HEADER_H) + PADDING
            for i, (lbl, val) in enumerate(self.rows()):
                ry = y0 + i * ROW_H
                painter.setFont(_LABEL_FONT)
                painter.setPen(QColor(_THEME["label_fg"]))
                painter.drawText(QRectF(PADDING, ry, 80, ROW_H),
                                 Qt.AlignVCenter | Qt.AlignLeft, str(lbl) + ":")
                painter.setFont(_VALUE_FONT)
                painter.setPen(QColor(_THEME["value_fg"]))
                painter.drawText(QRectF(90, ry, w - 90 - PADDING, ROW_H),
                                 Qt.AlignVCenter | Qt.AlignLeft, str(val))

        # ── Ports ─────────────────────────────────────────────────────────
        self._paint_ports(painter)

        # ── Resize handles (expanded + selected) ──────────────────────────
        if selected and not collapsed:
            handle_color = QColor(_THEME["sel_border"])
            painter.setPen(QPen(handle_color, 1))
            painter.setBrush(handle_color)
            for pt in (self._handle_br(), self._handle_mr(), self._handle_mb()):
                painter.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))

    # ── Mouse events ──────────────────────────────────────────────────────────
    def hoverMoveEvent(self, event):
        handle = self._handle_at(event.pos())
        cursor_map = {
            "br": Qt.SizeFDiagCursor,
            "mr": Qt.SizeHorCursor,
            "mb": Qt.SizeVerCursor,
        }
        if handle:
            self.setCursor(cursor_map[handle])
        else:
            self.unsetCursor()
        # Parent handles port hover
        new_port = self.port_at(event.pos())
        if new_port is not self._hovered_port:
            self._hovered_port = new_port
            self.update()

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        handle = self._handle_at(event.pos())
        if handle and self.isSelected():
            self._resizing = True
            self._resize_corner = handle
            self._resize_start  = event.pos()
            r = self.boundingRect()
            self._resize_w0 = r.width()
            self._resize_h0 = r.height()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._resizing:
            delta = event.pos() - self._resize_start
            new_w = self._data.get("w", 300.0)
            new_h = self._data.get("h", 200.0)
            if self._resize_corner in ("br", "mr"):
                new_w = max(float(_GROUP_MIN_W), self._resize_w0 + delta.x())
            if self._resize_corner in ("br", "mb"):
                new_h = max(float(_GROUP_MIN_H), self._resize_h0 + delta.y())
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

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        local = event.pos()
        # Header area → toggle collapse
        if local.y() <= _GROUP_HEADER_H:
            self.toggle_collapse()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


# ── Factory ───────────────────────────────────────────────────────────────────
_NODE_REGISTRY: dict[str, type] = {
    "table":     TableNode,
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
    # New nodes (Tasks 5.1 / 5.2)
    "note":      NoteNode,
    "group":     GroupNode,
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
