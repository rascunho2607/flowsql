from PyQt5.QtWidgets import QStatusBar, QLabel
from PyQt5.QtCore import Qt


class StatusBar(QStatusBar):
    """Bottom status bar styled like SSMS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)

        self._lbl_server = QLabel("Sem conexão")
        self._lbl_db = QLabel("")
        self._lbl_message = QLabel("Pronto")
        self._lbl_user = QLabel("")

        self.addWidget(self._lbl_server)
        self.addWidget(self._lbl_db)
        self.addWidget(self._lbl_message, 1)
        self.addPermanentWidget(self._lbl_user)

    def set_server(self, name: str):
        self._lbl_server.setText(name)

    def set_database(self, name: str):
        self._lbl_db.setText(f"  |  {name}" if name else "")

    def set_message(self, msg: str):
        self._lbl_message.setText(msg)

    def set_user(self, user: str):
        self._lbl_user.setText(user)

    def clear_connection(self):
        self._lbl_server.setText("Sem conexão")
        self._lbl_db.setText("")
        self._lbl_message.setText("Pronto")
        self._lbl_user.setText("")
