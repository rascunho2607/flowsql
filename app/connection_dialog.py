from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton,
    QTabWidget, QFormLayout, QComboBox, QLineEdit, QSpinBox, QCheckBox,
    QFrame, QSizePolicy, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView,
)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont, QCursor

from core.db_engine import DBEngine


# Port defaults per DB type
_PORT_MAP = {
    "PostgreSQL": 5432,
    "MySQL": 3306,
    "SQL Server": 1433,
    "SQLite": 0,
    "Oracle": 1521,
}


class ConnectionDialog(QDialog):
    """
    Modal connection dialog that replicates the SSMS 'Connect to Server' popup.
    """

    def __init__(self, parent=None, prefill: dict = None,
                 history: list = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(580)

        self._drag_pos = None
        self._result_config: dict | None = None
        self._history: list = history or []   # list of saved config dicts

        self._build_ui()
        if prefill:
            self._apply_prefill(prefill)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Custom title bar ─────────────────────────────────────────────────
        titlebar = QWidget(objectName="dialog_titlebar")
        titlebar.setFixedHeight(38)
        tb_layout = QHBoxLayout(titlebar)
        tb_layout.setContentsMargins(12, 0, 8, 0)

        lbl_title = QLabel("Conectar ao Servidor", objectName="dialog_title_label")
        font = QFont()
        font.setBold(True)
        lbl_title.setFont(font)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(26, 26)
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: white; border: none; font-size: 14px; }"
            "QPushButton:hover { background: #c42b1c; border-radius: 3px; }"
        )
        btn_close.clicked.connect(self.reject)

        tb_layout.addWidget(lbl_title)
        tb_layout.addStretch()
        tb_layout.addWidget(btn_close)

        # Draggable titlebar
        titlebar.mousePressEvent = self._title_mouse_press
        titlebar.mouseMoveEvent = self._title_mouse_move

        root_layout.addWidget(titlebar)

        # ── Tab widget ───────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_history_tab(), "Recentes")
        self._tabs.addTab(self._build_logon_tab(), "Logon")
        self._tabs.addTab(self._build_properties_tab(), "Propriedades de Conexão")
        self._tabs.addTab(self._build_extra_tab(), "Parâmetros Adicionais")
        # Start on Logon unless there are saved connections
        self._tabs.setCurrentIndex(1 if not self._history else 0)
        root_layout.addWidget(self._tabs, 1)

        # ── Footer ──────────────────────────────────────────────────────────
        footer = QWidget(objectName="dialog_footer")
        footer.setFixedHeight(50)
        foot_layout = QHBoxLayout(footer)
        foot_layout.setContentsMargins(10, 8, 10, 8)
        foot_layout.setSpacing(6)
        foot_layout.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_test = QPushButton("Testar Conexão")
        btn_connect = QPushButton("Conectar")
        btn_connect.setDefault(True)

        btn_cancel.clicked.connect(self.reject)
        btn_test.clicked.connect(self._on_test)
        btn_connect.clicked.connect(self._on_connect)

        foot_layout.addWidget(btn_cancel)
        foot_layout.addWidget(btn_test)
        foot_layout.addWidget(btn_connect)

        root_layout.addWidget(footer)

    # ── History tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        lo = QVBoxLayout(widget)
        lo.setContentsMargins(14, 10, 14, 10)
        lo.setSpacing(8)

        lbl = QLabel("Clique duas vezes para preencher o formulário de conexão")
        lbl.setObjectName("secondary_label")
        lbl.setWordWrap(True)
        lo.addWidget(lbl)

        self._history_list = QListWidget()
        self._history_list.setObjectName("history_list")
        self._history_list.setAlternatingRowColors(True)
        self._history_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._history_list.itemDoubleClicked.connect(self._on_history_double_click)
        lo.addWidget(self._history_list, 1)

        btn_row = QHBoxLayout()
        btn_use = QPushButton("Usar selecionada")
        btn_use.clicked.connect(self._on_history_use)
        btn_row.addStretch()
        btn_row.addWidget(btn_use)
        lo.addLayout(btn_row)

        # Populate
        self._refresh_history_list()
        return widget

    def _refresh_history_list(self):
        self._history_list.clear()
        for cfg in self._history:
            host  = cfg.get("host", "")
            db    = cfg.get("database", "")
            uname = cfg.get("user", "")
            alias = cfg.get("alias", "")
            label = alias or cfg.get("name") or host
            sub   = "{}{}{}".format(
                host,
                ("/" + db) if db else "",
                ("  [" + uname + "]") if uname else "",
            )
            it = QListWidgetItem(label)
            it.setToolTip(sub)
            it.setData(Qt.UserRole, cfg)
            self._history_list.addItem(it)

    def _on_history_double_click(self, item: QListWidgetItem):
        cfg = item.data(Qt.UserRole)
        if cfg:
            self._apply_prefill(cfg)
            self._tabs.setCurrentIndex(1)  # switch to Logon tab

    def _on_history_use(self):
        item = self._history_list.currentItem()
        if item:
            self._on_history_double_click(item)

    # ── Logon tab ─────────────────────────────────────────────────────────────

    def _build_logon_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Server type
        self._cmb_server_type = QComboBox()
        self._cmb_server_type.addItems([
            "Mecanismo de Banco de Dados",
            "Analysis Services",
            "Integration Services",
        ])
        layout.addRow("Tipo de servidor:", self._cmb_server_type)

        # DB type
        self._cmb_db_type = QComboBox()
        self._cmb_db_type.addItems(list(_PORT_MAP.keys()))
        self._cmb_db_type.currentTextChanged.connect(self._on_db_type_changed)
        layout.addRow("Tipo de banco:", self._cmb_db_type)

        layout.addRow(self._separator())

        # Server alias
        self._edit_alias = QLineEdit()
        self._edit_alias.setPlaceholderText("Ex: Produção, Homologação, 192.168.1.10")
        layout.addRow("Alias (apelido):", self._edit_alias)

        # Server name
        self._edit_host = QLineEdit()
        self._edit_host.setPlaceholderText("Ex: localhost ou db.empresa.com")
        layout.addRow("Nome do servidor:", self._edit_host)

        # Port
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1, 65535)
        self._spin_port.setValue(5432)
        layout.addRow("Porta:", self._spin_port)

        layout.addRow(self._separator())

        # Auth type
        self._cmb_auth = QComboBox()
        self._cmb_auth.addItems([
            "Autenticação SQL Server",
            "Autenticação do Windows",
            "Azure Active Directory",
        ])
        self._cmb_auth.currentTextChanged.connect(self._on_auth_changed)
        layout.addRow("Autenticação:", self._cmb_auth)

        # Login
        self._edit_user = QLineEdit()
        layout.addRow("Logon:", self._edit_user)

        # Password
        self._edit_password = QLineEdit()
        self._edit_password.setEchoMode(QLineEdit.Password)
        layout.addRow("Senha:", self._edit_password)

        # Remember password
        self._chk_remember = QCheckBox("Lembrar senha")
        layout.addRow("", self._chk_remember)

        layout.addRow(self._separator())

        # Database name
        self._edit_db = QLineEdit()
        self._edit_db.setPlaceholderText("Nome do banco (opcional)")
        layout.addRow("Banco de dados:", self._edit_db)

        # Connection name
        self._edit_conn_name = QLineEdit()
        self._edit_conn_name.setPlaceholderText("Ex: prod-postgres")
        layout.addRow("Nome da conexão:", self._edit_conn_name)

        return widget

    # ── Properties tab ────────────────────────────────────────────────────────

    def _build_properties_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setVerticalSpacing(10)
        layout.setHorizontalSpacing(12)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._spin_conn_timeout = QSpinBox()
        self._spin_conn_timeout.setRange(0, 3600)
        self._spin_conn_timeout.setValue(30)
        layout.addRow("Timeout de conexão (s):", self._spin_conn_timeout)

        self._spin_exec_timeout = QSpinBox()
        self._spin_exec_timeout.setRange(0, 86400)
        self._spin_exec_timeout.setValue(0)
        layout.addRow("Timeout de execução (s):", self._spin_exec_timeout)

        self._chk_ssl = QCheckBox("Usar SSL")
        layout.addRow("", self._chk_ssl)

        ssl_row = QHBoxLayout()
        self._edit_ssl_cert = QLineEdit()
        self._edit_ssl_cert.setPlaceholderText("Caminho do certificado SSL...")
        btn_ssl_browse = QPushButton("...")
        btn_ssl_browse.setFixedWidth(32)
        btn_ssl_browse.clicked.connect(self._browse_ssl_cert)
        ssl_row.addWidget(self._edit_ssl_cert)
        ssl_row.addWidget(btn_ssl_browse)

        ssl_widget = QWidget()
        ssl_widget.setLayout(ssl_row)
        layout.addRow("Certificado SSL (path):", ssl_widget)

        return widget

    # ── Extra tab ─────────────────────────────────────────────────────────────

    def _build_extra_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setVerticalSpacing(10)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lbl = QLabel("Parâmetros adicionais de conexão estarão disponíveis em versões futuras.")
        lbl.setWordWrap(True)
        lbl.setObjectName("secondary_label")
        layout.addRow(lbl)

        return widget

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        return line

    def _on_db_type_changed(self, db_type: str):
        port = _PORT_MAP.get(db_type, 5432)
        if db_type == "SQLite":
            self._spin_port.setEnabled(False)
            self._spin_port.setValue(0)
        else:
            self._spin_port.setEnabled(True)
            self._spin_port.setValue(port)

    def _on_auth_changed(self, auth: str):
        windows_auth = auth == "Autenticação do Windows"
        self._edit_user.setEnabled(not windows_auth)
        self._edit_password.setEnabled(not windows_auth)
        self._chk_remember.setEnabled(not windows_auth)

    def _browse_ssl_cert(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Certificado SSL", "", "Arquivos PEM (*.pem *.crt *.key);;Todos (*)")
        if path:
            self._edit_ssl_cert.setText(path)

    def _build_config(self) -> dict:
        db_type_text = self._cmb_db_type.currentText()
        type_map = {
            "PostgreSQL": "postgresql",
            "MySQL": "mysql",
            "SQL Server": "mssql",
            "SQLite": "sqlite",
            "Oracle": "oracle",
        }
        return {
            "name": self._edit_conn_name.text().strip() or self._edit_host.text().strip(),
            "alias": self._edit_alias.text().strip(),
            "type": type_map.get(db_type_text, "postgresql"),
            "host": self._edit_host.text().strip(),
            "port": self._spin_port.value(),
            "database": self._edit_db.text().strip(),
            "user": self._edit_user.text().strip(),
            "password": self._edit_password.text(),
            "ssl": self._chk_ssl.isChecked(),
            "conn_timeout": self._spin_conn_timeout.value(),
            "exec_timeout": self._spin_exec_timeout.value(),
        }

    def _validate(self) -> tuple[bool, str]:
        host = self._edit_host.text().strip()
        db_type = self._cmb_db_type.currentText()
        auth = self._cmb_auth.currentText()

        if db_type != "SQLite" and not host:
            return False, "O campo 'Nome do servidor' não pode estar vazio."
        port = self._spin_port.value()
        if db_type != "SQLite" and port <= 0:
            return False, "Porta inválida."
        if auth == "Autenticação SQL Server" and not self._edit_user.text().strip():
            return False, "O campo 'Logon' não pode estar vazio para Autenticação SQL Server."
        return True, ""

    def _on_test(self):
        valid, msg = self._validate()
        if not valid:
            QMessageBox.warning(self, "Validação", msg)
            return
        config = self._build_config()
        success, result_msg = DBEngine.test_connection(config)
        if success:
            QMessageBox.information(self, "Testar Conexão", result_msg)
        else:
            QMessageBox.critical(self, "Erro de Conexão", result_msg)

    def _on_connect(self):
        valid, msg = self._validate()
        if not valid:
            QMessageBox.warning(self, "Validação", msg)
            return
        self._result_config = self._build_config()
        self.accept()

    def _apply_prefill(self, cfg: dict):
        type_map_rev = {
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "mssql": "SQL Server",
            "sqlite": "SQLite",
        }
        db_type_text = type_map_rev.get(cfg.get("type", "postgresql"), "PostgreSQL")
        idx = self._cmb_db_type.findText(db_type_text)
        if idx >= 0:
            self._cmb_db_type.setCurrentIndex(idx)

        self._edit_alias.setText(cfg.get("alias", ""))
        self._edit_host.setText(cfg.get("host", ""))
        self._spin_port.setValue(cfg.get("port", 5432))
        self._edit_db.setText(cfg.get("database", ""))
        self._edit_user.setText(cfg.get("user", ""))
        self._edit_password.setText(cfg.get("password", ""))
        self._edit_conn_name.setText(cfg.get("name", ""))

    # ── Result ────────────────────────────────────────────────────────────────

    def get_config(self) -> dict | None:
        return self._result_config

    # ── Drag support ─────────────────────────────────────────────────────────

    def _title_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def _title_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
