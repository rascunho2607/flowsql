from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QMenuBar, QMenu, QAction, QToolBar, QToolButton, QComboBox,
    QSplitter, QTabWidget, QTabBar, QPushButton, QCheckBox,
    QSizePolicy, QMessageBox, QFileDialog, QShortcut
)
from PyQt5.QtCore import Qt, QPoint, QSize
from PyQt5.QtGui import QFont, QIcon, QKeySequence

from app.connection_dialog import ConnectionDialog
from app.object_explorer import ObjectExplorer
from app.settings_dialog import SettingsDialog
from app.status_bar import StatusBar
from app.sql_editor_tab import SqlEditorTab
from app.query_history import QueryHistoryDock
from app.flow_builder_tab import FlowBuilderTab
from core.connection_manager import ConnectionManager
from core.settings_manager import SettingsManager
from themes.theme_manager import ThemeManager

ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"


def _icon(name: str) -> QIcon:
    path = ICONS_DIR / f"{name}.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon()


class MainWindow(QMainWindow):
    """Main application window — layout identical to SSMS."""

    def __init__(self, app, theme_manager: ThemeManager):
        super().__init__()
        self._app = app
        self._theme_manager = theme_manager
        self._conn_manager = ConnectionManager()
        self._settings = SettingsManager()
        self._query_counter = 0
        self._current_theme = "dark"
        self._schema_words_cache: dict = {}  # conn_name -> list[str]

        self.setWindowTitle("FlowSQL — Microsoft SQL Server Management Studio")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 800)

        # Remove native title bar so we draw a custom one
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        self._drag_pos = None

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_connection_bar()
        self._build_central()
        self._build_status_bar()
        self._build_history_dock()
        self._register_shortcuts()
        self._refresh_connection_combos()
        self._auto_connect_all()     # async-connect all saved servers on startup

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        """Build the outer shell: custom title bar + content area."""
        # Central container that will hold everything
        self._root = QWidget()
        self.setCentralWidget(self._root)

        self._root_layout = QVBoxLayout(self._root)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # ── Custom Title Bar ─────────────────────────────────────────────────
        self._titlebar = QWidget()
        self._titlebar.setFixedHeight(32)
        self._titlebar.setStyleSheet(
            "background-color: #007acc;"
        )
        tb_layout = QHBoxLayout(self._titlebar)
        tb_layout.setContentsMargins(10, 0, 4, 0)
        tb_layout.setSpacing(0)

        lbl_title = QLabel("FlowSQL — Microsoft SQL Server Management Studio")
        lbl_title.setStyleSheet("color: #ffffff; font-size: 12px; background: transparent;")

        btn_min = QPushButton("─")
        btn_max = QPushButton("□")
        btn_close_tb = QPushButton("✕")
        for btn in (btn_min, btn_max, btn_close_tb):
            btn.setFixedSize(46, 32)
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: white; border: none; font-size: 13px; }"
                "QPushButton:hover { background: #005a9e; }"
            )
        btn_close_tb.setStyleSheet(
            "QPushButton { background: transparent; color: white; border: none; font-size: 13px; }"
            "QPushButton:hover { background: #c42b1c; }"
        )
        btn_min.clicked.connect(self.showMinimized)
        btn_max.clicked.connect(self._toggle_maximize)
        btn_close_tb.clicked.connect(self.close)

        tb_layout.addWidget(lbl_title)
        tb_layout.addStretch()
        tb_layout.addWidget(btn_min)
        tb_layout.addWidget(btn_max)
        tb_layout.addWidget(btn_close_tb)

        # Drag support
        self._titlebar.mousePressEvent = self._tb_mouse_press
        self._titlebar.mouseMoveEvent = self._tb_mouse_move
        self._titlebar.mouseDoubleClickEvent = self._tb_double_click

        self._root_layout.addWidget(self._titlebar)

        # Content area (below title bar)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._root_layout.addWidget(self._content, 1)

    def _build_menu(self):
        menubar = QMenuBar()
        menubar.setObjectName("main_menubar")

        # File menu
        m_file = menubar.addMenu("Arquivo")
        m_file.addAction(self._act("Nova Consulta", self._new_query_tab, "Ctrl+N"))
        m_file.addAction(self._act("Abrir SQL...", self._open_sql_file, "Ctrl+O"))
        m_file.addAction(self._act("Salvar SQL...", self._save_sql_file, "Ctrl+S"))
        m_file.addSeparator()
        m_file.addAction(self._act("Nova Conexão", self._open_connection_dialog))
        m_file.addAction(self._act("Desconectar", None))
        m_file.addSeparator()
        m_file.addAction(self._act("Sair", self.close))

        # Edit menu
        m_edit = menubar.addMenu("Editar")
        m_edit.addAction(self._act("Desfazer", lambda: self._active_editor_call("undo"), "Ctrl+Z"))
        m_edit.addAction(self._act("Refazer", lambda: self._active_editor_call("redo"), "Ctrl+Y"))
        m_edit.addSeparator()
        m_edit.addAction(self._act("Recortar", lambda: self._active_editor_call("cut"), "Ctrl+X"))
        m_edit.addAction(self._act("Copiar", lambda: self._active_editor_call("copy"), "Ctrl+C"))
        m_edit.addAction(self._act("Colar", lambda: self._active_editor_call("paste"), "Ctrl+V"))
        m_edit.addSeparator()
        m_edit.addAction(self._act("Selecionar Tudo", lambda: self._active_editor_call("selectAll"), "Ctrl+A"))
        m_edit.addAction(self._act("Comentar Seleção", self._comment_selection))
        m_edit.addAction(self._act("Descomentar Seleção", self._uncomment_selection))

        # View menu
        m_view = menubar.addMenu("Exibir")
        m_view.addAction(self._act("Pesquisador de Objetos", None))
        m_view.addAction(self._act("Histórico de Consultas", self._toggle_history_dock))
        m_view.addSeparator()
        m_view.addAction(self._act("Tema Escuro", lambda: self._apply_theme("dark")))
        m_view.addAction(self._act("Tema Claro", lambda: self._apply_theme("light")))
        m_view.addSeparator()
        m_view.addAction(self._act("★ Orange Pulse", lambda: self._apply_theme("orange")))
        m_view.addAction(self._act("★ Dracula Pro", lambda: self._apply_theme("dracula")))
        m_view.addAction(self._act("★ Neon Cyber", lambda: self._apply_theme("neon")))
        m_view.addAction(self._act("★ Blueprint Pro", lambda: self._apply_theme("blueprint")))
        m_view.addAction(self._act("★ Data Stream", lambda: self._apply_theme("datastream")))
        m_view.addAction(self._act("★ Neural Flow", lambda: self._apply_theme("neural")))
        m_view.addAction(self._act("★ Matrix Core", lambda: self._apply_theme("matrix")))
        m_view.addAction(self._act("★ Deep Space", lambda: self._apply_theme("deepspace")))
        m_view.addAction(self._act("★ Synthwave X", lambda: self._apply_theme("synthwave")))
        m_view.addAction(self._act("★ Lava / Inferno", lambda: self._apply_theme("lava")))
        m_view.addAction(self._act("★ Industrial Metal", lambda: self._apply_theme("industrial")))
        m_view.addAction(self._act("★ Frost UI", lambda: self._apply_theme("frost")))
        m_view.addAction(self._act("★ Nature Tech", lambda: self._apply_theme("nature")))

        # Query menu
        m_query = menubar.addMenu("Consulta")
        m_query.addAction(self._act("Executar", self._execute_current, "F5"))
        m_query.addAction(self._act("Cancelar Execução", self._cancel_current))
        m_query.addSeparator()
        m_query.addAction(self._act("Formatar SQL", self._format_current))
        m_query.addAction(self._act("Explicar Consulta", self._explain_current))

        # Other menus (stubs)
        menubar.addMenu("Projeto")
        m_tools = menubar.addMenu("Ferramentas")
        m_tools.addAction(self._act("Opções...", self._open_settings))
        menubar.addMenu("Janela").addAction(self._act("Nova Janela", None))
        m_help = menubar.addMenu("Ajuda")
        m_help.addAction(self._act("Sobre", self._show_about))

        menubar.setCornerWidget(self._build_theme_toggle(), Qt.TopRightCorner)

        self._content_layout.addWidget(menubar)
        self._menubar = menubar

    def _act(self, label: str, slot, shortcut: str = None) -> QAction:
        action = QAction(label, self)
        if slot:
            action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_theme_toggle(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(4)

        lbl_dark = QLabel("Escuro")
        lbl_dark.setObjectName("secondary_label")

        self._theme_toggle = QCheckBox()
        self._theme_toggle.setObjectName("theme_toggle")
        self._theme_toggle.setChecked(False)  # dark = unchecked
        self._theme_toggle.toggled.connect(self._on_theme_toggle)

        lbl_light = QLabel("Claro")
        lbl_light.setObjectName("secondary_label")

        layout.addWidget(lbl_dark)
        layout.addWidget(self._theme_toggle)
        layout.addWidget(lbl_light)
        return container

    def _build_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setFixedHeight(34)
        toolbar.setObjectName("main_toolbar")

        btn_new = QToolButton()
        btn_new.setObjectName("btn_new_connection")
        btn_new.setText("  Nova Conexão")
        btn_new.setIcon(_icon("server"))
        btn_new.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_new.clicked.connect(self._open_connection_dialog)
        toolbar.addWidget(btn_new)

        toolbar.addSeparator()

        btn_new_q = QToolButton()
        btn_new_q.setText("  Nova Consulta")
        btn_new_q.setIcon(_icon("table"))
        btn_new_q.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_new_q.clicked.connect(self._new_query_tab)
        toolbar.addWidget(btn_new_q)

        btn_open = QToolButton()
        btn_open.setText("  Abrir")
        btn_open.setIcon(_icon("folder"))
        btn_open.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_open.clicked.connect(self._open_sql_file)
        toolbar.addWidget(btn_open)

        btn_save = QToolButton()
        btn_save.setText("  Salvar")
        btn_save.setIcon(_icon("save"))
        btn_save.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_save.clicked.connect(self._save_sql_file)
        toolbar.addWidget(btn_save)

        toolbar.addSeparator()

        btn_run = QToolButton()
        btn_run.setText("  Executar")
        btn_run.setIcon(_icon("play"))
        btn_run.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_run.clicked.connect(self._execute_current)
        toolbar.addWidget(btn_run)

        btn_stop = QToolButton()
        btn_stop.setText("  Cancelar")
        btn_stop.setIcon(_icon("stop"))
        btn_stop.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_stop.clicked.connect(self._cancel_current)
        toolbar.addWidget(btn_stop)

        toolbar.addSeparator()

        btn_flow = QToolButton()
        btn_flow.setText("  Flow Builder")
        btn_flow.setIcon(_icon("flow"))
        btn_flow.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn_flow.clicked.connect(self._open_flow_builder_tab)
        toolbar.addWidget(btn_flow)

        self._content_layout.addWidget(toolbar)
        self._toolbar = toolbar

    def _build_connection_bar(self):
        bar = QWidget(objectName="connection_bar")
        bar.setFixedHeight(30)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        lbl_conn = QLabel("Conexão:")
        self._cmb_connections = QComboBox()
        self._cmb_connections.setMinimumWidth(160)
        self._cmb_connections.currentTextChanged.connect(self._on_connection_selected)

        lbl_db = QLabel("Banco:")
        self._cmb_databases = QComboBox()
        self._cmb_databases.setMinimumWidth(120)
        self._cmb_databases.currentTextChanged.connect(self._on_database_selected)

        layout.addWidget(lbl_conn)
        layout.addWidget(self._cmb_connections)
        layout.addWidget(lbl_db)
        layout.addWidget(self._cmb_databases)
        layout.addStretch()

        self._content_layout.addWidget(bar)

    def _build_central(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)

        # Object Explorer
        self._explorer = ObjectExplorer(self._conn_manager)
        self._explorer.setMinimumWidth(180)
        self._explorer.open_table_requested.connect(self._on_open_table)
        self._explorer.open_query_requested.connect(self._on_open_query)
        self._explorer.server_connected.connect(self._on_server_connected)
        self._explorer.server_order_changed.connect(
            self._conn_manager.save_server_order)
        splitter.addWidget(self._explorer)
        splitter.setCollapsible(0, False)

        # Main content tabs
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.setMovable(True)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # "+" button to add new tab
        self._btn_add_tab = QPushButton("+")
        self._btn_add_tab.setFixedSize(24, 24)
        self._btn_add_tab.setToolTip("Nova Consulta (Ctrl+N)")
        self._btn_add_tab.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 16px; color: #a0a0a0; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        self._btn_add_tab.clicked.connect(self._new_query_tab)
        self._tabs.setCornerWidget(self._btn_add_tab, Qt.TopRightCorner)

        # Welcome placeholder
        self._add_welcome_tab()

        splitter.addWidget(self._tabs)
        splitter.setCollapsible(1, False)
        splitter.setSizes([220, 860])

        self._content_layout.addWidget(splitter, 1)
        self._splitter = splitter

    def _add_welcome_tab(self):
        placeholder = QLabel(
            "Conecte-se a um servidor para começar\n\n"
            "Use  Nova Conexão  para adicionar um banco de dados\n"
            "ou  Ctrl+N  para abrir um editor SQL vazio."
        )
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("placeholder_label")
        idx = self._tabs.addTab(placeholder, "Início")
        self._tabs.tabBar().setTabButton(idx, QTabBar.RightSide, None)

    def _build_status_bar(self):
        self._status = StatusBar(self)
        self._content_layout.addWidget(self._status)

    def _build_history_dock(self):
        self._history_dock = QueryHistoryDock(self)
        self._history_dock.open_query.connect(self._open_query_from_history)
        self.addDockWidget(Qt.RightDockWidgetArea, self._history_dock)
        self._history_dock.hide()

    def _register_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._comment_selection)

    # ── Tab management ────────────────────────────────────────────────────────

    def _new_query_tab(self, sql: str = "", title: str = "",
                        conn_name: str = "", db_name: str = "") -> "SqlEditorTab":
        self._query_counter += 1
        tab_name = title or f"Query{self._query_counter}.sql"

        # Apply BEGIN/ROLLBACK template for brand-new (empty) queries
        if not sql and self._settings.get("new_query_template", True):
            sql = "BEGIN TRANSACTION\n\n\n\nROLLBACK"

        # Prefer explicitly passed context, then explorer selection, then combos
        if not conn_name or not db_name:
            exp_conn, exp_db = self._explorer.get_selected_context()
            if not conn_name:
                conn_name = exp_conn or self._current_conn_name()
            if not db_name:
                db_name = exp_db or self._cmb_databases.currentText()

        engine = self._conn_manager.get_connection(conn_name)

        # For MSSQL (and any odbc_connect-based URL): create a db-specific engine
        # so that user queries run in the correct database, not the server default.
        if engine is not None and db_name:
            from core.schema_loader import SchemaLoader
            db_engine = SchemaLoader._engine_for_db(engine, db_name)
            if db_engine is not None:
                engine = db_engine
                tab_owns_engine = True
            else:
                tab_owns_engine = False
        else:
            tab_owns_engine = False

        tab = SqlEditorTab(
            tab_name=tab_name,
            engine=engine,
            conn_name=conn_name,
            db_name=db_name,
            initial_sql=sql,
            parent=self,
        )
        tab._owns_engine = tab_owns_engine
        tab.set_theme(self._current_theme)
        # Push settings to the editor
        tab.set_autocomplete_enabled(self._settings.get("autocomplete_enabled", True))
        tab.set_syntax_check_enabled(self._settings.get("syntax_check_enabled", True))
        tab.set_object_check_enabled(self._settings.get("object_check_enabled", True))
        tab.set_autocorrect_syntax_enabled(self._settings.get("autocorrect_syntax_enabled", True))
        tab.set_autocorrect_objects_enabled(self._settings.get("autocorrect_objects_enabled", True))
        # Push cached schema words if available (prefer db-specific cache)
        cache_key = f"{conn_name}/{db_name}" if db_name else conn_name
        cached = (self._schema_words_cache.get(cache_key)
                  or self._schema_words_cache.get(conn_name))
        if cached:
            # cache stores (obj_words, all_words) tuple; legacy entries may be plain list
            if isinstance(cached, tuple):
                obj_words, all_words = cached
            else:
                obj_words = cached
                all_words = cached
            tab.set_schema_words(all_words)
            tab.set_object_words(obj_words)
        elif conn_name and db_name:
            # Trigger a load if not cached yet
            engine_for_words = self._conn_manager.get_connection(conn_name)
            if engine_for_words:
                self._load_schema_words_async(conn_name, engine_for_words, db_name)
        tab.title_changed.connect(lambda t, _tab=tab: self._update_tab_title(_tab, t))
        tab.open_query_in_new_tab.connect(self._open_query_from_history)

        idx = self._tabs.addTab(tab, tab_name)
        # Label and tooltip both show server / database
        conn_label = "{} / {}".format(conn_name, db_name) if conn_name else tab_name
        self._tabs.setTabText(idx, conn_label)
        self._tabs.tabBar().setTabToolTip(idx, conn_label)
        self._tabs.setCurrentIndex(idx)
        return tab

    def _close_tab(self, index: int):
        widget = self._tabs.widget(index)
        if isinstance(widget, SqlEditorTab) and widget.is_modified:
            reply = QMessageBox.question(
                self, "Fechar aba",
                f"'{widget.tab_name}' tem alterações não salvas. Fechar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        # Dispose tab-owned db engine to release the connection
        if isinstance(widget, SqlEditorTab) and getattr(widget, "_owns_engine", False):
            try:
                widget._engine.dispose()
            except Exception:
                pass
        if isinstance(widget, FlowBuilderTab) and getattr(widget, "_owns_engine", False):
            try:
                widget._engine.dispose()
            except Exception:
                pass
        self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self._add_welcome_tab()

    def _update_tab_title(self, tab: "SqlEditorTab", title: str):
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is tab:
                conn = tab._conn_name
                db   = tab._db_name
                label = "{} / {}".format(conn, db) if conn else title
                self._tabs.setTabText(i, label)
                self._tabs.tabBar().setTabToolTip(i, label)
                break

    def _current_editor_tab(self) -> "SqlEditorTab | None":
        w = self._tabs.currentWidget()
        return w if isinstance(w, SqlEditorTab) else None

    def _current_conn_name(self) -> str:
        """Return the real connection name (key) from the combo, honouring alias userData."""
        data = self._cmb_connections.currentData()
        return data if data else self._cmb_connections.currentText()

    def _active_editor_call(self, method: str):
        tab = self._current_editor_tab()
        if tab:
            getattr(tab._editor, method)()

    # ── Query actions ─────────────────────────────────────────────────────────

    def _execute_current(self):
        tab = self._current_editor_tab()
        if tab:
            tab._run_query()

    def _cancel_current(self):
        tab = self._current_editor_tab()
        if tab:
            tab._cancel_query()

    def _format_current(self):
        tab = self._current_editor_tab()
        if tab:
            tab._format_sql()

    def _explain_current(self):
        tab = self._current_editor_tab()
        if tab:
            tab._explain_query()

    def _comment_selection(self):
        tab = self._current_editor_tab()
        if tab:
            tab._editor.comment_selection()

    def _uncomment_selection(self):
        tab = self._current_editor_tab()
        if tab:
            tab._editor.uncomment_selection()

    # ── Connection / navigation actions ───────────────────────────────────────

    def _open_connection_dialog(self):
        history = self._conn_manager.list_saved_configs()
        dlg = ConnectionDialog(self, history=history)
        if dlg.exec_() == ConnectionDialog.Accepted:
            cfg = dlg.get_config()
            if cfg is None:
                return
            name = cfg.get("name") or cfg.get("host", "server")
            # Save config immediately; actual connection happens async via explorer
            self._conn_manager.add_config_only(name, cfg)
            self._explorer.add_server(name, cfg, auto_connect=True)
            self._refresh_connection_combos()
            self._status.set_server(name)
            self._status.set_user(cfg.get("user", ""))
            self._status.set_message(f"Conectando a {name}…")

    def _on_server_connected(self, conn_name: str, engine):
        """Called when explorer successfully connects to a server."""
        self._refresh_connection_combos()
        self._status.set_server(conn_name)
        self._status.set_message(f"Conectado a {self._conn_manager.get_display_name(conn_name)}")
        # Select the newly connected server in the combo
        for i in range(self._cmb_connections.count()):
            if self._cmb_connections.itemData(i) == conn_name:
                if self._cmb_connections.currentIndex() != i:
                    self._cmb_connections.setCurrentIndex(i)
                break
        cfg = self._conn_manager.get_config(conn_name)
        if cfg:
            self._status.set_user(cfg.get("user", ""))
        # Load databases for the combo
        self._load_databases_for(conn_name)
        # Load schema words for autocomplete asynchronously
        self._load_schema_words_async(conn_name, engine)

    def _auto_connect_all(self):
        """On startup: add all saved servers to explorer and connect async."""
        saved = self._conn_manager.list_connections()
        if not saved:
            return
        order = self._conn_manager.load_server_order()
        # Apply saved order (servers not in order list come last)
        ordered = sorted(saved, key=lambda n: order.index(n)
                         if n in order else len(order))
        for name in ordered:
            cfg = self._conn_manager.get_config(name)
            if cfg:
                self._explorer.add_server(name, cfg, auto_connect=True)
        self._refresh_connection_combos()

    def _on_theme_toggle(self, checked: bool):
        self._apply_theme("light" if checked else "dark")

    def _open_flow_builder_tab(self):
        """Open a new Flow Builder tab with the current connection."""
        # Use explorer selection first, fall back to combos
        exp_conn, exp_db = self._explorer.get_selected_context()
        conn_name = exp_conn or self._current_conn_name()
        db_name   = exp_db  or self._cmb_databases.currentText()
        engine    = self._conn_manager.get_connection(conn_name)
        tab_owns_engine = False
        if engine is not None and db_name:
            from core.schema_loader import SchemaLoader
            db_engine = SchemaLoader._engine_for_db(engine, db_name)
            if db_engine is not None:
                engine = db_engine
                tab_owns_engine = True
        cfg       = self._conn_manager.get_config(conn_name) or {}
        # Detect dialect from driver type
        db_type   = cfg.get("type", "postgresql").lower()
        dialect_map = {
            "mssql":      "mssql",
            "mysql":      "mysql",
            "sqlite":     "sqlite",
            "postgresql": "postgresql",
            "postgres":   "postgresql",
        }
        dialect = dialect_map.get(db_type, "postgresql")

        flow_tab = FlowBuilderTab(
            engine    = engine,
            conn_name = conn_name,
            db_name   = db_name,
            dialect   = dialect,
            parent    = self,
        )
        flow_tab._owns_engine = tab_owns_engine
        flow_tab.set_theme(self._current_theme)
        flow_tab.open_sql_in_editor.connect(self._new_query_tab)
        flow_tab.execute_sql.connect(self._run_sql_on_current_connection)

        self._flow_builder_counter = getattr(self, "_flow_builder_counter", 0) + 1
        label = "Flow {} — {} / {}".format(self._flow_builder_counter, conn_name, db_name) if conn_name else f"Flow {self._flow_builder_counter}"
        idx = self._tabs.addTab(flow_tab, label)
        self._tabs.tabBar().setTabToolTip(idx, label)
        self._tabs.setCurrentIndex(idx)

    def _run_sql_on_current_connection(self, sql: str):
        """Open a new query tab and run SQL immediately."""
        tab = self._new_query_tab(sql=sql)
        tab._run_query()

    def _apply_theme(self, theme: str):
        self._current_theme = theme
        self._theme_manager.apply_theme(theme)
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, SqlEditorTab):
                w.set_theme(theme)
            elif isinstance(w, FlowBuilderTab):
                w.set_theme(theme)

    def _on_connection_selected(self, name: str):
        if not name:
            return
        conn_name = self._current_conn_name()
        self._status.set_server(conn_name)
        cfg = self._conn_manager.get_config(conn_name)
        if cfg:
            self._status.set_user(cfg.get("user", ""))
        self._load_databases_for(conn_name)
        self._update_current_tab_engine()

    def _on_database_selected(self, db: str):
        self._status.set_database(db)
        self._update_current_tab_engine()
        # Load schema words for the selected database
        if db:
            conn = self._current_conn_name()
            engine = self._conn_manager.get_connection(conn)
            if engine and conn:
                self._load_schema_words_async(conn, engine, db)

    def _on_tab_changed(self, index: int):
        tab = self._current_editor_tab()
        if tab:
            self._status.set_message(tab.tab_name)
            # Sync dropdowns to the tab's own connection (block signals to avoid cascade)
            if tab._conn_name:
                self._cmb_connections.blockSignals(True)
                # Find by UserRole data (real conn_name)
                for i in range(self._cmb_connections.count()):
                    if self._cmb_connections.itemData(i) == tab._conn_name:
                        self._cmb_connections.setCurrentIndex(i)
                        break
                self._cmb_connections.blockSignals(False)
            if tab._db_name:
                self._cmb_databases.blockSignals(True)
                didx = self._cmb_databases.findText(tab._db_name)
                if didx >= 0:
                    self._cmb_databases.setCurrentIndex(didx)
                else:
                    # db not in list yet — add temporarily
                    self._cmb_databases.addItem(tab._db_name)
                    self._cmb_databases.setCurrentText(tab._db_name)
                self._cmb_databases.blockSignals(False)

    def _on_open_table(self, sql: str, conn: str):
        table_name = sql.split("FROM")[-1].strip() if "FROM" in sql else "query"
        safe_name = table_name.replace(".", "_").replace(" ", "")[:20] + ".sql"
        self._new_query_tab(sql=sql, title=safe_name, conn_name=conn)

    def _on_open_query(self, sql: str, conn: str, db: str):
        table_name = sql.split("FROM")[-1].strip() if "FROM" in sql else "query"
        safe_name = table_name.replace(".", "_").replace(" ", "")[:20] + ".sql"
        self._new_query_tab(sql=sql, title=safe_name, conn_name=conn, db_name=db)

    def _open_query_from_history(self, sql: str):
        self._new_query_tab(sql=sql)

    def _toggle_history_dock(self):
        if self._history_dock.isVisible():
            self._history_dock.hide()
        else:
            self._history_dock.show()

    def _update_current_tab_engine(self):
        tab = self._tabs.currentWidget()
        conn = self._current_conn_name()
        db = self._cmb_databases.currentText()
        engine = self._conn_manager.get_connection(conn)

        if engine is not None and db:
            from core.schema_loader import SchemaLoader
            db_engine = SchemaLoader._engine_for_db(engine, db)
            if db_engine is not None:
                engine = db_engine

        if isinstance(tab, SqlEditorTab):
            tab.set_engine(engine, conn, db)
        elif isinstance(tab, FlowBuilderTab):
            tab.set_engine(engine, conn, db)

    def _load_databases_for(self, conn_name: str):
        """Load databases asynchronously and populate the combo box."""
        engine = self._conn_manager.get_connection(conn_name)
        if engine is None:
            return
        from PyQt5.QtCore import QThread, QObject, pyqtSignal as _sig

        class _DbLoader(QObject):
            done  = _sig(list)
            error = _sig(str)
            def __init__(self, eng):
                super().__init__()
                self._eng = eng
            def run(self):
                try:
                    from core.schema_loader import SchemaLoader
                    self.done.emit(SchemaLoader.load_databases(self._eng))
                except Exception as exc:
                    self.error.emit(str(exc))

        worker = _DbLoader(engine)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda dbs: self._populate_db_combo(dbs))
        worker.done.connect(lambda *_: thread.quit())
        worker.error.connect(lambda *_: thread.quit())
        thread.finished.connect(thread.deleteLater)
        # Keep worker alive until thread finishes
        if not hasattr(self, "_db_workers"):
            self._db_workers = []
        self._db_workers.append(worker)
        thread.finished.connect(lambda: self._db_workers.remove(worker)
                                if worker in self._db_workers else None)
        thread.start()

    def _populate_db_combo(self, dbs: list):
        self._cmb_databases.blockSignals(True)
        self._cmb_databases.clear()
        for db in dbs:
            self._cmb_databases.addItem(db)
        self._cmb_databases.blockSignals(False)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _open_sql_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir arquivo SQL", "",
            "SQL Files (*.sql);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()
            from pathlib import Path as _Path
            self._new_query_tab(sql=sql, title=_Path(path).name)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao abrir", str(exc))

    def _save_sql_file(self):
        tab = self._current_editor_tab()
        if tab is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar SQL", tab.tab_name.lstrip("*"),
            "SQL Files (*.sql);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(tab.get_sql())
            tab.mark_saved()
            self._status.set_message(f"Salvo: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))

    def _refresh_connection_combos(self):
        self._cmb_connections.blockSignals(True)
        current = self._current_conn_name()
        self._cmb_connections.clear()
        for name in self._conn_manager.list_connections():
            display = self._conn_manager.get_display_name(name)
            self._cmb_connections.addItem(display, name)   # data = real conn_name
        # Restore selection by real conn_name
        for i in range(self._cmb_connections.count()):
            if self._cmb_connections.itemData(i) == current:
                self._cmb_connections.setCurrentIndex(i)
                break
        self._cmb_connections.blockSignals(False)

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec_() == SettingsDialog.Accepted:
            self._apply_settings_to_all_tabs()

    def _apply_settings_to_all_tabs(self):
        """Push current settings to all open editor tabs."""
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, SqlEditorTab):
                w.set_autocomplete_enabled(self._settings.get("autocomplete_enabled", True))
                w.set_syntax_check_enabled(self._settings.get("syntax_check_enabled", True))
                w.set_object_check_enabled(self._settings.get("object_check_enabled", True))
                w.set_autocorrect_syntax_enabled(self._settings.get("autocorrect_syntax_enabled", True))
                w.set_autocorrect_objects_enabled(self._settings.get("autocorrect_objects_enabled", True))

    def _load_schema_words_async(self, conn_name: str, engine, db_name: str = ""):
        """Load table/view/procedure names from DB and push to all editor tabs."""
        from PyQt5.QtCore import QThread, QObject, pyqtSignal as _sig

        cache_key = f"{conn_name}/{db_name}" if db_name else conn_name

        class _WordLoader(QObject):
            # Emits (object_words, column_words) as two separate lists
            done = _sig(list, list)

            def __init__(self, eng, cn, db):
                super().__init__()
                self._eng = eng
                self._cn  = cn
                self._db  = db

            def run(self):
                try:
                    from core.schema_loader import SchemaLoader
                    work_eng = self._eng
                    owned = False
                    if self._db:
                        db_eng = SchemaLoader._engine_for_db(self._eng, self._db)
                        if db_eng is not None:
                            work_eng = db_eng
                            owned = True
                    try:
                        obj_words = []
                        tables = SchemaLoader.load_tables(work_eng, self._db or None)
                        for t in tables:
                            name   = t.get("name", "")
                            schema = t.get("schema", "")
                            if name:
                                obj_words.append(name)
                            if schema and name:
                                obj_words.append(f"{schema}.{name}")
                        views = SchemaLoader.load_views(work_eng, self._db or None)
                        for v in views:
                            vname   = v.get("name", "") if isinstance(v, dict) else str(v)
                            vschema = v.get("schema", "") if isinstance(v, dict) else ""
                            if vname:
                                obj_words.append(vname)
                            if vschema and vname:
                                obj_words.append(f"{vschema}.{vname}")
                        procs = SchemaLoader.load_procedures(work_eng, self._db or None)
                        for p in procs:
                            pname = p.get("name", "")
                            if pname:
                                obj_words.append(pname)

                        # Column names go into autocomplete only (not autocorrect)
                        col_words = SchemaLoader.load_all_column_names(
                            work_eng, self._db or None
                        )

                        self.done.emit(
                            [w for w in obj_words if w],
                            [w for w in col_words if w],
                        )
                    finally:
                        if owned:
                            work_eng.dispose()
                except Exception:
                    self.done.emit([], [])

        def _on_words(obj_words, col_words):
            all_words = obj_words + col_words
            self._schema_words_cache[cache_key] = (obj_words, all_words)
            for i in range(self._tabs.count()):
                w = self._tabs.widget(i)
                if isinstance(w, SqlEditorTab) and w._conn_name == conn_name:
                    if not db_name or w._db_name == db_name:
                        w.set_schema_words(all_words)   # QCompleter: all words
                        w.set_object_words(obj_words)   # linter + autocorrect: tables/views/procs

        if not hasattr(self, "_word_workers"):
            self._word_workers = []

        worker = _WordLoader(engine, conn_name, db_name)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(_on_words)
        worker.done.connect(lambda *_: thread.quit())
        thread.finished.connect(thread.deleteLater)
        self._word_workers.append(worker)
        thread.finished.connect(lambda: self._word_workers.remove(worker)
                                if worker in self._word_workers else None)
        thread.start()

    def _show_about(self):
        QMessageBox.about(
            self,
            "Sobre FlowSQL",
            "FlowSQL — Cliente de banco de dados multi-plataforma.\n"
            "Versão 1.0 — Fase 2 (Editor SQL)\n\n"
            "Interface inspirada no SQL Server Management Studio.",
        )

    # ── Title bar drag & window controls ─────────────────────────────────────

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _tb_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def _tb_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            if self.isMaximized():
                self.showNormal()
                self._drag_pos = QPoint(self.width() // 2, 16)
            self.move(event.globalPos() - self._drag_pos)

    def _tb_double_click(self, event):
        self._toggle_maximize()
