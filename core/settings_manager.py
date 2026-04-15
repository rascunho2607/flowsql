from __future__ import annotations

import json
from pathlib import Path


class SettingsManager:
    """Persists user preferences to ~/.flowsql/settings.json."""

    STORAGE_DIR   = Path.home() / ".flowsql"
    SETTINGS_FILE = STORAGE_DIR / "settings.json"

    _DEFAULTS: dict = {
        "autocomplete_enabled":       True,
        "syntax_check_enabled":       True,
        "object_check_enabled":       True,
        "autocorrect_syntax_enabled": True,
        "autocorrect_objects_enabled": True,
        "new_query_template":         True,
    }

    def __init__(self):
        self._data: dict = dict(self._DEFAULTS)
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._data.get(key, self._DEFAULTS.get(key, default))

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def all(self) -> dict:
        return dict(self._data)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        try:
            with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            self._data.update(stored)
        except Exception:
            pass

    def _save(self):
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
