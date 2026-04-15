from __future__ import annotations
"""
flow_connections.py — Bezier curve connections between node ports.
"""

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush
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
            width = 2.0
            style = Qt.DashLine
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
            # Convert to local coords
            local = self.mapFromScene(pt)
            painter.drawEllipse(local, 3, 3)

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
        pen = QPen(QColor("#3b82f6"), 1.5, Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
