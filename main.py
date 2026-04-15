"""
FlowSQL — Entry point
Run: python main.py
"""
import sys
import os

# Ensure the flowsql package root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from themes.theme_manager import ThemeManager
from app.main_window import MainWindow


def main():
    # Enable high-DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("FlowSQL")
    app.setOrganizationName("FlowSQL")

    theme_manager = ThemeManager(app)
    theme_manager.apply_theme("dark")  # Dark mode by default

    window = MainWindow(app, theme_manager)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


# alista de objetos ter uma aba com os bancos acessados recentes, independente do servidor. E uma terceira aba com os bancos favoritos do usuário. organizados separados por servidor.
# a opção de ao clicar com o direito em um banco, ter a opção de "abrir nova aba com esse banco" ou "definir como favorito". E na aba de favoritos, clicar com o direito em um banco para "remover dos favoritos".
# uma nova funcionalidade é definir o banco no projeto ocm um click o app ir até p app.setting do SOFC e configurar o acesso ao cliente.