from __future__ import annotations

import re
import urllib.parse
from typing import List

import sqlalchemy
from sqlalchemy import inspect, text


class SchemaLoader:
    """Loads database schema metadata using SQLAlchemy inspection."""

    @staticmethod
    def _engine_for_db(engine: sqlalchemy.Engine, database: str):
        """
        Return a *temporary* engine connected to `database` on the same server.
        Works by cloning the ODBC connection string and swapping DATABASE=.
        Caller is responsible for calling .dispose() on the returned engine.
        Returns None if the original URL is not an odbc_connect-style URL.
        """
        try:
            # render_as_string does NOT mask PWD embedded in query params —
            # only the SQLAlchemy URL's own password field is masked, but our
            # credentials live inside the odbc_connect value, so this is safe.
            url_str = engine.url.render_as_string(hide_password=False)
            if "odbc_connect=" not in url_str:
                return None
            prefix, odbc_enc = url_str.split("odbc_connect=", 1)
            odbc_str = urllib.parse.unquote_plus(odbc_enc)
            if re.search(r'DATABASE=', odbc_str, re.IGNORECASE):
                odbc_str = re.sub(r'(?i)DATABASE=[^;]*;',
                                  f'DATABASE={database};', odbc_str)
            else:
                odbc_str += f'DATABASE={database};'
            new_url = prefix + "odbc_connect=" + urllib.parse.quote_plus(odbc_str)
            from sqlalchemy import create_engine
            return create_engine(new_url, future=True)
        except Exception:
            return None

    @staticmethod
    def load_databases(engine: sqlalchemy.Engine) -> List[str]:
        """Return list of database/schema names on the server."""
        db_type = engine.dialect.name
        try:
            with engine.connect() as conn:
                if db_type == "postgresql":
                    result = conn.execute(
                        text("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
                    )
                    return [row[0] for row in result]
                elif db_type == "mysql":
                    result = conn.execute(text("SHOW DATABASES"))
                    return [row[0] for row in result]
                elif db_type == "mssql":
                    result = conn.execute(text("SELECT name FROM sys.databases ORDER BY name"))
                    return [row[0] for row in result]
                elif db_type == "sqlite":
                    return ["main"]
                else:
                    insp = inspect(engine)
                    return insp.get_schema_names()
        except Exception:
            insp = inspect(engine)
            return insp.get_schema_names()

    @staticmethod
    def load_tables(engine: sqlalchemy.Engine, database: str = None) -> List[dict]:
        """Return list of {name, schema} dicts for tables in the given database."""
        db_type = engine.dialect.name
        try:
            # For MSSQL: create a temp engine targeting the specific DB so we
            # query its own INFORMATION_SCHEMA without cross-database references.
            if db_type == "mssql" and database:
                temp = SchemaLoader._engine_for_db(engine, database)
                if temp:
                    try:
                        with temp.connect() as conn:
                            result = conn.execute(text(
                                "SELECT TABLE_SCHEMA, TABLE_NAME "
                                "FROM INFORMATION_SCHEMA.TABLES "
                                "WHERE TABLE_TYPE = 'BASE TABLE' "
                                "ORDER BY TABLE_SCHEMA, TABLE_NAME"
                            ))
                            return [{"schema": r[0], "name": r[1]} for r in result]
                    finally:
                        temp.dispose()
            insp = inspect(engine)
            schemas = insp.get_schema_names()
            tables = []
            for schema in schemas:
                if schema in ("information_schema", "pg_catalog", "pg_toast",
                              "sys", "INFORMATION_SCHEMA", "guest"):
                    continue
                try:
                    for tname in insp.get_table_names(schema=schema):
                        tables.append({"name": tname, "schema": schema})
                except Exception:
                    continue
            return tables
        except Exception:
            return []

    @staticmethod
    def load_columns(
        engine: sqlalchemy.Engine, table: str, schema: str = None
    ) -> List[dict]:
        """Return list of {name, type, pk, nullable} dicts for columns of a table."""
        try:
            insp = inspect(engine)
            pk_cols = set(insp.get_pk_constraint(table, schema=schema).get("constrained_columns", []))
            columns = []
            for col in insp.get_columns(table, schema=schema):
                columns.append(
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "pk": col["name"] in pk_cols,
                        "nullable": col.get("nullable", True),
                    }
                )
            return columns
        except Exception:
            return []

    @staticmethod
    def load_views(engine: sqlalchemy.Engine, database: str = None) -> List[dict]:
        """Return list of {schema, name} dicts for views."""
        db_type = engine.dialect.name
        try:
            if db_type == "mssql" and database:
                temp = SchemaLoader._engine_for_db(engine, database)
                if temp:
                    try:
                        with temp.connect() as conn:
                            result = conn.execute(text(
                                "SELECT TABLE_SCHEMA, TABLE_NAME "
                                "FROM INFORMATION_SCHEMA.VIEWS "
                                "ORDER BY TABLE_SCHEMA, TABLE_NAME"
                            ))
                            return [{"schema": r[0], "name": r[1]} for r in result]
                    finally:
                        temp.dispose()
            insp = inspect(engine)
            schemas = insp.get_schema_names()
            views = []
            for schema in schemas:
                if schema in ("information_schema", "pg_catalog", "pg_toast",
                              "sys", "INFORMATION_SCHEMA", "guest"):
                    continue
                try:
                    for vname in insp.get_view_names(schema=schema):
                        views.append({"schema": schema, "name": vname})
                except Exception:
                    continue
            return views
        except Exception:
            return []

    @staticmethod
    def load_procedures(engine: sqlalchemy.Engine, database: str = None) -> List[dict]:
        """Return list of {schema, name, type} dicts for stored procedures and functions."""
        db_type = engine.dialect.name
        try:
            if db_type == "mssql" and database:
                temp = SchemaLoader._engine_for_db(engine, database)
                if temp:
                    try:
                        with temp.connect() as conn:
                            result = conn.execute(text(
                                "SELECT SCHEMA_NAME(schema_id), name, "
                                "  CASE type WHEN 'P' THEN 'procedure' ELSE 'function' END "
                                "FROM sys.objects "
                                "WHERE type IN ('P', 'FN', 'IF', 'TF') "
                                "  AND is_ms_shipped = 0 "
                                "ORDER BY SCHEMA_NAME(schema_id), name"
                            ))
                            return [{"schema": r[0], "name": r[1], "type": r[2]}
                                    for r in result]
                    finally:
                        temp.dispose()
                return []
            elif db_type == "mssql":
                with engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT SCHEMA_NAME(schema_id), name, "
                        "  CASE type WHEN 'P' THEN 'procedure' ELSE 'function' END "
                        "FROM sys.objects "
                        "WHERE type IN ('P', 'FN', 'IF', 'TF') "
                        "  AND is_ms_shipped = 0 "
                        "ORDER BY SCHEMA_NAME(schema_id), name"
                    ))
                    return [{"schema": r[0], "name": r[1], "type": r[2]}
                            for r in result]
            elif db_type == "postgresql":
                with engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT routine_schema, routine_name, routine_type "
                        "FROM information_schema.routines "
                        "WHERE routine_schema NOT IN ('pg_catalog', 'information_schema') "
                        "ORDER BY routine_type, routine_schema, routine_name"
                    ))
                    return [{"schema": r[0], "name": r[1], "type": r[2].lower()}
                            for r in result]
            elif db_type == "mysql":
                with engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE "
                        "FROM information_schema.ROUTINES "
                        "WHERE ROUTINE_SCHEMA = DATABASE() "
                        "ORDER BY ROUTINE_TYPE, ROUTINE_NAME"
                    ))
                    return [{"schema": r[0], "name": r[1], "type": r[2].lower()}
                            for r in result]
            else:
                return []
        except Exception:
            return []

    @staticmethod
    def load_all_column_names(engine: sqlalchemy.Engine, database: str = None) -> List[str]:
        """Return a deduplicated sorted list of column names from all user tables/views."""
        db_type = engine.dialect.name
        try:
            if db_type == "mssql":
                work = engine
                owned = False
                if database:
                    tmp = SchemaLoader._engine_for_db(engine, database)
                    if tmp:
                        work = tmp
                        owned = True
                try:
                    with work.connect() as conn:
                        result = conn.execute(text(
                            "SELECT DISTINCT COLUMN_NAME "
                            "FROM INFORMATION_SCHEMA.COLUMNS "
                            "ORDER BY COLUMN_NAME"
                        ))
                        return [r[0] for r in result]
                finally:
                    if owned:
                        work.dispose()
            elif db_type == "postgresql":
                with engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT DISTINCT column_name "
                        "FROM information_schema.columns "
                        "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
                        "ORDER BY column_name"
                    ))
                    return [r[0] for r in result]
            elif db_type == "mysql":
                with engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT DISTINCT COLUMN_NAME "
                        "FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() "
                        "ORDER BY COLUMN_NAME"
                    ))
                    return [r[0] for r in result]
            else:
                insp = inspect(engine)
                cols: set = set()
                for schema in insp.get_schema_names():
                    for tbl in insp.get_table_names(schema=schema):
                        try:
                            for c in insp.get_columns(tbl, schema=schema):
                                cols.add(c["name"])
                        except Exception:
                            continue
                return sorted(cols)
        except Exception:
            return []

    @staticmethod
    def load_definition(engine: sqlalchemy.Engine, schema: str, name: str,
                        database: str = None) -> str:
        """Return the source definition (CREATE statement) of a procedure, function, or view."""
        db_type = engine.dialect.name
        try:
            if db_type == "mssql":
                target = engine
                dispose_after = False
                if database:
                    temp = SchemaLoader._engine_for_db(engine, database)
                    if temp:
                        target = temp
                        dispose_after = True
                try:
                    with target.connect() as conn:
                        result = conn.execute(
                            text(
                                "SELECT m.definition "
                                "FROM sys.sql_modules m "
                                "JOIN sys.objects o ON m.object_id = o.object_id "
                                "JOIN sys.schemas s ON o.schema_id = s.schema_id "
                                "WHERE s.name = :schema AND o.name = :name"
                            ),
                            {"schema": schema, "name": name},
                        )
                        row = result.fetchone()
                        return row[0] if row else ""
                finally:
                    if dispose_after:
                        target.dispose()
            elif db_type == "postgresql":
                with engine.connect() as conn:
                    result = conn.execute(
                        text(
                            "SELECT pg_get_functiondef(p.oid) "
                            "FROM pg_proc p "
                            "JOIN pg_namespace n ON n.oid = p.pronamespace "
                            "WHERE n.nspname = :schema AND p.proname = :name "
                            "LIMIT 1"
                        ),
                        {"schema": schema, "name": name},
                    )
                    row = result.fetchone()
                    return row[0] if row else ""
            else:
                return ""
        except Exception:
            return ""
