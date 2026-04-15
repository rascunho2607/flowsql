from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QFrame, QScrollArea, QWidget, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from core.settings_manager import SettingsManager


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Opções do FlowSQL")
        self.setModal(True)
        self.setMinimumSize(500, 480)
        self.resize(540, 540)
        self._build_ui()
        self._load_values()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Scroll area so content never gets clipped ─────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 12)
        root.setSpacing(14)

        # ── Title ─────────────────────────────────────────────────────────────
        lbl_title = QLabel("Opções do FlowSQL")
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        lbl_title.setFont(font)
        root.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Plain)
        root.addWidget(sep)

        # ── Editor group ──────────────────────────────────────────────────────
        grp_editor = QGroupBox("Editor SQL")
        grp_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lo_editor = QVBoxLayout(grp_editor)
        lo_editor.setContentsMargins(14, 10, 14, 12)
        lo_editor.setSpacing(10)

        self._chk_autocomplete = QCheckBox(
            "Habilitar autocomplete (palavras-chave e objetos do banco)")
        self._chk_autocomplete.setToolTip(
            "Exibe lista de sugestões ao digitar. Tab ou Enter substitui a palavra inteira.")

        self._chk_new_template = QCheckBox(
            "Iniciar nova consulta com BEGIN TRANSACTION / ROLLBACK")

        lo_editor.addWidget(self._chk_autocomplete)
        lo_editor.addWidget(self._chk_new_template)
        root.addWidget(grp_editor)

        # ── Autocorrect group ─────────────────────────────────────────────────
        grp_correct = QGroupBox("Autocorretор")
        grp_correct.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lo_correct = QVBoxLayout(grp_correct)
        lo_correct.setContentsMargins(14, 10, 14, 12)
        lo_correct.setSpacing(10)

        hint_correct = QLabel(
            "Ao pressionar Espaço ou Enter, corrige automaticamente palavras "
            "similares à palavra correta. Exemplo: \"form\" → \"FROM\", "
            "\"tbLicitcoe\" → \"tbLicitacao\"."
        )
        hint_correct.setWordWrap(True)
        hint_correct.setObjectName("secondary_label")
        lo_correct.addWidget(hint_correct)

        self._chk_autocorrect_syntax = QCheckBox(
            "Autocorrigir palavras-chave SQL (SELECT, FROM, WHERE…)")

        self._chk_autocorrect_objects = QCheckBox(
            "Autocorrigir nomes de objetos do banco (tabelas, views, procedures)")

        lo_correct.addWidget(self._chk_autocorrect_syntax)
        lo_correct.addWidget(self._chk_autocorrect_objects)
        root.addWidget(grp_correct)

        # ── Linter group ──────────────────────────────────────────────────────
        grp_lint = QGroupBox("Verificação de código (sublinhado em tempo real)")
        grp_lint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lo_lint = QVBoxLayout(grp_lint)
        lo_lint.setContentsMargins(14, 10, 14, 12)
        lo_lint.setSpacing(10)

        hint_lint = QLabel(
            "Sublinha problemas no editor 700 ms após você parar de digitar.\n"
            "A verificação de objetos requer que o Pesquisador de Objetos "
            "esteja conectado ao banco."
        )
        hint_lint.setWordWrap(True)
        hint_lint.setObjectName("secondary_label")
        lo_lint.addWidget(hint_lint)

        self._chk_syntax = QCheckBox(
            "Verificar sintaxe (parênteses não fechados, strings sem fechar)")

        self._chk_objects = QCheckBox(
            "Verificar objetos do banco (tabelas, views, procedures inexistentes)")

        lo_lint.addWidget(self._chk_syntax)
        lo_lint.addWidget(self._chk_objects)
        root.addWidget(grp_lint)

        root.addStretch()

        # ── Footer (outside scroll) ───────────────────────────────────────────
        footer = QFrame()
        footer.setFrameShape(QFrame.StyledPanel)
        foot_lo = QHBoxLayout(footer)
        foot_lo.setContentsMargins(20, 10, 20, 10)
        foot_lo.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedWidth(90)
        btn_ok = QPushButton("OK")
        btn_ok.setFixedWidth(90)
        btn_ok.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_ok)
        foot_lo.addWidget(btn_cancel)
        foot_lo.addWidget(btn_ok)
        outer.addWidget(footer)

    def _load_values(self):
        self._chk_autocomplete.setChecked(
            self._settings.get("autocomplete_enabled", True))
        self._chk_new_template.setChecked(
            self._settings.get("new_query_template", True))
        self._chk_autocorrect_syntax.setChecked(
            self._settings.get("autocorrect_syntax_enabled", True))
        self._chk_autocorrect_objects.setChecked(
            self._settings.get("autocorrect_objects_enabled", True))
        self._chk_syntax.setChecked(
            self._settings.get("syntax_check_enabled", True))
        self._chk_objects.setChecked(
            self._settings.get("object_check_enabled", True))

    def _on_ok(self):
        self._settings.set("autocomplete_enabled",
                           self._chk_autocomplete.isChecked())
        self._settings.set("new_query_template",
                           self._chk_new_template.isChecked())
        self._settings.set("autocorrect_syntax_enabled",
                           self._chk_autocorrect_syntax.isChecked())
        self._settings.set("autocorrect_objects_enabled",
                           self._chk_autocorrect_objects.isChecked())
        self._settings.set("syntax_check_enabled",
                           self._chk_syntax.isChecked())
        self._settings.set("object_check_enabled",
                           self._chk_objects.isChecked())
        self.accept()

