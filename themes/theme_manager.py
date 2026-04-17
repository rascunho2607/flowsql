import os
from pathlib import Path
from PyQt5.QtWidgets import QApplication


class ThemeManager:
    """Applies QSS themes to the application. All colors live in .qss files."""

    THEMES_DIR = Path(__file__).parent

    # Supported theme names. "high-contrast" reuses dark.qss as a base and
    # relies on apply_node_theme() to override canvas colours programmatically.
    VALID_THEMES = (
        "dark",
        "light",
        "high-contrast",
        "orange",
        "dracula",
        "neon",
        "blueprint",
        "datastream",
        "neural",
        "matrix",
        "deepspace",
        "synthwave",
        "lava",
        "industrial",
        "frost",
        "nature",
    )

    def __init__(self, app: QApplication):
        self._app = app
        self._current = "dark"

    def apply_theme(self, theme_name: str):
        """Apply a registered theme by name."""
        # High-contrast uses dark.qss as base QSS
        qss_name = "dark" if theme_name == "high-contrast" else theme_name
        qss_path = self.THEMES_DIR / f"{qss_name}.qss"
        if qss_path.exists():
            with open(qss_path, "r", encoding="utf-8") as f:
                stylesheet = f.read()
            self._app.setStyleSheet(stylesheet)
        self._current = theme_name

    def toggle_theme(self):
        """Cycle through all registered themes."""
        cycle = (
            "dark",
            "light",
            "high-contrast",
            "orange",
            "dracula",
            "neon",
            "blueprint",
            "datastream",
            "neural",
            "matrix",
            "deepspace",
            "synthwave",
            "lava",
            "industrial",
            "frost",
            "nature",
        )
        idx = cycle.index(self._current) if self._current in cycle else 0
        next_theme = cycle[(idx + 1) % len(cycle)]
        self.apply_theme(next_theme)

    def current_theme(self) -> str:
        return self._current
