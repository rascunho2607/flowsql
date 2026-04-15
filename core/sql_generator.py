from __future__ import annotations
"""
SQLGenerator — Converts an AST dict into formatted SQL.
Supports dialects: postgresql, mysql, mssql, sqlite.
"""

from typing import Tuple


class SQLGenerator:

    # Keywords that need quoting for each dialect
    _QUOTE = {
        "postgresql": ('"', '"'),
        "mysql": ("`", "`"),
        "mssql": ("[", "]"),
        "sqlite": ('"', '"'),
    }

    @staticmethod
    def generate(ast: dict, dialect: str = "postgresql") -> str:
        """Convert AST to formatted SQL string."""
        if not ast:
            return ""

        dialect = dialect.lower().replace("sqlserver", "mssql")
        if dialect not in SQLGenerator._QUOTE:
            dialect = "postgresql"

        lines: list[str] = []

        # SELECT
        distinct_kw = "DISTINCT " if ast.get("_distinct") else ""
        select_fields = ast.get("select") or ["*"]
        if len(select_fields) == 1:
            lines.append(f"SELECT {distinct_kw}{select_fields[0]}")
        else:
            lines.append(f"SELECT {distinct_kw}")
            for i, field in enumerate(select_fields):
                comma = "," if i < len(select_fields) - 1 else ""
                lines.append(f"    {field}{comma}")

        # FROM / TOP (MSSQL uses TOP instead of LIMIT)
        limit = ast.get("limit")
        from_node = ast.get("from")
        if from_node:
            table = from_node.get("table", "")
            alias = from_node.get("alias", "")
            if dialect == "mssql" and limit and limit.get("value", 0) > 0:
                # Insert TOP clause
                top_val = limit["value"]
                # Inject into SELECT line
                if lines:
                    lines[0] = lines[0].replace("SELECT ", f"SELECT TOP {top_val} ", 1)
            from_part = SQLGenerator._quote_identifier(table, dialect)
            if alias:
                from_part += f" {alias}"
            lines.append(f"FROM {from_part}")

        # JOINs
        for join in ast.get("joins") or []:
            jtype = join.get("type", "INNER").upper()
            jtable = SQLGenerator._quote_identifier(join.get("table", ""), dialect)
            jalias = join.get("alias", "")
            jon = join.get("on", "")
            if jalias:
                jtable += f" {jalias}"
            join_line = f"{jtype} JOIN {jtable}"
            if jon:
                join_line += f" ON {jon}"
            lines.append(join_line)

        # WHERE
        where = ast.get("where")
        if where and where.get("conditions"):
            op = f"\n  {where.get('op', 'AND')} "
            conds = op.join(where["conditions"])
            lines.append(f"WHERE {conds}")

        # GROUP BY
        group_by = ast.get("group_by") or []
        if group_by:
            lines.append(f"GROUP BY {', '.join(group_by)}")

        # HAVING
        having = ast.get("having")
        if having and having.get("conditions"):
            op = f"\n  {having.get('op', 'AND')} "
            conds = op.join(having["conditions"])
            lines.append(f"HAVING {conds}")

        # ORDER BY
        order_by = ast.get("order_by") or []
        if order_by:
            parts = []
            for entry in order_by:
                if isinstance(entry, dict):
                    direction = entry.get("direction", "ASC").upper()
                    parts.append(f"{entry['name']} {direction}")
                else:
                    parts.append(str(entry))
            lines.append(f"ORDER BY {', '.join(parts)}")

        # LIMIT / OFFSET (not MSSQL — handled via TOP above)
        if limit and limit.get("value", 0) > 0 and dialect != "mssql":
            limit_line = f"LIMIT {limit['value']}"
            if limit.get("offset", 0) > 0:
                if dialect == "mysql":
                    limit_line += f" OFFSET {limit['offset']}"
                else:
                    limit_line += f"\nOFFSET {limit['offset']}"
            lines.append(limit_line)

        sql = "\n".join(lines)
        if not sql.rstrip().endswith(";"):
            sql = sql.rstrip() + ";"
        return sql

    @staticmethod
    def validate(ast: dict) -> Tuple[bool, list]:
        """Validate the AST. Returns (is_valid, list_of_error_strings)."""
        errors: list[str] = list(ast.get("_errors") or [])

        if ast.get("from") is None and not ast.get("joins"):
            errors.append("Nenhuma tabela de origem definida (adicione um TableNode).")

        from_node = ast.get("from") or {}
        if from_node and not from_node.get("table", "").strip():
            errors.append("TableNode sem nome de tabela.")

        for join in ast.get("joins") or []:
            if not join.get("table", "").strip():
                errors.append("JoinNode sem tabela alvo.")
            if not join.get("on", "").strip() and join.get("type", "INNER") != "CROSS":
                errors.append(
                    f"JoinNode ({join.get('type', 'INNER')}) sem condição ON."
                )

        return len(errors) == 0, errors

    @staticmethod
    def _quote_identifier(name: str, dialect: str) -> str:
        if not name or name == "*":
            return name
        # Already has schema prefix?
        if "." in name:
            parts = name.split(".", 1)
            return (
                SQLGenerator._quote_identifier(parts[0], dialect)
                + "."
                + SQLGenerator._quote_identifier(parts[1], dialect)
            )
        # Only quote if name is not already quoted and contains spaces or is a keyword
        open_q, close_q = SQLGenerator._QUOTE.get(dialect, ('"', '"'))
        if " " in name or name.upper() in _SQL_RESERVED:
            return f"{open_q}{name}{close_q}"
        return name

    @staticmethod
    def parse_sql_to_ast(sql: str) -> dict:
        """
        Partial SQL → AST parser for the "Import SQL into Flow Builder" feature.
        Supports simple SELECT ... FROM ... [JOIN ...] [WHERE ...] [GROUP BY ...]
        [ORDER BY ...] [LIMIT ...].  Returns an AST dict (same shape as build()).
        Complex sub-queries / CTEs return a partial result with a warning.
        """
        import re

        ast: dict = {
            "select": [],
            "from": None,
            "joins": [],
            "where": None,
            "group_by": [],
            "having": None,
            "order_by": [],
            "limit": None,
            "aggregates": [],
            "case": [],
            "_errors": [],
        }

        # Normalise whitespace
        sql = re.sub(r"\s+", " ", sql.strip().rstrip(";"))

        # ── SELECT clause ────────────────────────────────────────────
        m = re.search(r"(?i)\bSELECT\b(.+?)\bFROM\b", sql, re.DOTALL)
        if m:
            raw_fields = m.group(1).strip()
            if re.search(r"(?i)\bDISTINCT\b", raw_fields):
                ast["_distinct"] = True
                raw_fields = re.sub(r"(?i)\bDISTINCT\b\s*", "", raw_fields)
            ast["select"] = [f.strip() for f in raw_fields.split(",") if f.strip()]
        else:
            ast["_errors"].append("Parser parcial: cláusula SELECT não encontrada.")
            return ast

        # ── FROM clause ──────────────────────────────────────────────
        from_match = re.search(
            r"(?i)\bFROM\b\s+([\w\.\[\]\"` ]+?)(?:\s+(?:INNER|LEFT|RIGHT|FULL|CROSS|WHERE|GROUP|ORDER|LIMIT|;|$))",
            sql,
        )
        if from_match:
            parts = from_match.group(1).strip().split()
            ast["from"] = {
                "table": parts[0],
                "alias": parts[1] if len(parts) > 1 else "",
            }

        # ── JOINs ────────────────────────────────────────────────────
        join_pattern = re.compile(
            r"(?i)(INNER|LEFT(?:\s+OUTER)?|RIGHT(?:\s+OUTER)?|FULL(?:\s+OUTER)?|CROSS)\s+JOIN\s+"
            r"([\w\.\[\]\"` ]+?)\s+ON\s+(.+?)(?=\s+(?:INNER|LEFT|RIGHT|FULL|CROSS|WHERE|GROUP|ORDER|LIMIT|;|$))",
            re.DOTALL,
        )
        for jm in join_pattern.finditer(sql):
            jtype = re.sub(r"\s+", " ", jm.group(1).strip().upper())
            jtable_raw = jm.group(2).strip().split()
            ast["joins"].append({
                "type": jtype.replace(" OUTER", ""),
                "table": jtable_raw[0],
                "alias": jtable_raw[1] if len(jtable_raw) > 1 else "",
                "on": jm.group(3).strip(),
            })

        # ── WHERE ────────────────────────────────────────────────────
        where_match = re.search(
            r"(?i)\bWHERE\b(.+?)(?=\s+(?:GROUP|ORDER|LIMIT|HAVING|;|$))",
            sql, re.DOTALL,
        )
        if where_match:
            cond_text = where_match.group(1).strip()
            op = "AND"
            if re.search(r"(?i)\bOR\b", cond_text) and not re.search(r"(?i)\bAND\b", cond_text):
                op = "OR"
            conds = re.split(r"(?i)\s+AND\s+|\s+OR\s+", cond_text)
            ast["where"] = {
                "conditions": [c.strip() for c in conds if c.strip()],
                "op": op,
            }

        # ── GROUP BY ─────────────────────────────────────────────────
        grp_match = re.search(
            r"(?i)\bGROUP\s+BY\b(.+?)(?=\s+(?:HAVING|ORDER|LIMIT|;|$))",
            sql, re.DOTALL,
        )
        if grp_match:
            ast["group_by"] = [f.strip() for f in grp_match.group(1).split(",") if f.strip()]

        # ── HAVING ───────────────────────────────────────────────────
        hav_match = re.search(
            r"(?i)\bHAVING\b(.+?)(?=\s+(?:ORDER|LIMIT|;|$))",
            sql, re.DOTALL,
        )
        if hav_match:
            cond_text = hav_match.group(1).strip()
            conds = re.split(r"(?i)\s+AND\s+|\s+OR\s+", cond_text)
            ast["having"] = {
                "conditions": [c.strip() for c in conds if c.strip()],
                "op": "AND",
            }

        # ── ORDER BY ─────────────────────────────────────────────────
        ord_match = re.search(
            r"(?i)\bORDER\s+BY\b(.+?)(?=\s+(?:LIMIT|;|$))",
            sql, re.DOTALL,
        )
        if ord_match:
            for part in ord_match.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                tokens = part.rsplit(None, 1)
                if len(tokens) == 2 and tokens[1].upper() in ("ASC", "DESC"):
                    ast["order_by"].append({"name": tokens[0], "direction": tokens[1].upper()})
                else:
                    ast["order_by"].append({"name": part, "direction": "ASC"})

        # ── LIMIT ────────────────────────────────────────────────────
        lim_match = re.search(r"(?i)\bLIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?", sql)
        if lim_match:
            ast["limit"] = {
                "value": int(lim_match.group(1)),
                "offset": int(lim_match.group(2) or 0),
            }

        if not ast["from"]:
            ast["_errors"].append(
                "Parser parcial: não foi possível identificar a tabela principal. "
                "Verifique os nodes manualmente."
            )

        return ast


# A minimal set of SQL reserved words that need quoting when used as identifiers
_SQL_RESERVED = {
    "SELECT", "FROM", "WHERE", "JOIN", "ON", "AS", "AND", "OR", "NOT",
    "IN", "IS", "NULL", "LIKE", "BETWEEN", "EXISTS", "CASE", "WHEN",
    "THEN", "ELSE", "END", "GROUP", "BY", "HAVING", "ORDER", "LIMIT",
    "DISTINCT", "ALL", "UNION", "INTERSECT", "EXCEPT", "INSERT", "UPDATE",
    "DELETE", "CREATE", "DROP", "ALTER", "TABLE", "INDEX", "VIEW",
    "PRIMARY", "FOREIGN", "KEY", "REFERENCES", "CONSTRAINT", "DEFAULT",
    "USER", "NAME", "TYPE", "VALUE", "VALUES", "SET", "WITH", "TOP",
}
