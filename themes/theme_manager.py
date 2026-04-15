import os
from pathlib import Path
from PyQt5.QtWidgets import QApplication


class ThemeManager:
    """Applies QSS themes to the application. All colors live in .qss files."""

    THEMES_DIR = Path(__file__).parent

    def __init__(self, app: QApplication):
        self._app = app
        self._current = "dark"

    def apply_theme(self, theme_name: str):
        """Apply 'dark' or 'light' theme."""
        qss_path = self.THEMES_DIR / f"{theme_name}.qss"
        if not qss_path.exists():
            return
        with open(qss_path, "r", encoding="utf-8") as f:
            stylesheet = f.read()
        self._app.setStyleSheet(stylesheet)
        self._current = theme_name

    def toggle_theme(self):
        """Switch between dark and light."""
        next_theme = "light" if self._current == "dark" else "dark"
        self.apply_theme(next_theme)

    def current_theme(self) -> str:
        return self._current
