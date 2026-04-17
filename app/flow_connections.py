from __future__ import annotations
"""
flow_connections.py — Bezier curve connections between node ports.
"""

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush, QFont
from PyQt5.QtWidgets import (
    QGraphicsPathItem, QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
)

from app.flow_nodes import _THEME, Port, BaseNode


class FlowConnection(QGraphicsPathItem):
    """
    A Bezier curve drawn between an output port and an input port.
    """

    def __init__(
        self,
        from_node: BaseNode,
        from_port: Port,
        to_node: BaseNode,
        to_port: Port,
        parent=None,
    ):
        super().__init__(parent)
        self.from_node = from_node
        self.from_port = from_port
        self.to_node   = to_node
        self.to_port   = to_port

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)   # draw behind nodes

        self._hover = False

        # Mark ports as connected
        from_port.connected = True
        to_port.connected   = True
        from_node.update()
        to_node.update()

        # Connect position signals so we repaint when a node moves
        from_node.position_changed.connect(self._update_path)
        to_node.position_changed.connect(self._update_path)

        self._update_path()

    # ── Geometry ──────────────────────────────────────────────────────────────
    def _ctrl_offset(self) -> float:
        """Control-point horizontal offset (scales with distance)."""
        p1 = self.from_port.scene_pos()
        p4 = self.to_port.scene_pos()
        dist = abs(p4.x() - p1.x())
        return max(60.0, dist * 0.4)

    def _update_path(self, *_):
        p1 = self.from_port.scene_pos()
        p4 = self.to_port.scene_pos()
        offset = self._ctrl_offset()
        p2 = QPointF(p1.x() + offset, p1.y())
        p3 = QPointF(p4.x() - offset, p4.y())

        path = QPainterPath(p1)
        path.cubicTo(p2, p3, p4)
        self.setPath(path)
        self.update()

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-4, -4, 4, 4)

    def shape(self):
        # Make a wider clickable area than the visual stroke
        stroker = self.path()
        from PyQt5.QtGui import QPainterPathStroker
        ps = QPainterPathStroker()
        ps.setWidth(12)
        return ps.createStroke(stroker)

    # ── Label ─────────────────────────────────────────────────────────────────
    def get_label(self) -> str:
        """Return a short operator label to render on the edge, or '' if none."""
        node_type = getattr(self.to_node, "node_type", "")

        if node_type == "join":
            port_id = self.to_port.port_id
            if port_id.startswith("in_left_") or port_id.startswith("in_right_"):
                try:
                    idx = int(port_id.split("_")[-1])
                except (ValueError, IndexError):
                    return ""
                pairs: list[dict] = self.to_node._data.get("pairs", [])
                if idx < len(pairs):
                    return pairs[idx].get("op", "=")

        elif node_type == "where":
            port_id = self.to_port.port_id
            if port_id.startswith("in_field_") or port_id.startswith("in_value_"):
                try:
                    idx = int(port_id.split("_")[-1])
                except (ValueError, IndexError):
                    return ""
                conditions: list[dict] = self.to_node._data.get("conditions", [])
                if idx < len(conditions):
                    return conditions[idx].get("op", "=")

        return ""

    def _bezier_midpoint(self) -> QPointF:
        """Return the cubic Bezier midpoint (t=0.5) in local item coordinates."""
        p1 = self.from_port.scene_pos()
        p4 = self.to_port.scene_pos()
        offset = self._ctrl_offset()
        p2 = QPointF(p1.x() + offset, p1.y())
        p3 = QPointF(p4.x() - offset, p4.y())
        # B(0.5) = 0.125*P0 + 0.375*P1 + 0.375*P2 + 0.125*P3
        mx = 0.125 * p1.x() + 0.375 * p2.x() + 0.375 * p3.x() + 0.125 * p4.x()
        my = 0.125 * p1.y() + 0.375 * p2.y() + 0.375 * p3.y() + 0.125 * p4.y()
        return self.mapFromScene(QPointF(mx, my))

    # ── Paint ─────────────────────────────────────────────────────────────────
    def _base_color(self) -> QColor:
        """Determine stroke color from port kind and destination node type."""
        kind = self.from_port.kind
        if kind == "context":
            base = QColor(_THEME["sel_border"])   # blue
        elif kind == "field":
            base = QColor("#22c55e")              # green
        else:                                      # "data"
            base = QColor(_THEME["conn_line"])    # gray

        # Override for destructive destination nodes
        if getattr(self.to_node, "node_type", "") in ("update", "delete"):
            base = QColor("#ef4444")

        return base

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        selected = self.isSelected()
        color = self._base_color()

        if selected:
            width = 3.0
            style = Qt.SolidLine
            color = QColor(_THEME["sel_border"])   # blue highlight
        elif self._hover:
            width = 2.0
            style = Qt.SolidLine
        else:
            width = 1.5
            style = Qt.SolidLine

        pen = QPen(color, width, style)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

        # Small dot at each endpoint
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))
        for pt in (self.from_port.scene_pos(), self.to_port.scene_pos()):
            local = self.mapFromScene(pt)
            painter.drawEllipse(local, 3, 3)

        # Edge label (operator badge)
        label = self.get_label()
        if label:
            mid = self._bezier_midpoint()
            font = QFont("Consolas", 7, QFont.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(label)
            th = fm.height()
            pad = 3
            bg_rect = QRectF(
                mid.x() - tw / 2 - pad,
                mid.y() - th / 2 - pad,
                tw + pad * 2,
                th + pad * 2,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(_THEME["body_bg"])))
            painter.drawRoundedRect(bg_rect, 3.0, 3.0)
            painter.setPen(QPen(QColor(_THEME["value_fg"])))
            painter.drawText(bg_rect, Qt.AlignCenter, label)

    # ── Hover ─────────────────────────────────────────────────────────────────
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def remove(self):
        """Disconnect ports and delete from scene."""
        self.from_port.connected = False
        self.to_port.connected   = False
        self.from_node.position_changed.disconnect(self._update_path)
        self.to_node.position_changed.disconnect(self._update_path)
        self.from_node.update()
        self.to_node.update()
        if self.scene():
            self.scene().removeItem(self)

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "from_node": self.from_node.node_id,
            "from_port": self.from_port.port_id,
            "to_node":   self.to_node.node_id,
            "to_port":   self.to_port.port_id,
        }


class TempConnection(QGraphicsPathItem):
    """
    Rubber-band line drawn while the user drags from a port
    before dropping on a target port.
    """

    def __init__(self, start: QPointF, parent=None):
        super().__init__(parent)
        self._start = start
        self._end   = start
        self.is_valid: bool = True   # False → draw in red with ⛔ indicator
        self.setZValue(-1)
        self._refresh()

    def update_end(self, end: QPointF):
        self._end = end
        self._refresh()

    def _refresh(self):
        p1 = self._start
        p4 = self._end
        offset = max(60.0, abs(p4.x() - p1.x()) * 0.4)
        p2 = QPointF(p1.x() + offset, p1.y())
        p3 = QPointF(p4.x() - offset, p4.y())
        path = QPainterPath(p1)
        path.cubicTo(p2, p3, p4)
        self.setPath(path)
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None):
        color = QColor("#3b82f6") if self.is_valid else QColor("#ef4444")
        pen = QPen(color, 1.5, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

        # Draw ⛔ indicator near cursor when the connection is invalid
        if not self.is_valid:
            painter.setFont(QFont("Segoe UI", 11))
            painter.setPen(QColor("#ef4444"))
            painter.drawText(self._end + QPointF(10, -10), "\u26d4")
