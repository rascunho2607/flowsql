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
from pathlib import Path

from PyQt5.QtCore import (
    Qt, QPointF, QRectF, QPoint, pyqtSignal, QMimeData,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QTransform, QDrag, QKeyEvent,
    QWheelEvent, QMouseEvent,
)
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QUndoStack,
    QUndoCommand, QApplication, QMenu, QAction,
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

    def undo(self):
        self._conn.remove()
        if self._conn in self._canvas._connections:
            self._canvas._connections.remove(self._conn)
        self._canvas.flow_changed.emit()


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
        self.setTransform(QTransform().scale(factor, factor))
        self._zoom = factor
        self.zoom_changed.emit(factor)

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
            # Check if clicking on a port
            item = self._scene.itemAt(scene_pos, self.transform())
            if isinstance(item, BaseNode):
                port = item.port_at(item.mapFromScene(scene_pos))
                if port and port.side == "out":
                    # Begin connection drag
                    self._drag_from_port = port
                    self._drag_from_node = item
                    self._temp_conn = TempConnection(port.scene_pos())
                    self._scene.addItem(self._temp_conn)
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

        if self._temp_conn is not None:
            self._temp_conn.update_end(scene_pos)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())

        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if self._temp_conn is not None:
            # Try to find a target port under cursor
            self._scene.removeItem(self._temp_conn)
            self._temp_conn = None

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
        if event.key() == Qt.Key_Space:
            self._space_held = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            return
        if event.key() == Qt.Key_0 and event.modifiers() & Qt.ControlModifier:
            self.zoom_reset()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self._space_held = False
            self.setCursor(Qt.ArrowCursor)
        super().keyReleaseEvent(event)

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
