from __future__ import annotations
"""
object_explorer.py — Pesquisador de Objetos com:

• Conexões assíncronas (QThread) com ícone de status por servidor
  (verde = conectado, laranja = conectando, vermelho = erro)
• Spinner animado exibido após 2 s de espera na conexão
• Filtro global no topo + filtro por nível (clique-direito -> "Filtrar nível...")
• Drag-to-reorder servidores / botões seta no menu contextual
• Ordem persistida via connection_manager.save_server_order()
• Todo carregamento de schema é assíncrono (sem bloqueio da UI)
"""

from pathlib import Path
import re
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal, QThread, QObject, QTimer, QPoint
from PyQt5.QtGui import QIcon, QFont, QColor, QBrush, QPixmap, QPainter
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QLabel, QMenu, QAction, QMessageBox, QInputDialog,
    QPushButton, QAbstractItemView,
)

if TYPE_CHECKING:
    from core.connection_manager import ConnectionManager

ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"

_SPINNER_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834",
                   "\u2826", "\u2827", "\u2807", "\u280f"]
_STATUS_COLORS  = {
    "connected":    "#4CAF50",
    "connecting":   "#FF9800",
    "error":        "#f44747",
    "disconnected": "#888888",
}


def _icon(name: str) -> QIcon:
    path = ICONS_DIR / f"{name}.svg"
    return QIcon(str(path)) if path.exists() else QIcon()


def _dot_icon(color: str) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 10, 10)
    p.end()
    return QIcon(pix)


# ── Workers ───────────────────────────────────────────────────────────────────

class _ConnectWorker(QObject):
    connected = pyqtSignal(str, object)
    failed    = pyqtSignal(str, str)

    def __init__(self, conn_name: str, config: dict):
        super().__init__()
        self._name   = conn_name
        self._config = config

    def run(self):
        try:
            import sqlalchemy
            from core.db_engine import DBEngine
            engine = DBEngine.get_engine(self._config)
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            self.connected.emit(self._name, engine)
        except Exception as exc:
            self.failed.emit(self._name, str(exc))


class _SchemaWorker(QObject):
    done  = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, engine, mode: str, db=None, table=None, schema=None):
        super().__init__()
        self._engine = engine
        self._mode   = mode
        self._db     = db
        self._table  = table
        self._schema = schema

    def run(self):
        from core.schema_loader import SchemaLoader
        try:
            if self._mode == "databases":
                self.done.emit(SchemaLoader.load_databases(self._engine))
            elif self._mode == "tables":
                self.done.emit(SchemaLoader.load_tables(self._engine, self._db))
            elif self._mode == "columns":
                self.done.emit(SchemaLoader.load_columns(
                    self._engine, self._table, schema=self._schema))
            elif self._mode == "views":
                self.done.emit(SchemaLoader.load_views(self._engine, self._db))
            elif self._mode in ("procedures", "functions"):
                rows = SchemaLoader.load_procedures(self._engine, self._db)
                if self._mode == "procedures":
                    self.done.emit([r for r in rows if r.get("type") != "function"])
                else:
                    self.done.emit([r for r in rows if r.get("type") == "function"])
        except Exception as exc:
            self.error.emit(str(exc))


# ── Tree helpers ──────────────────────────────────────────────────────────────

def _ph(parent: QTreeWidgetItem) -> QTreeWidgetItem:
    ph = QTreeWidgetItem(parent)
    ph.setText(0, "Carregando...")
    ph.setData(0, Qt.UserRole, {"type": "_placeholder"})
    ph.setDisabled(True)
    return ph


def _has_ph(item: QTreeWidgetItem) -> bool:
    return (item.childCount() == 1 and
            (item.child(0).data(0, Qt.UserRole) or {}).get("type") == "_placeholder")


def _folder_node(parent: QTreeWidgetItem, label: str) -> QTreeWidgetItem:
    node = QTreeWidgetItem(parent)
    node.setText(0, label)
    node.setIcon(0, _icon("folder"))
    return node


def _err_node(parent: QTreeWidgetItem, msg: str):
    node = QTreeWidgetItem(parent)
    node.setText(0, "! " + msg[:100])
    node.setForeground(0, QBrush(QColor("#f44747")))
    node.setData(0, Qt.UserRole, {"type": "_error"})


# ── Reorderable tree ──────────────────────────────────────────────────────────

class _DragTree(QTreeWidget):
    order_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self._dragging_top = False

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        self._dragging_top = item is not None and self.indexOfTopLevelItem(item) >= 0
        super().mousePressEvent(event)

    def dropEvent(self, event):
        target     = self.itemAt(event.pos())
        target_top = target is None or self.indexOfTopLevelItem(target) >= 0
        if self._dragging_top and target_top:
            super().dropEvent(event)
            self.order_changed.emit()
        else:
            event.ignore()


# ── Object Explorer ───────────────────────────────────────────────────────────

class ObjectExplorer(QWidget):
    open_table_requested  = pyqtSignal(str, str)          # legacy (sql, conn)
    open_query_requested  = pyqtSignal(str, str, str)     # (sql, conn, db)
    server_order_changed  = pyqtSignal(list)
    server_connected      = pyqtSignal(str, object)

    def __init__(self, connection_manager: "ConnectionManager", parent=None):
        super().__init__(parent)
        self.setObjectName("object_explorer")
        self._manager = connection_manager
        self._threads: list          = []
        self._workers: list          = []   # keep refs to prevent GC
        self._statuses: dict         = {}
        self._spin_idx: dict         = {}
        self._level_filters: dict    = {}
        self._server_items: dict     = {}

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(110)
        self._spin_timer.timeout.connect(self._tick_spinners)
        self._build_ui()

    def _build_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        header = QWidget(objectName="explorer_header")
        header.setFixedHeight(30)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(6, 0, 6, 0)
        lbl = QLabel("Pesquisador de Objetos", objectName="explorer_title")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        hl.addWidget(lbl)
        hl.addStretch()
        btn_ref = QPushButton("\u21ba")
        btn_ref.setObjectName("explorer_btn")
        btn_ref.setFixedSize(20, 20)
        btn_ref.setToolTip("Atualizar item selecionado")
        btn_ref.clicked.connect(self._refresh_selected)
        hl.addWidget(btn_ref)
        lo.addWidget(header)

        filter_bar = QWidget(objectName="explorer_filter_bar")
        filter_bar.setFixedHeight(28)
        fb = QHBoxLayout(filter_bar)
        fb.setContentsMargins(4, 2, 4, 2)
        fb.setSpacing(2)
        self._filter_edit = QLineEdit(objectName="filter_input")
        self._filter_edit.setPlaceholderText("Filtrar objetos...")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_global_filter)
        fb.addWidget(self._filter_edit)
        lo.addWidget(filter_bar)

        self._tree = _DragTree(self)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.order_changed.connect(self._on_order_changed)
        lo.addWidget(self._tree, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_server(self, conn_name: str, config: dict = None, auto_connect: bool = True):
        if conn_name in self._server_items:
            return
        alias = (config or {}).get("alias", "").strip() or conn_name
        root = QTreeWidgetItem()
        root.setText(0, alias)
        root.setToolTip(0, conn_name if alias != conn_name else "")
        root.setData(0, Qt.UserRole, {"type": "server", "conn": conn_name})
        self._tree.addTopLevelItem(root)
        self._server_items[conn_name] = root
        self._apply_status_visuals(root, "disconnected")

        db_folder = _folder_node(root, "Bancos de Dados")
        db_folder.setData(0, Qt.UserRole, {"type": "db_folder", "conn": conn_name})
        _ph(db_folder)

        if auto_connect and config:
            self._connect_async(conn_name, config)

    def apply_saved_order(self, order: list):
        if not order:
            return
        name_pos = {n: i for i, n in enumerate(order)}
        count    = self._tree.topLevelItemCount()
        items    = [self._tree.takeTopLevelItem(0) for _ in range(count)]
        items.sort(key=lambda it: name_pos.get(
            (it.data(0, Qt.UserRole) or {}).get("conn", ""), 9999))
        for item in items:
            self._tree.addTopLevelItem(item)
        for item in items:
            conn = (item.data(0, Qt.UserRole) or {}).get("conn", "")
            if conn:
                self._server_items[conn] = item

    def refresh_server(self, conn_name: str):
        item = self._server_items.get(conn_name)
        if item is None:
            return
        item.takeChildren()
        db_folder = _folder_node(item, "Bancos de Dados")
        db_folder.setData(0, Qt.UserRole, {"type": "db_folder", "conn": conn_name})
        _ph(db_folder)
        item.setExpanded(True)

    def reconnect_server(self, conn_name: str):
        cfg = self._manager.get_config(conn_name)
        if cfg:
            self._connect_async(conn_name, cfg)

    def current_server_order(self) -> list:
        order = []
        for i in range(self._tree.topLevelItemCount()):
            d = self._tree.topLevelItem(i).data(0, Qt.UserRole) or {}
            if d.get("conn"):
                order.append(d["conn"])
        return order

    # ── Async connection ──────────────────────────────────────────────────────

    def _connect_async(self, conn_name: str, config: dict):
        self._set_server_status(conn_name, "connecting")
        worker = _ConnectWorker(conn_name, config)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.connected.connect(self._on_connected)
        worker.failed.connect(self._on_connect_failed)
        worker.connected.connect(lambda *_: thread.quit())
        worker.failed.connect(lambda *_: thread.quit())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._workers.remove(worker)
                                if worker in self._workers else None)
        self._workers.append(worker)   # prevent GC while thread runs
        self._threads.append(thread)
        thread.start()
        QTimer.singleShot(2000, lambda: self._maybe_start_spin(conn_name))

    def _maybe_start_spin(self, conn_name: str):
        if self._statuses.get(conn_name) == "connecting":
            self._spin_idx.setdefault(conn_name, 0)
            if not self._spin_timer.isActive():
                self._spin_timer.start()

    def _tick_spinners(self):
        any_active = False
        for conn_name, idx in list(self._spin_idx.items()):
            if self._statuses.get(conn_name) != "connecting":
                continue
            item = self._server_items.get(conn_name)
            if item:
                frame = _SPINNER_FRAMES[idx % len(_SPINNER_FRAMES)]
                display = self._manager.get_display_name(conn_name)
                item.setText(0, frame + " " + display)
                self._spin_idx[conn_name] = idx + 1
            any_active = True
        if not any_active:
            self._spin_timer.stop()

    def _on_connected(self, conn_name: str, engine):
        self._spin_idx.pop(conn_name, None)
        self._manager.register_engine(conn_name, engine)
        self._set_server_status(conn_name, "connected")
        item = self._server_items.get(conn_name)
        if item:
            display = self._manager.get_display_name(conn_name)
            item.setText(0, display)
            tooltip = "Conectado"
            if display != conn_name:
                tooltip += "\n" + conn_name
            item.setToolTip(0, tooltip)
        self.server_connected.emit(conn_name, engine)

    def _on_connect_failed(self, conn_name: str, error: str):
        self._spin_idx.pop(conn_name, None)
        self._set_server_status(conn_name, "error")
        item = self._server_items.get(conn_name)
        if item:
            display = self._manager.get_display_name(conn_name)
            item.setText(0, display)
            item.setToolTip(0, "Erro de conexao:\n" + error)

    def _set_server_status(self, conn_name: str, status: str):
        self._statuses[conn_name] = status
        item = self._server_items.get(conn_name)
        if item:
            self._apply_status_visuals(item, status)

    @staticmethod
    def _apply_status_visuals(item: QTreeWidgetItem, status: str):
        color = _STATUS_COLORS.get(status, "#888888")
        item.setIcon(0, _dot_icon(color))
        fg = QColor(color) if status != "disconnected" else QColor("#cccccc")
        item.setForeground(0, QBrush(fg))
        item.setToolTip(0, {
            "connected":    "Conectado",
            "connecting":   "Conectando...",
            "error":        "Erro de conexao",
            "disconnected": "Desconectado",
        }.get(status, ""))

    # ── Async schema loading ──────────────────────────────────────────────────

    def _async_load(self, item: QTreeWidgetItem, mode: str, callback,
                    conn: str, db=None, table=None, schema=None):
        engine = self._manager.get_connection(conn)
        if engine is None:
            _err_node(item, "Sem conexao — clique com botao direito para reconectar")
            return
        _ph(item)
        worker = _SchemaWorker(engine, mode, db=db, table=table, schema=schema)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda r: self._finish_load(item, r, callback))
        worker.error.connect(lambda e: self._finish_error(item, e))
        worker.done.connect(lambda *_: thread.quit())
        worker.error.connect(lambda *_: thread.quit())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._workers.remove(worker)
                                if worker in self._workers else None)
        self._workers.append(worker)   # prevent GC while thread runs
        self._threads.append(thread)
        thread.start()

    def _finish_load(self, item: QTreeWidgetItem, result, callback):
        item.takeChildren()
        callback(item, result)

    def _finish_error(self, item: QTreeWidgetItem, error: str):
        item.takeChildren()
        _err_node(item, error)

    # ── Expansion ─────────────────────────────────────────────────────────────

    def _on_item_expanded(self, item: QTreeWidgetItem):
        if not _has_ph(item):
            return
        data = item.data(0, Qt.UserRole) or {}
        t    = data.get("type")
        conn = data.get("conn", "")
        db   = data.get("db")
        item.takeChildren()

        if t == "db_folder":
            self._async_load(item, "databases", self._populate_dbs, conn=conn)
        elif t == "database":
            self._populate_db_node(item, conn, db)
        elif t == "table_folder":
            self._async_load(item, "tables", self._populate_tables,
                             conn=conn, db=db)
        elif t == "col_folder":
            self._async_load(item, "columns", self._populate_columns,
                             conn=conn, db=db,
                             table=data.get("table"), schema=data.get("schema"))
        elif t == "view_folder":
            self._async_load(item, "views", self._populate_views,
                             conn=conn, db=db)
        elif t == "proc_folder":
            self._async_load(item, "procedures", self._populate_procs,
                             conn=conn, db=db)
        elif t == "func_folder":
            self._async_load(item, "functions", self._populate_procs,
                             conn=conn, db=db)

    # ── Populate callbacks ────────────────────────────────────────────────────

    def _populate_dbs(self, folder_item: QTreeWidgetItem, dbs: list):
        data = folder_item.data(0, Qt.UserRole) or {}
        conn = data.get("conn", "")
        lf   = self._level_filters.get(id(folder_item), "").lower()
        for db in dbs:
            if lf and lf not in db.lower():
                continue
            db_node = QTreeWidgetItem(folder_item)
            db_node.setText(0, db)
            db_node.setIcon(0, _icon("database"))
            db_node.setData(0, Qt.UserRole,
                            {"type": "database", "conn": conn, "db": db})
            _ph(db_node)

    def _populate_db_node(self, db_item: QTreeWidgetItem, conn: str, db: str):
        tbl_f = _folder_node(db_item, "Tabelas")
        tbl_f.setData(0, Qt.UserRole, {"type": "table_folder", "conn": conn, "db": db})
        _ph(tbl_f)
        view_f = _folder_node(db_item, "Views")
        view_f.setData(0, Qt.UserRole, {"type": "view_folder", "conn": conn, "db": db})
        _ph(view_f)
        prog_f = _folder_node(db_item, "Programabilidade")
        prog_f.setData(0, Qt.UserRole, {"type": "prog_folder", "conn": conn, "db": db})
        func_f = _folder_node(prog_f, "Funcoes")
        func_f.setData(0, Qt.UserRole, {"type": "func_folder", "conn": conn, "db": db})
        _ph(func_f)
        proc_f = _folder_node(prog_f, "Procedures")
        proc_f.setData(0, Qt.UserRole, {"type": "proc_folder", "conn": conn, "db": db})
        _ph(proc_f)

    def _populate_tables(self, folder_item: QTreeWidgetItem, tables: list):
        data = folder_item.data(0, Qt.UserRole) or {}
        conn = data.get("conn", "")
        db   = data.get("db", "")
        lf   = self._level_filters.get(id(folder_item), "").lower()
        for tbl in tables:
            schema = tbl.get("schema", "dbo")
            name   = tbl.get("name", "")
            label  = "{}.{}".format(schema, name)
            if lf and lf not in label.lower():
                continue
            tbl_node = QTreeWidgetItem(folder_item)
            tbl_node.setText(0, label)
            tbl_node.setIcon(0, _icon("table"))
            tbl_node.setData(0, Qt.UserRole, {
                "type": "table", "conn": conn, "db": db,
                "table": name, "schema": schema,
            })
            col_f = _folder_node(tbl_node, "Colunas")
            col_f.setData(0, Qt.UserRole, {
                "type": "col_folder", "conn": conn, "db": db,
                "table": name, "schema": schema,
            })
            _ph(col_f)
            _folder_node(tbl_node, "Indices")
            _folder_node(tbl_node, "Chaves")

    def _populate_columns(self, folder_item: QTreeWidgetItem, cols: list):
        for col in cols:
            pk   = col.get("pk", False)
            node = QTreeWidgetItem(folder_item)
            node.setText(0, "{} ({}){}".format(
                col["name"], col["type"], " (PK)" if pk else ""))
            node.setIcon(0, _icon("key") if pk else _icon("column"))
            node.setData(0, Qt.UserRole, {"type": "column"})

    def _populate_views(self, folder_item: QTreeWidgetItem, views: list):
        data = folder_item.data(0, Qt.UserRole) or {}
        conn = data.get("conn", "")
        db   = data.get("db", "")
        lf   = self._level_filters.get(id(folder_item), "").lower()
        for view in views:
            if isinstance(view, dict):
                schema = view.get("schema", "dbo")
                name   = view.get("name", "")
            else:
                parts  = str(view).split(".")
                schema = parts[0] if len(parts) > 1 else "dbo"
                name   = parts[-1]
            label = "{}.{}".format(schema, name)
            if lf and lf not in label.lower():
                continue
            node = QTreeWidgetItem(folder_item)
            node.setText(0, label)
            node.setIcon(0, _icon("view"))
            node.setData(0, Qt.UserRole, {
                "type": "view", "conn": conn, "db": db,
                "schema": schema, "name": name,
            })

    def _populate_procs(self, folder_item: QTreeWidgetItem, procs: list):
        data = folder_item.data(0, Qt.UserRole) or {}
        conn = data.get("conn", "")
        db   = data.get("db", "")
        lf   = self._level_filters.get(id(folder_item), "").lower()
        for proc in procs:
            schema  = proc.get("schema", "dbo")
            name    = proc.get("name", "")
            ptype   = proc.get("type", "procedure")  # "procedure" or "function"
            label   = "{}.{}".format(schema, name)
            if lf and lf not in label.lower():
                continue
            node = QTreeWidgetItem(folder_item)
            node.setText(0, label)
            node.setIcon(0, _icon("procedure"))
            node.setData(0, Qt.UserRole, {
                "type": "proc" if ptype != "function" else "func",
                "conn": conn, "db": db,
                "schema": schema, "name": name,
            })

    # ── Global filter ─────────────────────────────────────────────────────────

    def _apply_global_filter(self, text: str):
        text = text.lower()
        for i in range(self._tree.topLevelItemCount()):
            self._filter_recursive(self._tree.topLevelItem(i), text)

    def _filter_recursive(self, item: QTreeWidgetItem, text: str) -> bool:
        match       = not text or text in item.text(0).lower()
        child_match = any(
            self._filter_recursive(item.child(i), text)
            for i in range(item.childCount())
        )
        visible = match or child_match
        item.setHidden(not visible)
        return visible

    # ── Per-level filter ──────────────────────────────────────────────────────

    def _set_level_filter(self, item: QTreeWidgetItem):
        current  = self._level_filters.get(id(item), "")
        base_lbl = item.text(0).replace(" [F]", "")
        text, ok = QInputDialog.getText(
            self, "Filtrar nivel",
            'Filtrar filhos de "{}"\n(deixe vazio para limpar):'.format(base_lbl),
            text=current,
        )
        if not ok:
            return
        text = text.strip()
        if text:
            self._level_filters[id(item)] = text
            item.setText(0, "{} [F]".format(base_lbl))
        else:
            self._level_filters.pop(id(item), None)
            item.setText(0, base_lbl)
        self._refresh_folder(item)

    def _clear_level_filter(self, item: QTreeWidgetItem):
        self._level_filters.pop(id(item), None)
        item.setText(0, item.text(0).replace(" [F]", ""))
        self._refresh_folder(item)

    def _refresh_folder(self, item: QTreeWidgetItem):
        item.takeChildren()
        _ph(item)
        item.setExpanded(False)
        item.setExpanded(True)

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole) or {}
        t    = data.get("type", "")
        conn = data.get("conn", "")
        menu = QMenu(self)

        if t == "server":
            status = self._statuses.get(conn, "disconnected")
            if status in ("disconnected", "error"):
                act = QAction("Reconectar", self)
                act.triggered.connect(lambda: self.reconnect_server(conn))
                menu.addAction(act)
            act_ref = QAction("Atualizar", self)
            act_ref.triggered.connect(lambda: self.refresh_server(conn))
            menu.addAction(act_ref)
            # Server-level database filter
            db_folder = self._get_server_db_folder(item)
            if db_folder is not None:
                menu.addSeparator()
                act_filt = QAction("Filtrar bancos...", self)
                act_filt.triggered.connect(lambda _f=db_folder: self._set_level_filter(_f))
                menu.addAction(act_filt)
                if id(db_folder) in self._level_filters:
                    act_clr = QAction("Remover filtro de bancos", self)
                    act_clr.triggered.connect(lambda _f=db_folder: self._clear_level_filter(_f))
                    menu.addAction(act_clr)
            menu.addSeparator()
            top_idx = self._tree.indexOfTopLevelItem(item)
            act_up = QAction("Mover para cima", self)
            act_up.setEnabled(top_idx > 0)
            act_up.triggered.connect(lambda: self._move_server(item, -1))
            menu.addAction(act_up)
            act_dn = QAction("Mover para baixo", self)
            act_dn.setEnabled(top_idx < self._tree.topLevelItemCount() - 1)
            act_dn.triggered.connect(lambda: self._move_server(item, +1))
            menu.addAction(act_dn)
            menu.addSeparator()
            act_rm = QAction("Remover servidor", self)
            act_rm.triggered.connect(lambda: self._remove_server(item, conn))
            menu.addAction(act_rm)

        elif t in ("db_folder", "table_folder", "view_folder", "proc_folder", "func_folder"):
            act_filter = QAction("Filtrar nivel...", self)
            act_filter.triggered.connect(lambda: self._set_level_filter(item))
            menu.addAction(act_filter)
            if id(item) in self._level_filters:
                act_clear = QAction("Remover filtro", self)
                act_clear.triggered.connect(lambda: self._clear_level_filter(item))
                menu.addAction(act_clear)
            menu.addSeparator()
            act_ref = QAction("Atualizar", self)
            act_ref.triggered.connect(lambda: self._refresh_folder(item))
            menu.addAction(act_ref)

        elif t == "table":
            act_sel = QAction("Script como SELECT TOP 200", self)
            act_sel.triggered.connect(lambda: self._script_select(data))
            menu.addAction(act_sel)
            act_cnt = QAction("Script como SELECT COUNT(*)", self)
            act_cnt.triggered.connect(lambda: self._script_count(data))
            menu.addAction(act_cnt)

        elif t == "view":
            act_sel = QAction("Script como SELECT TOP 200", self)
            act_sel.triggered.connect(lambda: self._script_view_select(data))
            menu.addAction(act_sel)
            act_cnt = QAction("Script como SELECT COUNT(*)", self)
            act_cnt.triggered.connect(lambda: self._script_view_count(data))
            menu.addAction(act_cnt)
            menu.addSeparator()
            act_cr = QAction("Abrir como CREATE VIEW", self)
            act_cr.triggered.connect(lambda: self._open_as_definition(data, as_alter=False))
            menu.addAction(act_cr)
            act_al = QAction("Abrir como ALTER VIEW", self)
            act_al.triggered.connect(lambda: self._open_as_definition(data, as_alter=True))
            menu.addAction(act_al)

        elif t in ("proc", "func"):
            lbl = "Procedure" if t == "proc" else "Funcao"
            act_exec = QAction(f"Script EXEC {lbl}", self)
            act_exec.triggered.connect(lambda: self._script_proc_exec(data))
            menu.addAction(act_exec)
            menu.addSeparator()
            obj_kw = "PROCEDURE" if t == "proc" else "FUNCTION"
            act_cr = QAction(f"Abrir como CREATE {obj_kw}", self)
            act_cr.triggered.connect(lambda: self._open_as_definition(data, as_alter=False))
            menu.addAction(act_cr)
            act_al = QAction(f"Abrir como ALTER {obj_kw}", self)
            act_al.triggered.connect(lambda: self._open_as_definition(data, as_alter=True))
            menu.addAction(act_al)

        if not menu.isEmpty():
            menu.exec_(self._tree.viewport().mapToGlobal(pos))

    def _get_server_db_folder(self, server_item: QTreeWidgetItem):
        """Return the db_folder child of a server item, or None if not expanded."""
        for i in range(server_item.childCount()):
            child = server_item.child(i)
            cdata = child.data(0, Qt.UserRole) or {}
            if cdata.get("type") == "db_folder":
                return child
        return None

    def get_selected_context(self):
        """Return (conn_name, db_name) from the currently selected tree item, or (None, None)."""
        item = self._tree.currentItem()
        if item is None:
            return None, None
        data = item.data(0, Qt.UserRole) or {}
        conn = data.get("conn") or None
        db   = data.get("db") or None
        return conn, db

    def _move_server(self, item: QTreeWidgetItem, direction: int):
        idx     = self._tree.indexOfTopLevelItem(item)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= self._tree.topLevelItemCount():
            return
        self._tree.takeTopLevelItem(idx)
        self._tree.insertTopLevelItem(new_idx, item)
        self._tree.setCurrentItem(item)
        self._on_order_changed()

    def _remove_server(self, item: QTreeWidgetItem, conn: str):
        reply = QMessageBox.question(
            self, "Remover servidor",
            "Remover '{}' do Pesquisador?".format(conn),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            idx = self._tree.indexOfTopLevelItem(item)
            self._tree.takeTopLevelItem(idx)
            self._server_items.pop(conn, None)
            self._statuses.pop(conn, None)
            self._on_order_changed()

    def _on_order_changed(self):
        self.server_order_changed.emit(self.current_server_order())

    def _refresh_selected(self):
        item = self._tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.UserRole) or {}
        t    = data.get("type")
        conn = data.get("conn", "")
        if t == "server":
            self.refresh_server(conn)
        elif t in ("db_folder", "table_folder", "view_folder", "col_folder"):
            self._refresh_folder(item)

    def _script_select(self, data: dict):
        schema = data.get("schema", "dbo")
        table  = data.get("table", "")
        conn   = data.get("conn", "")
        db     = data.get("db", "")
        sql    = "SELECT TOP 200 *\nFROM {}.{}".format(schema, table)
        self.open_query_requested.emit(sql, conn, db)
        self.open_table_requested.emit(sql, conn)  # legacy

    def _script_count(self, data: dict):
        schema = data.get("schema", "dbo")
        table  = data.get("table", "")
        conn   = data.get("conn", "")
        db     = data.get("db", "")
        sql    = "SELECT COUNT(*) AS total\nFROM {}.{}".format(schema, table)
        self.open_query_requested.emit(sql, conn, db)
        self.open_table_requested.emit(sql, conn)  # legacy

    def _script_view_select(self, data: dict):
        schema = data.get("schema", "dbo")
        name   = data.get("name", "")
        conn   = data.get("conn", "")
        db     = data.get("db", "")
        sql    = "SELECT TOP 200 *\nFROM {}.{}".format(schema, name)
        self.open_query_requested.emit(sql, conn, db)

    def _script_view_count(self, data: dict):
        schema = data.get("schema", "dbo")
        name   = data.get("name", "")
        conn   = data.get("conn", "")
        db     = data.get("db", "")
        sql    = "SELECT COUNT(*) AS total\nFROM {}.{}".format(schema, name)
        self.open_query_requested.emit(sql, conn, db)

    def _script_proc_exec(self, data: dict):
        schema = data.get("schema", "dbo")
        name   = data.get("name", "")
        conn   = data.get("conn", "")
        db     = data.get("db", "")
        sql    = "EXEC {}.{}".format(schema, name)
        self.open_query_requested.emit(sql, conn, db)

    def _open_as_definition(self, data: dict, as_alter: bool):
        """Async-fetch the CREATE definition of a view/proc/func and open it in a new tab."""
        schema = data.get("schema", "dbo")
        name   = data.get("name", "")
        conn   = data.get("conn", "")
        db     = data.get("db", "")

        def _on_definition(defn: str):
            if not defn:
                QMessageBox.warning(
                    self, "Definicao",
                    "Nao foi possivel obter a definicao de '{}.{}'.".
                    format(schema, name))
                return
            if as_alter:
                defn = re.sub(r'\bCREATE\b', 'ALTER', defn, count=1,
                              flags=re.IGNORECASE)
            self.open_query_requested.emit(defn, conn, db)

        self._async_fetch_definition(conn, db, schema, name, _on_definition)

    def _async_fetch_definition(self, conn: str, db: str, schema: str,
                                 name: str, callback):
        """Run SchemaLoader.load_definition in a background thread, call callback(str)."""
        engine = self._manager.get_connection(conn)
        if engine is None:
            return

        class _DefWorker(QObject):
            done  = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self_, eng, db_, schema_, name_):  # noqa: N805
                super().__init__()
                self_._engine = eng
                self_._db     = db_
                self_._schema = schema_
                self_._name   = name_

            def run(self_):  # noqa: N805
                from core.schema_loader import SchemaLoader
                try:
                    defn = SchemaLoader.load_definition(
                        self_._engine, self_._schema, self_._name, self_._db)
                    self_.done.emit(defn or "")
                except Exception as exc:
                    self_.error.emit(str(exc))

        worker = _DefWorker(engine, db, schema, name)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(callback)
        worker.error.connect(lambda e: QMessageBox.warning(self, "Erro", e))
        worker.done.connect(lambda *_: thread.quit())
        worker.error.connect(lambda *_: thread.quit())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda: self._workers.remove(worker)
            if worker in self._workers else None)
        self._workers.append(worker)
        thread.start()

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.UserRole) or {}
        t    = data.get("type")
        if t == "table":
            self._script_select(data)
        elif t == "view":
            self._script_view_select(data)
        elif t == "proc":
            self._script_proc_exec(data)
