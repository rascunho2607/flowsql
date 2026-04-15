from __future__ import annotations
"""
core/schema_inspector.py — Queries database metadata for stored procedures and
scalar/table-valued functions so the FlowSQL Node Palette can be populated at
runtime with schema-specific items.
"""

from typing import List

import sqlalchemy
from sqlalchemy import text, inspect as sa_inspect


class SchemaInspector:
    """Retrieves stored-procedure and function metadata from a live engine."""

    def __init__(self, engine: sqlalchemy.Engine):
        self._engine = engine
        self._sa_insp = sa_inspect(engine)

    # ── Tables ────────────────────────────────────────────────────────────────

    def get_tables(self) -> list[str]:
        """Return sorted list of table names in the default schema."""
        try:
            return sorted(self._sa_insp.get_table_names())
        except Exception:
            return []

    def get_columns(self, table_name: str) -> list[dict]:
        """Return column metadata for *table_name*.

        Each dict: {"name": str, "type": str, "pk": bool, "fk": bool}
        """
        try:
            raw_cols = self._sa_insp.get_columns(table_name)
            pk_info  = self._sa_insp.get_pk_constraint(table_name)
            fk_infos = self._sa_insp.get_foreign_keys(table_name)
            pk_cols  = set(pk_info.get("constrained_columns", []))
            fk_cols  = {col for fk in fk_infos
                        for col in fk.get("constrained_columns", [])}
            result = []
            for col in raw_cols:
                col_name = col["name"]
                col_type = str(col["type"]) if col.get("type") is not None else ""
                result.append({
                    "name": col_name,
                    "type": col_type,
                    "pk":   col_name in pk_cols,
                    "fk":   col_name in fk_cols and col_name not in pk_cols,
                })
            return result
        except Exception:
            return []

    # ── Procedures ────────────────────────────────────────────────────────────

    def get_procedures(self) -> list[str]:
        """Return a list of stored-procedure names available in the database."""
        dialect = self._engine.dialect.name
        try:
            with self._engine.connect() as conn:
                if dialect == "postgresql":
                    result = conn.execute(text(
                        "SELECT routine_name "
                        "FROM information_schema.routines "
                        "WHERE routine_type = 'PROCEDURE' "
                        "ORDER BY routine_name"
                    ))
                    return [row[0] for row in result]

                elif dialect == "mysql":
                    result = conn.execute(text(
                        "SELECT ROUTINE_NAME "
                        "FROM INFORMATION_SCHEMA.ROUTINES "
                        "WHERE ROUTINE_TYPE = 'PROCEDURE' "
                        "ORDER BY ROUTINE_NAME"
                    ))
                    return [row[0] for row in result]

                elif dialect == "mssql":
                    result = conn.execute(text(
                        "SELECT name FROM sys.procedures "
                        "WHERE is_ms_shipped = 0 "
                        "ORDER BY name"
                    ))
                    return [row[0] for row in result]

                else:
                    return []
        except Exception:
            return []

    def get_procedure_params(self, name: str) -> dict:
        """Return {"in": [...], "out": [...]} for a stored procedure.

        Each item: {"name": str, "type": str}
        """
        dialect = self._engine.dialect.name
        try:
            with self._engine.connect() as conn:
                if dialect == "postgresql":
                    result = conn.execute(text(
                        "SELECT p.parameter_name, p.data_type, p.parameter_mode "
                        "FROM information_schema.parameters p "
                        "JOIN information_schema.routines r "
                        "  ON r.specific_name = p.specific_name "
                        " AND r.routine_schema = p.specific_schema "
                        "WHERE r.routine_name = :name "
                        "  AND r.routine_type = 'PROCEDURE' "
                        "ORDER BY p.ordinal_position"
                    ), {"name": name})
                    params_in, params_out = [], []
                    for row in result:
                        p_name, p_type, p_mode = row[0] or "", row[1] or "", row[2] or "IN"
                        entry = {"name": p_name, "type": p_type}
                        if p_mode.upper() in ("OUT", "INOUT"):
                            params_out.append(entry)
                        else:
                            params_in.append(entry)
                    return {"in": params_in, "out": params_out}

                elif dialect == "mysql":
                    result = conn.execute(text(
                        "SELECT PARAMETER_NAME, DATA_TYPE, PARAMETER_MODE "
                        "FROM INFORMATION_SCHEMA.PARAMETERS "
                        "WHERE SPECIFIC_NAME = :name "
                        "  AND ROUTINE_TYPE = 'PROCEDURE' "
                        "ORDER BY ORDINAL_POSITION"
                    ), {"name": name})
                    params_in, params_out = [], []
                    for row in result:
                        p_name, p_type, p_mode = row[0] or "", row[1] or "", row[2] or "IN"
                        entry = {"name": p_name, "type": p_type}
                        if p_mode.upper() in ("OUT", "INOUT"):
                            params_out.append(entry)
                        else:
                            params_in.append(entry)
                    return {"in": params_in, "out": params_out}

                elif dialect == "mssql":
                    result = conn.execute(text(
                        "SELECT p.name, t.name AS type_name, p.is_output "
                        "FROM sys.parameters p "
                        "JOIN sys.procedures pr ON pr.object_id = p.object_id "
                        "JOIN sys.types t ON t.user_type_id = p.user_type_id "
                        "WHERE pr.name = :name "
                        "ORDER BY p.parameter_id"
                    ), {"name": name})
                    params_in, params_out = [], []
                    for row in result:
                        p_name, p_type, is_output = row[0] or "", row[1] or "", row[2]
                        entry = {"name": p_name.lstrip("@"), "type": p_type}
                        if is_output:
                            params_out.append(entry)
                        else:
                            params_in.append(entry)
                    return {"in": params_in, "out": params_out}

                else:
                    return {"in": [], "out": []}
        except Exception:
            return {"in": [], "out": []}

    # ── Functions (scalar / table-valued) ─────────────────────────────────────

    def get_functions(self) -> list[str]:
        """Return a list of user-defined function names."""
        dialect = self._engine.dialect.name
        try:
            with self._engine.connect() as conn:
                if dialect == "postgresql":
                    result = conn.execute(text(
                        "SELECT routine_name "
                        "FROM information_schema.routines "
                        "WHERE routine_type = 'FUNCTION' "
                        "ORDER BY routine_name"
                    ))
                    return [row[0] for row in result]

                elif dialect == "mysql":
                    result = conn.execute(text(
                        "SELECT ROUTINE_NAME "
                        "FROM INFORMATION_SCHEMA.ROUTINES "
                        "WHERE ROUTINE_TYPE = 'FUNCTION' "
                        "ORDER BY ROUTINE_NAME"
                    ))
                    return [row[0] for row in result]

                elif dialect == "mssql":
                    result = conn.execute(text(
                        "SELECT name FROM sys.objects "
                        "WHERE type IN ('FN','IF','TF') "
                        "  AND is_ms_shipped = 0 "
                        "ORDER BY name"
                    ))
                    return [row[0] for row in result]

                else:
                    return []
        except Exception:
            return []
