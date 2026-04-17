from __future__ import annotations
"""
flow_canvas.py — QGraphicsView / QGraphicsScene for the Flow Builder.

Features:
  - Dot-grid background
  - Ctrl+Scroll zoom (25%–400%), Ctrl+0 reset
  - Middle-button pan / Space+LMB pan
  - Drag-and-drop from NodePalette → creates nodes at drop position
  - Snap-to-grid (toggleable)
  - Rubber-band selection
  - Port-to-port Bezier connections with validation
  - Delete / Backspace removes selected items
  - QUndoStack for move, add, delete, connect
  - save_to_json / load_from_json
"""

import json
import uuid
from pathlib import Path

from PyQt5.QtCore import (
    Qt, QPointF, QRectF, QPoint, pyqtSignal, QMimeData, QTimer,
    QPropertyAnimation, QEasingCurve, QObject, pyqtProperty,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QTransform, QDrag, QKeyEvent,
    QWheelEvent, QMouseEvent, QFont,
)
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QUndoStack,
    QUndoCommand, QApplication, QMenu, QAction,
    QWidget, QDialog, QVBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QInputDialog,
)

from app.flow_nodes import (
    BaseNode, Port, create_node, node_from_dict, apply_node_theme, _THEME,
)
from app.flow_connections import FlowConnection, TempConnection

GRID_SIZE = 20


# ── Undo commands ─────────────────────────────────────────────────────────────

class AddNodeCommand(QUndoCommand):
    def __init__(self, canvas: "FlowCanvas", node: BaseNode):
        super().__init__("Adicionar Node")
        self._canvas = canvas
        self._node   = node

    def redo(self):
        self._canvas._scene.addItem(self._node)
        self._canvas._nodes.append(self._node)
        self._canvas._connect_node_signals(self._node)
        self._canvas.flow_changed.emit()

    def undo(self):
        self._canvas._scene.removeItem(self._node)
        self._canvas._nodes.remove(self._node)
        self._canvas.flow_changed.emit()


class DeleteItemsCommand(QUndoCommand):
    def __init__(self, canvas: "FlowCanvas", nodes: list, conns: list):
        super().__init__("Deletar")
        self._canvas = canvas
        self._nodes  = nodes
        self._conns  = conns

    def redo(self):
        for conn in self._conns:
            conn.remove()
            if conn in self._canvas._connections:
                self._canvas._connections.remove(conn)
        for node in self._nodes:
            # Also remove connections attached to this node
            attached = [c for c in list(self._canvas._connections)
                        if c.from_node is node or c.to_node is node]
            for c in attached:
                c.remove()
                if c in self._canvas._connections:
                    self._canvas._connections.remove(c)
            self._canvas._scene.removeItem(node)
            if node in self._canvas._nodes:
                self._canvas._nodes.remove(node)
        self._canvas.flow_changed.emit()

    def undo(self):
        for node in self._nodes:
            self._canvas._scene.addItem(node)
            self._canvas._nodes.append(node)
            self._canvas._connect_node_signals(node)
        for conn in self._conns:
            self._canvas._scene.addItem(conn)
            self._canvas._connections.append(conn)
        self._canvas.flow_changed.emit()


class MoveNodeCommand(QUndoCommand):
    def __init__(self, node: BaseNode, old_pos: QPointF, new_pos: QPointF):
        super().__init__("Mover Node")
        self._node    = node
        self._old_pos = old_pos
        self._new_pos = new_pos

    def redo(self):  self._node.setPos(self._new_pos)
    def undo(self):  self._node.setPos(self._old_pos)


class AddConnectionCommand(QUndoCommand):
    def __init__(self, canvas: "FlowCanvas", conn: FlowConnection):
        super().__init__("Conectar")
        self._canvas = canvas
        self._conn   = conn

    def redo(self):
        self._canvas._scene.addItem(self._conn)
        self._canvas._connections.append(self._conn)
        self._conn.from_port.connected = True
        self._conn.to_port.connected   = True
        self._conn.from_node.update()
        self._conn.to_node.update()
        self._canvas.flow_changed.emit()
        # Notify the destination node so it can react (e.g. rebuild dynamic ports)
        self._conn.to_node.port_connected.emit(self._conn.to_port.port_id)
        # Allow nodes that care about the from_port object (e.g. UpdateNode)
        if hasattr(self._conn.to_node, "_on_field_port_connected"):
            self._conn.to_node._on_field_port_connected(
                self._conn.to_port.port_id, self._conn.from_port
            )
        # Auto-wire JoinNode context after this command finishes
        conn = self._conn
        QTimer.singleShot(0, lambda: self._canvas._try_auto_wire_join_ctx(conn))

    def undo(self):
        self._conn.remove()
        if self._conn in self._canvas._connections:
            self._canvas._connections.remove(self._conn)
        self._canvas.flow_changed.emit()


class DuplicateNodesCommand(QUndoCommand):
    """Undo/redo for duplicated nodes and their internal connections."""

    def __init__(self, canvas: "FlowCanvas", new_nodes: list,
                 new_conns: list):
        super().__init__("Duplicar Nós")
        self._canvas    = canvas
        self._new_nodes = new_nodes   # list[BaseNode]
        self._new_conns = new_conns   # list[FlowConnection]

    def redo(self):
        for node in self._new_nodes:
            self._canvas._scene.addItem(node)
            self._canvas._nodes.append(node)
            self._canvas._connect_node_signals(node)
        for conn in self._new_conns:
            self._canvas._scene.addItem(conn)
            self._canvas._connections.append(conn)
            conn.from_port.connected = True
            conn.to_port.connected   = True
            # Reconnect position signals (disconnected during undo)
            try:
                conn.from_node.position_changed.connect(conn._update_path)
                conn.to_node.position_changed.connect(conn._update_path)
            except RuntimeError:
                pass
            conn.from_node.update()
            conn.to_node.update()
        self._canvas._scene.clearSelection()
        for node in self._new_nodes:
            node.setSelected(True)
        self._canvas.flow_changed.emit()

    def undo(self):
        for conn in self._new_conns:
            conn.from_port.connected = False
            conn.to_port.connected   = False
            try:
                conn.from_node.position_changed.disconnect(conn._update_path)
                conn.to_node.position_changed.disconnect(conn._update_path)
            except (RuntimeError, TypeError):
                pass
            conn.from_node.update()
            conn.to_node.update()
            if conn.scene():
                conn.scene().removeItem(conn)
            if conn in self._canvas._connections:
                self._canvas._connections.remove(conn)
        for node in self._new_nodes:
            if node.scene():
                self._canvas._scene.removeItem(node)
            if node in self._canvas._nodes:
                self._canvas._nodes.remove(node)
        self._canvas.flow_changed.emit()


# ── Zoom animator ─────────────────────────────────────────────────────────────

class ZoomAnimator(QObject):
    """Smooth zoom via QPropertyAnimation on a custom Qt property."""

    def __init__(self, canvas: "FlowCanvas", parent: QObject = None):
        super().__init__(parent)
        self._canvas = canvas
        self._factor: float = 1.0
        self._anim = QPropertyAnimation(self, b"zoom_factor", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    @pyqtProperty(float)
    def zoom_factor(self) -> float:
        return self._factor

    @zoom_factor.setter
    def zoom_factor(self, value: float) -> None:
        self._factor = value
        self._canvas.setTransform(QTransform().scale(value, value))
        self._canvas._zoom = value
        self._canvas.zoom_changed.emit(value)

    def animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._factor)
        self._anim.setEndValue(target)
        self._anim.start()


# ── Scene ─────────────────────────────────────────────────────────────────────

class FlowScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"

    def set_theme(self, theme: str):
        self._theme = theme
        self.update()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        bg = "#1e1e1e" if self._theme == "dark" else "#f8f8f8"
        dot_color = "#2d2d30" if self._theme == "dark" else "#e0e0e0"

        painter.fillRect(rect, QColor(bg))

        # Dot grid
        painter.setPen(QPen(QColor(dot_color), 1.5))
        left   = int(rect.left())  - int(rect.left())  % GRID_SIZE
        top    = int(rect.top())   - int(rect.top())   % GRID_SIZE
        right  = int(rect.right())  + GRID_SIZE
        bottom = int(rect.bottom()) + GRID_SIZE

        x = left
        while x <= right:
            y = top
            while y <= bottom:
                painter.drawPoint(x, y)
                y += GRID_SIZE
            x += GRID_SIZE


# ── View / Canvas ─────────────────────────────────────────────────────────────

class FlowCanvas(QGraphicsView):
    """Main visual canvas for the Flow Builder."""

    # Signals
    flow_changed          = pyqtSignal()          # SQL needs to be regenerated
    node_selected         = pyqtSignal(object)    # BaseNode or None
    zoom_changed          = pyqtSignal(float)     # current zoom factor (0.25 – 4.0)
    node_execute_requested = pyqtSignal(object)   # BaseNode — caller wants to run this node

    def __init__(self, parent=None):
        self._scene = FlowScene()
        super().__init__(self._scene, parent)

        self._nodes:       list[BaseNode]       = []
        self._connections: list[FlowConnection] = []
        self._undo_stack   = QUndoStack(self)
        self._snap         = True
        self._zoom         = 1.0
        self._panning      = False
        self._pan_start:   QPoint  = QPoint()
        self._space_held   = False
        self._drag_node_pos: dict[BaseNode, QPointF] = {}

        # Temp connection drawn while dragging from a port
        self._temp_conn:   TempConnection | None = None
        self._drag_from_port: Port | None        = None
        self._drag_from_node: BaseNode | None    = None

        # Port that is currently highlighted as a drop target while dragging
        self._hover_target_port: Port | None     = None
        self._hover_target_node: BaseNode | None = None

        # Alt+drag duplication state
        self._alt_drag_mode:         bool                    = False
        self._alt_drag_start_scene:  QPointF                 = QPointF()
        self._alt_drag_nodes:        list[BaseNode]          = []
        self._alt_drag_nodes_init_pos: dict[BaseNode, QPointF] = {}

        # Schema inspector (set externally via set_inspector())
        self._inspector = None

        # View settings
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setObjectName("flow_canvas")

        self._scene.setSceneRect(-2000, -2000, 6000, 6000)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        # Smooth zoom animator
        self._zoom_animator = ZoomAnimator(self)

        # Minimap overlay (created after scene is ready)
        self._minimap = MiniMap(self)
        self._minimap.show()
        self._minimap.raise_()

        # Keep minimap in sync with scene and scroll changes
        self._scene.changed.connect(lambda _: self._minimap.update())

    # ── Theme ─────────────────────────────────────────────────────────────────
    def set_theme(self, theme: str):
        self._scene.set_theme(theme)
        apply_node_theme(theme)
        for node in self._nodes:
            node.update()
        for conn in self._connections:
            conn.update()

    # ── Zoom ──────────────────────────────────────────────────────────────────
    def zoom_in(self):      self._set_zoom(self._zoom * 1.2)
    def zoom_out(self):     self._set_zoom(self._zoom / 1.2)
    def zoom_reset(self):   self._set_zoom(1.0)
    def current_zoom(self) -> float: return self._zoom

    def zoom_fit(self):
        if not self._nodes:
            return
        rects = [n.mapToScene(n.boundingRect()).boundingRect() for n in self._nodes]
        united = rects[0]
        for r in rects[1:]:
            united = united.united(r)
        self.fitInView(united.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def _set_zoom(self, factor: float):
        factor = max(0.25, min(4.0, factor))
        self._zoom_animator.animate_to(factor)

    # ── Snap ──────────────────────────────────────────────────────────────────
    @property
    def snap_enabled(self) -> bool:
        return self._snap

    def set_snap(self, enabled: bool):
        self._snap = enabled

    def _snap_pos(self, pos: QPointF) -> QPointF:
        if not self._snap:
            return pos
        x = round(pos.x() / GRID_SIZE) * GRID_SIZE
        y = round(pos.y() / GRID_SIZE) * GRID_SIZE
        return QPointF(x, y)

    # ── Undo / Redo ───────────────────────────────────────────────────────────
    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    # ── Add / Remove nodes ────────────────────────────────────────────────────
    def add_node(self, node_type: str, scene_pos: QPointF) -> BaseNode:
        node = create_node(node_type)
        node.setPos(self._snap_pos(scene_pos))
        cmd = AddNodeCommand(self, node)
        self._undo_stack.push(cmd)
        self._scene.clearSelection()
        node.setSelected(True)
        return node

    def _connect_node_signals(self, node: BaseNode):
        node.node_selected.connect(lambda n: self.node_selected.emit(n))
        node.node_changed.connect(lambda _: self.flow_changed.emit())
        node.position_changed.connect(self._on_node_moved)
        if hasattr(node, "execute_requested"):
            node.execute_requested.connect(self.node_execute_requested.emit)

    def _on_node_moved(self, node: BaseNode):
        if self._snap:
            snapped = self._snap_pos(node.pos())
            if snapped != node.pos():
                node.setPos(snapped)

    def delete_selected(self):
        sel_nodes = [i for i in self._scene.selectedItems() if isinstance(i, BaseNode)]
        sel_conns = [i for i in self._scene.selectedItems() if isinstance(i, FlowConnection)]
        if not sel_nodes and not sel_conns:
            return
        cmd = DeleteItemsCommand(self, sel_nodes, sel_conns)
        self._undo_stack.push(cmd)

    # ── Selection signal ──────────────────────────────────────────────────────
    def _on_selection_changed(self):
        items = self._scene.selectedItems()
        nodes = [i for i in items if isinstance(i, BaseNode)]
        self.node_selected.emit(nodes[0] if len(nodes) == 1 else None)

    # ── Connections ───────────────────────────────────────────────────────────
    def _try_connect(self, from_node: BaseNode, from_port: Port,
                     to_node: BaseNode, to_port: Port):
        # Validate: no self-connections, port direction match
        if from_node is to_node:
            return
        if from_port.side != "out" or to_port.side != "in":
            return
        # Port-kind compatibility: field <-> context is forbidden.
        # "data" is compatible with everything (backward compat).
        fk, tk = from_port.kind, to_port.kind
        if fk != "data" and tk != "data":
            if fk != tk:
                return
        # Check not already connected
        for conn in self._connections:
            if conn.from_port is from_port and conn.to_port is to_port:
                return
        conn = FlowConnection(from_node, from_port, to_node, to_port)
        # Remove from scene first (AddConnectionCommand will re-add)
        conn.setParentItem(None)
        cmd = AddConnectionCommand(self, conn)
        self._undo_stack.push(cmd)

    def _can_connect_preview(self, from_port: Port, to_port: Port) -> bool:
        """Return True if from_port can legally connect to to_port (used for
        highlighting during drag without actually creating the connection)."""
        if from_port is None or to_port is None:
            return False
        if from_port.node is to_port.node:
            return False
        if from_port.side != "out" or to_port.side != "in":
            return False
        fk, tk = from_port.kind, to_port.kind
        if fk != "data" and tk != "data":
            if fk != tk:
                return False
        for conn in self._connections:
            if conn.from_port is from_port and conn.to_port is to_port:
                return False
        return True

    def _duplicate_selected(self) -> list[BaseNode]:
        """Create copies of all selected nodes (and internal connections).
        Pushes a DuplicateNodesCommand and returns the list of new nodes."""
        sel_nodes = [n for n in self._nodes if n.isSelected()]
        if not sel_nodes:
            return []

        sel_ids = {n.node_id for n in sel_nodes}
        old_to_new: dict[str, BaseNode] = {}
        new_nodes: list[BaseNode] = []

        for node in sel_nodes:
            data = node.to_dict()
            new_node = node_from_dict(data)
            # Restore extra fields (schema columns, etc.)
            new_node.load_from_dict(data)
            # Assign fresh ID so duplicates are independent
            new_node.node_id = str(uuid.uuid4())[:8]
            new_node.setPos(node.pos() + QPointF(30, 30))
            old_to_new[node.node_id] = new_node
            new_nodes.append(new_node)

        # Duplicate connections that are entirely within the selection
        new_conns: list[FlowConnection] = []
        for conn in self._connections:
            if (conn.from_node.node_id in sel_ids and
                    conn.to_node.node_id in sel_ids):
                fn = old_to_new[conn.from_node.node_id]
                tn = old_to_new[conn.to_node.node_id]
                fp = next((p for p in fn.out_ports
                           if p.port_id == conn.from_port.port_id), None)
                tp = next((p for p in tn.in_ports
                           if p.port_id == conn.to_port.port_id), None)
                if fp and tp:
                    nc = FlowConnection(fn, fp, tn, tp)
                    # Disconnect signals added by __init__ so that
                    # DuplicateNodesCommand.redo() can reconnect cleanly.
                    try:
                        fn.position_changed.disconnect(nc._update_path)
                        tn.position_changed.disconnect(nc._update_path)
                    except (RuntimeError, TypeError):
                        pass
                    fp.connected = False
                    tp.connected = False
                    new_conns.append(nc)

        cmd = DuplicateNodesCommand(self, new_nodes, new_conns)
        self._undo_stack.push(cmd)
        return new_nodes

    def _focus_node(self, node: BaseNode) -> None:
        """Center the viewport on *node* and select it."""
        self._scene.clearSelection()
        node.setSelected(True)
        self.centerOn(node)

    def _try_auto_wire_join_ctx(self, conn: "FlowConnection"):
        """After a field port is connected to a JoinNode, auto-wire the context
        port (in_ctx) from the source node's out_ctx if not already connected.
        Called via QTimer.singleShot so it runs outside the current undo command.
        """
        from app.flow_nodes import JoinNode as _JoinNode
        to_node = conn.to_node
        if not isinstance(to_node, _JoinNode):
            return
        port_id = conn.to_port.port_id
        if not (port_id.startswith("in_left_") or port_id.startswith("in_right_")):
            return
        # Only auto-wire if in_ctx is still unconnected
        ctx_in = next((p for p in to_node.in_ports if p.port_id == "in_ctx"), None)
        if ctx_in is None or ctx_in.connected:
            return
        # Find out_ctx on the source node
        from_node = conn.from_node
        out_ctx = next((p for p in from_node.out_ports if p.port_id == "out_ctx"), None)
        if out_ctx is None:
            return
        # Guard: don't duplicate
        for c in self._connections:
            if c.from_port is out_ctx and c.to_port is ctx_in:
                return
        # Create the context connection directly (no undo entry — it's automatic)
        auto = FlowConnection(from_node, out_ctx, to_node, ctx_in)
        self._scene.addItem(auto)
        self._connections.append(auto)
        out_ctx.connected = True
        ctx_in.connected  = True
        from_node.update()
        to_node.update()
        to_node.port_connected.emit("in_ctx")
        if hasattr(to_node, "_on_field_port_connected"):
            to_node._on_field_port_connected("in_ctx", out_ctx)
        self.flow_changed.emit()

    # ── Drag from palette / schema explorer ──────────────────────────────────
    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat("application/x-flowsql-node") or
                event.mimeData().hasFormat("application/x-flowsql-schema")):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if (event.mimeData().hasFormat("application/x-flowsql-node") or
                event.mimeData().hasFormat("application/x-flowsql-schema")):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        # ── Schema mime (functions / procedures with rich params) ───────────
        if event.mimeData().hasFormat("application/x-flowsql-schema"):
            raw = event.mimeData().data(
                "application/x-flowsql-schema"
            ).data().decode()
            try:
                meta = json.loads(raw)
            except (ValueError, TypeError):
                meta = {}
            node_type = meta.get("type", "")
            name      = meta.get("name", "")
            node = self.add_node(node_type, scene_pos)
            if node_type == "procedure" and name:
                if self._inspector is not None:
                    params = self._inspector.get_procedure_params(name)
                else:
                    params = meta.get("params_in") and {
                        "in": meta.get("params_in", []),
                        "out": meta.get("params_out", []),
                    } or {"in": [], "out": []}
                node.set_procedure_schema(
                    name,
                    params.get("in", []),
                    params.get("out", []),
                )
            elif node_type == "function" and name:
                node.set_data("formula", name + "()")
                node.set_data("mode", "formula")
            event.acceptProposedAction()
            return

        # ── Node mime (palette + schema-explorer table/field drops) ────────
        if event.mimeData().hasFormat("application/x-flowsql-node"):
            raw = event.mimeData().data(
                "application/x-flowsql-node"
            ).data().decode()

            # "field:{table}.{col}" — ignore on canvas (port-to-port only)
            if raw.startswith("field:"):
                event.acceptProposedAction()
                return

            # "table:{name}" — create TableNode and populate schema
            if raw.startswith("table:"):
                table_name = raw[len("table:"):]
                node = self.add_node("table", scene_pos)
                node.set_data("name", table_name)
                if self._inspector is not None:
                    cols = self._inspector.get_columns(table_name)
                    node.set_schema_columns(cols)
                event.acceptProposedAction()
                return

            # Detect legacy JSON payload (schema items from NodePalette.load_schema)
            node_meta: dict | None = None
            try:
                node_meta = json.loads(raw)
            except (ValueError, TypeError):
                pass

            if node_meta and isinstance(node_meta, dict):
                node_type = node_meta.get("type", "")
                name      = node_meta.get("name", "")
                node = self.add_node(node_type, scene_pos)
                if node_type == "procedure" and name:
                    if self._inspector is not None:
                        params = self._inspector.get_procedure_params(name)
                        node.set_procedure_schema(
                            name,
                            params.get("in", []),
                            params.get("out", []),
                        )
                    else:
                        node.set_procedure_schema(name, [], [])
                elif node_type == "function" and name:
                    node.set_data("formula", name + "()")
                    node.set_data("mode", "formula")
            else:
                # Plain node type string (standard palette items)
                self.add_node(raw, scene_pos)

            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())

        # Middle button or Space+LMB → start pan
        if event.button() == Qt.MiddleButton or (
            self._space_held and event.button() == Qt.LeftButton
        ):
            self._panning  = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            item = self._scene.itemAt(scene_pos, self.transform())

            # ── Alt+LMB → duplicate selected nodes and begin drag on copies ──
            if event.modifiers() & Qt.AltModifier:
                if isinstance(item, BaseNode):
                    if not item.isSelected():
                        self._scene.clearSelection()
                        item.setSelected(True)
                    # Open macro so duplicate + subsequent move are one undo step
                    self._undo_stack.beginMacro("Duplicar e Mover Nós")
                    new_nodes = self._duplicate_selected()
                    if new_nodes:
                        self._alt_drag_mode = True
                        self._alt_drag_start_scene = scene_pos
                        self._alt_drag_nodes = new_nodes
                        self._alt_drag_nodes_init_pos = {
                            n: QPointF(n.pos()) for n in new_nodes
                        }
                        self.setCursor(Qt.ClosedHandCursor)
                    else:
                        self._undo_stack.endMacro()
                    event.accept()
                    return

            # ── LMB on output port → start connection drag ─────────────────
            if isinstance(item, BaseNode):
                port = item.port_at(item.mapFromScene(scene_pos))
                if port and port.side == "out":
                    self._drag_from_port = port
                    self._drag_from_node = item
                    self._temp_conn = TempConnection(port.scene_pos())
                    self._scene.addItem(self._temp_conn)
                    self.setCursor(Qt.CrossCursor)
                    event.accept()
                    return

        super().mousePressEvent(event)

        # Record positions for undo on move
        if event.button() == Qt.LeftButton:
            for n in self._nodes:
                if n.isSelected():
                    self._drag_node_pos[n] = QPointF(n.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())

        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        # ── Alt+drag: move the duplicated nodes ───────────────────────────
        if self._alt_drag_mode:
            delta = scene_pos - self._alt_drag_start_scene
            for node in self._alt_drag_nodes:
                node.setPos(self._alt_drag_nodes_init_pos[node] + delta)
            event.accept()
            return

        if self._temp_conn is not None:
            self._temp_conn.update_end(scene_pos)

            # ── Highlight ALL compatible in-ports across every node ────────
            for node in self._nodes:
                new_hl: set[Port] = {
                    p for p in node.in_ports
                    if self._can_connect_preview(self._drag_from_port, p)
                }
                if node._highlighted_ports != new_hl:
                    node._highlighted_ports = new_hl
                    node.update()

            # ── Highlight specific in-port under cursor ────────────────────
            new_target_port = None
            new_target_node = None
            item = self._scene.itemAt(scene_pos, self.transform())
            if isinstance(item, BaseNode):
                local = item.mapFromScene(scene_pos)
                candidate = item.port_at(local)
                if candidate and candidate.side == "in":
                    new_target_port = candidate
                    new_target_node = item
            if new_target_port is not self._hover_target_port:
                # Clear old highlight
                if self._hover_target_node is not None:
                    self._hover_target_node._drop_target_port = None
                    self._hover_target_node.update()
                # Set new highlight
                self._hover_target_port = new_target_port
                self._hover_target_node = new_target_node
                if new_target_node is not None:
                    new_target_node._drop_target_port = new_target_port
                    new_target_node.update()

            # ── Update temp-connection validity colour ─────────────────────
            if new_target_port is not None:
                new_valid = self._can_connect_preview(
                    self._drag_from_port, new_target_port
                )
            else:
                new_valid = True  # neutral when not hovering a port
            if self._temp_conn.is_valid != new_valid:
                self._temp_conn.is_valid = new_valid
                self._temp_conn.update()

            event.accept()
            return

        # ── Cursor feedback over output port (idle state) ─────────────────
        item = self._scene.itemAt(scene_pos, self.transform())
        if isinstance(item, BaseNode) and not self._space_held:
            local = item.mapFromScene(scene_pos)
            port  = item.port_at(local)
            if port and port.side == "out":
                self.setCursor(Qt.CrossCursor)
            else:
                self.unsetCursor()
        elif not self._space_held and not self._panning:
            self.unsetCursor()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())

        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        # ── Alt+drag release: snap new nodes and push move commands ───────
        if self._alt_drag_mode:
            self._alt_drag_mode = False
            for node in self._alt_drag_nodes:
                new_pos = self._snap_pos(node.pos())
                old_pos = self._alt_drag_nodes_init_pos[node]
                if (new_pos - old_pos).manhattanLength() > 1:
                    node.setPos(new_pos)
                    self._undo_stack.push(MoveNodeCommand(node, old_pos, new_pos))
            self._alt_drag_nodes.clear()
            self._alt_drag_nodes_init_pos.clear()
            self._undo_stack.endMacro()
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if self._temp_conn is not None:
            # Clear all highlighted ports
            for node in self._nodes:
                if node._highlighted_ports:
                    node._highlighted_ports = set()
                    node.update()
            # Clear drop-target highlight
            if self._hover_target_node is not None:
                self._hover_target_node._drop_target_port = None
                self._hover_target_node.update()
            self._hover_target_port = None
            self._hover_target_node = None

            # Try to find a target port under cursor
            self._scene.removeItem(self._temp_conn)
            self._temp_conn = None
            self.unsetCursor()

            target_item = self._scene.itemAt(scene_pos, self.transform())
            if isinstance(target_item, BaseNode) and self._drag_from_port:
                port = target_item.port_at(target_item.mapFromScene(scene_pos))
                if port and port.side == "in":
                    self._try_connect(
                        self._drag_from_node, self._drag_from_port,
                        target_item, port,
                    )
            self._drag_from_port = None
            self._drag_from_node = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

        # Push move commands for moved nodes
        if event.button() == Qt.LeftButton:
            for node, old_pos in self._drag_node_pos.items():
                new_pos = self._snap_pos(node.pos())
                if (new_pos - old_pos).manhattanLength() > 1:
                    node.setPos(new_pos)
                    cmd = MoveNodeCommand(node, old_pos, new_pos)
                    self._undo_stack.push(cmd)
            self._drag_node_pos.clear()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self._set_zoom(self._zoom * factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key  = event.key()
        mods = event.modifiers()

        if key == Qt.Key_Space:
            self._space_held = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
            return

        if key == Qt.Key_0 and mods & Qt.ControlModifier:
            self.zoom_reset()
            event.accept()
            return

        # Ctrl+A — select all nodes
        if key == Qt.Key_A and mods & Qt.ControlModifier:
            for node in self._nodes:
                node.setSelected(True)
            event.accept()
            return

        # Ctrl+D — duplicate selection (no drag)
        if key == Qt.Key_D and mods & Qt.ControlModifier:
            self._duplicate_selected()
            event.accept()
            return

        # Ctrl+Shift+F — open node search dialog
        if (key == Qt.Key_F and
                mods & Qt.ControlModifier and mods & Qt.ShiftModifier):
            dlg = NodeSearchDialog(self._nodes, self)
            dlg.node_selected.connect(self._focus_node)
            dlg.exec_()
            event.accept()
            return

        # F2 — rename (set alias on) the single selected node
        if key == Qt.Key_F2:
            sel = [n for n in self._nodes if n.isSelected()]
            if len(sel) == 1:
                node = sel[0]
                current = node._data.get("alias", node._data.get("name", ""))
                name, ok = QInputDialog.getText(
                    self, "Renomear Nó",
                    f"Alias para {node.label()}:",
                    text=current,
                )
                if ok and name.strip():
                    node.set_data("alias", name.strip())
            event.accept()
            return

        # Escape — cancel active connection drag, or clear selection
        if key == Qt.Key_Escape:
            if self._temp_conn is not None:
                # Abort connection drag
                for node in self._nodes:
                    if node._highlighted_ports:
                        node._highlighted_ports = set()
                        node.update()
                if self._hover_target_node is not None:
                    self._hover_target_node._drop_target_port = None
                    self._hover_target_node.update()
                self._hover_target_port = None
                self._hover_target_node = None
                self._scene.removeItem(self._temp_conn)
                self._temp_conn = None
                self._drag_from_port = None
                self._drag_from_node = None
                self.unsetCursor()
            else:
                self._scene.clearSelection()
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self._space_held = False
            self.setCursor(Qt.ArrowCursor)
        super().keyReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_minimap"):
            self._minimap._reposition()

    def scrollContentsBy(self, dx: int, dy: int):
        super().scrollContentsBy(dx, dy)
        if hasattr(self, "_minimap"):
            self._minimap._reposition()
            self._minimap.update()

    # ── Context menu ──────────────────────────────────────────────────────────
    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())
        menu = QMenu(self)

        if isinstance(item, BaseNode):
            menu.addAction("Deletar Node", self.delete_selected)
            menu.addSeparator()

        menu.addAction("Escala 100%", self.zoom_reset)
        menu.addAction("Ajustar à tela", self.zoom_fit)
        menu.addSeparator()
        menu.addAction("Desfazer", self._undo_stack.undo)
        menu.addAction("Refazer", self._undo_stack.redo)
        menu.exec_(event.globalPos())

    # ── Accessors ─────────────────────────────────────────────────────────────
    def get_nodes(self) -> list[BaseNode]:
        return list(self._nodes)

    def get_connections(self) -> list[FlowConnection]:
        return list(self._connections)

    def clear_canvas(self):
        self._scene.clear()
        self._nodes.clear()
        self._connections.clear()
        self._undo_stack.clear()
        self.flow_changed.emit()

    # ── Persistence ───────────────────────────────────────────────────────────
    def save_to_json(self, path: str):
        data = {
            "version": "1.0",
            "nodes": [n.to_dict() for n in self._nodes],
            "connections": [c.to_dict() for c in self._connections],
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    def load_from_json(self, path: str):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.clear_canvas()

        node_map: dict[str, BaseNode] = {}
        for nd in raw.get("nodes", []):
            node = node_from_dict(nd)
            self._scene.addItem(node)
            self._nodes.append(node)
            self._connect_node_signals(node)
            node_map[nd["id"]] = node

        for cd in raw.get("connections", []):
            fn  = node_map.get(cd["from_node"])
            tn  = node_map.get(cd["to_node"])
            if not fn or not tn:
                continue
            fport = next((p for p in fn.out_ports if p.port_id == cd["from_port"]), None)
            tport = next((p for p in tn.in_ports  if p.port_id == cd["to_port"]),   None)
            if fport and tport:
                conn = FlowConnection(fn, fport, tn, tport)
                self._scene.addItem(conn)
                self._connections.append(conn)

        self.flow_changed.emit()
        self.zoom_fit()

    # ── Build AST from current canvas ─────────────────────────────────────────
    def build_ast(self) -> dict:
        from core.ast_builder import ASTBuilder
        node_dicts = [n.to_dict() for n in self._nodes]
        conn_dicts = [c.to_dict() for c in self._connections]
        return ASTBuilder.build(node_dicts, conn_dicts)

    def generate_sql(self, dialect: str = "postgresql") -> str:
        from core.sql_generator import SQLGenerator
        ast = self.build_ast()
        return SQLGenerator.generate(ast, dialect)

    def generate_sql_for_node(self, node, dialect: str = "postgresql") -> str:
        """Gera SQL apenas para o sub-grafo que alimenta `node` (ancestors + o próprio)."""
        relevant: set = set()
        queue = [node]
        while queue:
            current = queue.pop()
            if current.node_id in relevant:
                continue
            relevant.add(current.node_id)
            for conn in self._connections:
                if conn.to_node is current and conn.from_node.node_id not in relevant:
                    queue.append(conn.from_node)

        node_dicts = [n.to_dict() for n in self._nodes
                      if n.node_id in relevant]
        conn_dicts = [c.to_dict() for c in self._connections
                      if (c.from_node.node_id in relevant and
                          c.to_node.node_id in relevant)]
        try:
            from core.ast_builder import ASTBuilder
            from core.sql_generator import SQLGenerator
            ast = ASTBuilder.build(node_dicts, conn_dicts)
            return SQLGenerator.generate(ast, dialect)
        except Exception as exc:
            return f"-- Erro ao gerar SQL: {exc}"

    # ── Schema inspector reference ────────────────────────────────────────────
    def set_inspector(self, inspector) -> None:
        """Store a SchemaInspector so dropEvent can enrich schema nodes."""
        self._inspector = inspector

    # ── Terminal (leaf) nodes ─────────────────────────────────────────────────
    def get_terminal_nodes(self) -> list[BaseNode]:
        """Return nodes that have no outgoing connections (leaf/endpoint nodes)."""
        nodes_with_outgoing = {c.from_node for c in self._connections}
        return [n for n in self._nodes if n not in nodes_with_outgoing]

    # ── Partial execution ─────────────────────────────────────────────────────
    def generate_sql_for_selection(self, dialect: str = "postgresql") -> str:
        """Generate SQL only for the selected sub-graph.

        If nothing is selected, falls back to the full canvas SQL.
        """
        selected_ids = {n.node_id for n in self._nodes if n.isSelected()}

        if not selected_ids:
            # Fall back to full graph
            return self.generate_sql(dialect)

        # Filter nodes and connections to the selected sub-graph
        node_dicts = [n.to_dict() for n in self._nodes
                      if n.node_id in selected_ids]
        conn_dicts = [c.to_dict() for c in self._connections
                      if (c.from_node.node_id in selected_ids and
                          c.to_node.node_id in selected_ids)]

        try:
            from core.ast_builder import ASTBuilder
            from core.sql_generator import SQLGenerator
            ast = ASTBuilder.build(node_dicts, conn_dicts)
            return SQLGenerator.generate(ast, dialect)
        except Exception as exc:
            return f"-- Erro ao gerar SQL para seleção: {exc}"


# ── Node search dialog (Ctrl+Shift+F) ─────────────────────────────────────────

class NodeSearchDialog(QDialog):
    """Filterable list of all nodes on the canvas.  Double-click or OK to
    centre the viewport on the selected node."""

    node_selected = pyqtSignal(object)  # emits BaseNode

    def __init__(self, nodes: list, parent=None):
        super().__init__(parent)
        self._all_nodes = list(nodes)
        self.setWindowTitle("Buscar Nó")
        self.setFixedSize(380, 300)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Digite para filtrar…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self._list)

        btn = QPushButton("Ir para Nó")
        btn.clicked.connect(self._accept_item)
        layout.addWidget(btn)

        self._populate("")

    def _populate(self, filter_text: str) -> None:
        self._list.clear()
        ft = filter_text.lower()
        for node in self._all_nodes:
            display = f"{node.label()}  [{node.node_id}]"
            name_val = node._data.get("name") or node._data.get("alias") or ""
            if name_val:
                display = f"{name_val}  — {node.label()}  [{node.node_id}]"
            if ft and ft not in display.lower():
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, node)
            self._list.addItem(item)

    def _filter(self, text: str) -> None:
        self._populate(text)

    def _accept_item(self) -> None:
        item = self._list.currentItem()
        if item is None and self._list.count() > 0:
            item = self._list.item(0)
        if item:
            self.node_selected.emit(item.data(Qt.UserRole))
            self.accept()


# ── Minimap overview widget ────────────────────────────────────────────────────

class MiniMap(QWidget):
    """Semi-transparent thumbnail of the flow shown in the bottom-right corner.

    Clicking or dragging on the minimap pans the main viewport.
    """

    _WIDTH  = 160
    _HEIGHT = 110
    _MARGIN = 8
    _PAD    = 8   # inner padding around the node rectangles

    def __init__(self, canvas: "FlowCanvas"):
        # Parent is the viewport so the overlay appears above the scene
        super().__init__(canvas.viewport())
        self._canvas = canvas
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setMouseTracking(True)
        self._reposition()

    # ── Positioning ───────────────────────────────────────────────────────────
    def _reposition(self) -> None:
        vp = self._canvas.viewport()
        self.move(
            vp.width() - self._WIDTH - self._MARGIN,
            self._MARGIN,
        )

    # ── Scene bounding rect helpers ───────────────────────────────────────────
    def _scene_bounds(self) -> QRectF | None:
        nodes = self._canvas._nodes
        if not nodes:
            return None
        rects = [
            QRectF(n.pos().x(), n.pos().y(),
                   n.boundingRect().width(), n.boundingRect().height())
            for n in nodes
        ]
        bounds = rects[0]
        for r in rects[1:]:
            bounds = bounds.united(r)
        return bounds.adjusted(-40, -40, 40, 40)

    def _scale_and_offset(self, bounds: QRectF) -> tuple[float, float, float]:
        """Return (scale, offset_x, offset_y) mapping scene → minimap coords."""
        map_w = self._WIDTH  - self._PAD * 2
        map_h = self._HEIGHT - self._PAD * 2
        sx = map_w / max(bounds.width(),  1)
        sy = map_h / max(bounds.height(), 1)
        scale = min(sx, sy)
        return scale, self._PAD - bounds.x() * scale, self._PAD - bounds.y() * scale

    def _to_map(self, sx: float, sy: float,
                scale: float, ox: float, oy: float) -> tuple[float, float]:
        return sx * scale + ox, sy * scale + oy

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(0, 0, self._WIDTH, self._HEIGHT, 6, 6)

        bounds = self._scene_bounds()
        if bounds is None:
            painter.setPen(QColor(120, 120, 120, 180))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(self.rect(), Qt.AlignCenter, "sem nós")
            return

        scale, ox, oy = self._scale_and_offset(bounds)

        # Draw each node as a small coloured rectangle
        for node in self._canvas._nodes:
            hdr_key = getattr(node, "_header_bg_key", "header_bg")
            from app.flow_nodes import _THEME as _NT
            color = QColor(_NT.get(hdr_key, "#3e3e42"))
            color.setAlpha(200)
            painter.setPen(QPen(QColor(80, 80, 80, 180), 0.5))
            painter.setBrush(color)
            nx, ny = self._to_map(node.pos().x(), node.pos().y(), scale, ox, oy)
            nw = max(4.0, node.boundingRect().width()  * scale)
            nh = max(2.0, node.boundingRect().height() * scale)
            painter.drawRect(QRectF(nx, ny, nw, nh))

        # Draw viewport rectangle
        vp   = self._canvas.viewport()
        tl   = self._canvas.mapToScene(vp.rect().topLeft())
        br   = self._canvas.mapToScene(vp.rect().bottomRight())
        vx1, vy1 = self._to_map(tl.x(), tl.y(), scale, ox, oy)
        vx2, vy2 = self._to_map(br.x(), br.y(), scale, ox, oy)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 25)))
        painter.drawRect(QRectF(vx1, vy1, vx2 - vx1, vy2 - vy1))

    # ── Mouse navigation ──────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._pan_to(event.pos())
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton:
            self._pan_to(event.pos())
        event.accept()

    def _pan_to(self, pos: QPoint) -> None:
        bounds = self._scene_bounds()
        if bounds is None:
            return
        scale, ox, oy = self._scale_and_offset(bounds)
        scene_x = (pos.x() - ox) / max(scale, 1e-6)
        scene_y = (pos.y() - oy) / max(scale, 1e-6)
        self._canvas.centerOn(QPointF(scene_x, scene_y))
