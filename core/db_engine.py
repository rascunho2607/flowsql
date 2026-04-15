from __future__ import annotations

import urllib.parse
import sqlalchemy
from sqlalchemy import create_engine, text


def _best_mssql_driver() -> str:
    """Return the best available pyodbc MSSQL driver, or raise if none found."""
    try:
        import pyodbc
    except ImportError:
        raise RuntimeError("pyodbc não está instalado. Execute: pip install pyodbc")

    # Preference order — newest first
    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "ODBC Driver 11 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server Native Client 10.0",
        "SQL Server",
    ]
    available = set(pyodbc.drivers())
    for d in preferred:
        if d in available:
            return d

    # Last resort: any driver that mentions SQL Server
    for d in available:
        if "SQL Server" in d or "sqlserver" in d.lower():
            return d

    raise RuntimeError(
        "Nenhum driver ODBC para SQL Server foi encontrado.\n"
        "Instale o 'Microsoft ODBC Driver 17 (ou 18) for SQL Server'.\n"
        f"Drivers disponíveis: {sorted(available) or ['(nenhum)']}"
    )


class DBEngine:
    """Abstraction layer over SQLAlchemy for multi-database support."""

    PORT_DEFAULTS = {
        "postgresql": 5432,
        "mysql": 3306,
        "mssql": 1433,
        "sqlite": None,
    }

    @staticmethod
    def get_engine(connection_config: dict) -> sqlalchemy.Engine:
        """
        Build and return a SQLAlchemy Engine from a connection config dict.

        Keys:
            type       - 'postgresql' | 'mysql' | 'mssql' | 'sqlite'
            host       - server hostname or IP
            port       - integer port
            database   - database/schema name
            user       - login username
            password   - plain-text password
            ssl        - bool, whether to use SSL
        """
        db_type = connection_config.get("type", "postgresql").lower()

        if db_type == "sqlite":
            db_path = connection_config.get("database", ":memory:")
            url = f"sqlite:///{db_path}"
            engine = create_engine(url, future=True)
            return engine

        host = connection_config.get("host", "localhost")
        port = connection_config.get("port", DBEngine.PORT_DEFAULTS.get(db_type, 5432))
        database = connection_config.get("database", "")
        user = connection_config.get("user", "")
        password = connection_config.get("password", "")

        if db_type == "postgresql":
            driver = "postgresql+psycopg2"
        elif db_type == "mysql":
            driver = "mysql+pymysql"
        elif db_type in ("mssql", "sqlserver"):
            odbc_driver = _best_mssql_driver()
            # Build a raw ODBC connection string — avoids SQLAlchemy URL-parsing
            # issues with driver names that contain spaces.
            odbc_str = (
                f"DRIVER={{{odbc_driver}}};"
                f"SERVER={host},{port};"
                f"DATABASE={database};"
                f"UID={user};"
                f"PWD={password};"
                "TrustServerCertificate=yes;"
                "Encrypt=no;"
            )
            url = "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc_str)
            engine = create_engine(url, future=True, fast_executemany=True)
            return engine
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

        connect_args = {}
        if connection_config.get("ssl"):
            connect_args["sslmode"] = "require"

        user_enc = urllib.parse.quote_plus(user)
        pw_enc = urllib.parse.quote_plus(password)
        url = f"{driver}://{user_enc}:{pw_enc}@{host}:{port}/{database}"
        engine = create_engine(url, connect_args=connect_args, future=True)
        return engine

    @staticmethod
    def test_connection(connection_config: dict) -> tuple[bool, str]:
        """Test connectivity. Returns (success, message)."""
        try:
            engine = DBEngine.get_engine(connection_config)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            return True, "Conexão realizada com sucesso!"
        except Exception as exc:
            return False, str(exc)
