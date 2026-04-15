from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import sqlalchemy

from core.db_engine import DBEngine


def _encode_password(plain: str) -> str:
    return base64.b64encode(plain.encode("utf-8")).decode("ascii")


def _decode_password(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return encoded


class ConnectionManager:
    """Manages named active connections and persists them to disk."""

    STORAGE_DIR  = Path.home() / ".flowsql"
    STORAGE_FILE = STORAGE_DIR / "connections.json"
    ORDER_FILE   = STORAGE_DIR / "server_order.json"

    def __init__(self):
        self._configs: Dict[str, dict] = {}           # name -> config dict
        self._engines: Dict[str, sqlalchemy.Engine] = {}  # name -> Engine
        self.load_from_disk()

    # ── Public API ───────────────────────────────────────────────────────────

    def add_config_only(self, name: str, config: dict):
        """Save config without connecting (engine created later, async)."""
        self._configs[name] = dict(config)
        self.save_to_disk()

    def register_engine(self, name: str, engine: sqlalchemy.Engine):
        """Register an externally-created engine (called after async connect)."""
        self._engines[name] = engine

    def add_connection(self, name: str, config: dict) -> bool:
        """Create and register an engine synchronously. Returns True if successful."""
        try:
            engine = DBEngine.get_engine(config)
            self._configs[name] = dict(config)
            self._engines[name] = engine
            self.save_to_disk()
            return True
        except Exception:
            return False

    def get_connection(self, name: str) -> Optional[sqlalchemy.Engine]:
        return self._engines.get(name)

    def get_connection_or_create(self, name: str) -> Optional[sqlalchemy.Engine]:
        """Returns cached engine or tries to create one synchronously."""
        if name in self._engines:
            return self._engines[name]
        if name in self._configs:
            try:
                engine = DBEngine.get_engine(self._configs[name])
                self._engines[name] = engine
                return engine
            except Exception:
                return None
        return None

    def remove_connection(self, name: str):
        engine = self._engines.pop(name, None)
        if engine:
            engine.dispose()
        self._configs.pop(name, None)
        self.save_to_disk()

    def list_connections(self) -> List[str]:
        return list(self._configs.keys())

    def list_saved_configs(self) -> List[dict]:
        """Return all saved configs for use as connection history."""
        return [{"name": k, **v} for k, v in self._configs.items()]

    # ── Server order ─────────────────────────────────────────────────────────

    def save_server_order(self, order: List[str]):
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.ORDER_FILE, "w", encoding="utf-8") as f:
            json.dump(order, f)

    def load_server_order(self) -> List[str]:
        try:
            with open(self.ORDER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    # ── Persistence ──────────────────────────────────────────────────────────

    def save_to_disk(self):
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        serializable = {}
        for name, cfg in self._configs.items():
            entry = dict(cfg)
            if "password" in entry and entry["password"]:
                entry["password"] = _encode_password(entry["password"])
                entry["_pw_encoded"] = True
            serializable[name] = entry
        with open(self.STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

    def load_from_disk(self):
        if not self.STORAGE_FILE.exists():
            return
        try:
            with open(self.STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, cfg in data.items():
                entry = dict(cfg)
                if entry.pop("_pw_encoded", False) and "password" in entry:
                    entry["password"] = _decode_password(entry["password"])
                self._configs[name] = entry
        except Exception:
            pass

    def get_config(self, name: str) -> Optional[dict]:
        return dict(self._configs.get(name, {}))

    def get_display_name(self, conn_name: str) -> str:
        """Return the alias (apelido) for a connection, or the conn_name if none set."""
        cfg = self._configs.get(conn_name, {})
        return cfg.get("alias", "").strip() or conn_name
