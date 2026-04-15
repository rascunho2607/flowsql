from __future__ import annotations
"""
ASTBuilder — Traverses flow nodes in topological order and builds a query AST.
"""

from collections import defaultdict, deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports at runtime


class ASTBuilder:
    """
    Given a list of node dicts (from BaseNode.to_dict()) and a list of
    connection dicts, build a normalised AST ready for SQLGenerator.
    """

    @staticmethod
    def build(nodes: list, connections: list) -> dict:
        """
        Parameters
        ----------
        nodes       : list of dicts returned by BaseNode.to_dict()
        connections : list of dicts {from_node, from_port, to_node, to_port}

        Returns
        -------
        AST dict:
        {
          "select":   [str, ...],
          "from":     {"table": str, "alias": str} | None,
          "joins":    [{"type", "table", "alias", "on"}, ...],
          "where":    {"conditions": [...], "op": "AND"|"OR"} | None,
          "group_by": [str, ...],
          "having":   {"conditions": [...], "op": str} | None,
          "order_by": [{"name": str, "direction": "ASC"|"DESC"}, ...],
          "limit":    {"value": int, "offset": int} | None,
          "aggregates": [{"func", "field", "alias"}, ...],
          "case":     [...],
          "_errors":  [str, ...]    # validation messages
        }
        """
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

        # Index nodes by id
        node_map = {n["id"]: n for n in nodes}

        # Build adjacency for topological sort
        # Edge: from_node → to_node
        out_edges: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = defaultdict(int)
        for nid in node_map:
            in_degree.setdefault(nid, 0)
        for conn in connections:
            fn, tn = conn["from_node"], conn["to_node"]
            out_edges[fn].append(tn)
            in_degree[tn] = in_degree.get(tn, 0) + 1

        # Kahn's algorithm
        queue: deque[str] = deque(
            nid for nid in node_map if in_degree.get(nid, 0) == 0
        )
        order: list[str] = []
        while queue:
            nid = queue.popleft()
            order.append(nid)
            for nb in out_edges[nid]:
                in_degree[nb] -= 1
                if in_degree[nb] == 0:
                    queue.append(nb)

        if len(order) != len(node_map):
            ast["_errors"].append("Ciclo detectado nos nodes — verifique as conexões.")
            order = list(node_map.keys())  # fallback: just process all

        # Process nodes in topological order
        join_counter = 0
        for nid in order:
            node = node_map[nid]
            ntype = node.get("type", "")
            data = node.get("data", {})

            if ntype == "table":
                if ast["from"] is None:
                    ast["from"] = {
                        "table": data.get("name", ""),
                        "alias": data.get("alias", ""),
                    }
                else:
                    # Subsequent tables become implicit joins (user should use JoinNode)
                    ast["joins"].append({
                        "type": "INNER",
                        "table": data.get("name", ""),
                        "alias": data.get("alias", ""),
                        "on": "",
                    })

            elif ntype == "join":
                # Build ON condition from pairs (field-port connections auto-fill them)
                pairs        = data.get("pairs", [])
                on_parts:    list[str] = []
                left_tables:  set[str] = set()
                right_tables: set[str] = set()
                for p in pairs:
                    lf = p.get("left_field", "")
                    rf = p.get("right_field", "")
                    op = p.get("op", "=")
                    if lf and rf:
                        on_parts.append(f"{lf} {op} {rf}")
                    if lf and "." in lf:
                        left_tables.add(lf.split(".")[0])
                    if rf and "." in rf:
                        right_tables.add(rf.split(".")[0])

                on_str = " AND ".join(on_parts) or data.get("on", "")

                # Prefer explicit tables stored by the node (via in_ctx / field ports)
                left_table  = data.get("left_table",  "") or next(iter(left_tables),  "")
                right_table = data.get("right_table", "") or next(iter(right_tables), data.get("table", ""))

                from_tbl = ast["from"]["table"] if ast["from"] else ""

                # If FROM was incorrectly set to the right_table (right TableNode was
                # processed before left), swap so left_table becomes FROM.
                if from_tbl and from_tbl == right_table and left_table:
                    ast["from"] = {"table": left_table, "alias": ""}
                    # Remove any implicit (ON-less) join for left_table — it's now FROM
                    ast["joins"] = [j for j in ast["joins"]
                                    if not (j["table"] == left_table and not j.get("on"))]
                elif ast["from"] is None and left_table:
                    ast["from"] = {"table": left_table, "alias": ""}

                # Remove implicit (ON-less) joins for both tables:
                # left_table is now FROM; right_table will get a proper join below.
                for tbl in (left_table, right_table):
                    if tbl:
                        ast["joins"] = [j for j in ast["joins"]
                                        if not (j["table"] == tbl and not j.get("on"))]

                if right_table:
                    ast["joins"].append({
                        "type":  data.get("join_type", "INNER"),
                        "table": right_table,
                        "alias": data.get("alias", ""),
                        "on":    on_str,
                    })
                join_counter += 1

            elif ntype == "select":
                ast["select"].extend(
                    f for f in data.get("fields", []) if f.strip()
                )
                if data.get("distinct"):
                    ast["_distinct"] = True  # handled by SQLGenerator

            elif ntype == "where":
                ast["where"] = {
                    "conditions": [c for c in data.get("conditions", []) if c.strip()],
                    "op": data.get("operator", "AND"),
                }

            elif ntype == "group_by":
                ast["group_by"].extend(
                    f for f in data.get("fields", []) if f.strip()
                )

            elif ntype == "having":
                ast["having"] = {
                    "conditions": [c for c in data.get("conditions", []) if c.strip()],
                    "op": data.get("operator", "AND"),
                }

            elif ntype == "order_by":
                for entry in data.get("fields", []):
                    if isinstance(entry, dict) and entry.get("name", "").strip():
                        ast["order_by"].append(entry)
                    elif isinstance(entry, str) and entry.strip():
                        ast["order_by"].append({"name": entry, "direction": "ASC"})

            elif ntype == "limit":
                ast["limit"] = {
                    "value": int(data.get("value", 0)),
                    "offset": int(data.get("offset", 0)),
                }

            elif ntype == "aggregate":
                ast["aggregates"].append({
                    "func": data.get("func", "COUNT"),
                    "field": data.get("field", "*"),
                    "alias": data.get("alias", ""),
                })

            elif ntype == "case":
                ast["case"].append({
                    "whens": data.get("whens", []),
                    "else": data.get("else_value", ""),
                    "alias": data.get("alias", ""),
                })

            # result node contributes nothing to AST

        # Post-process: remove redundant implicit (ON-less) joins that may have
        # been added by TableNode processing AFTER a JoinNode already added its
        # proper join for the same table.
        tables_with_proper_join = {j["table"] for j in ast["joins"] if j.get("on")}
        ast["joins"] = [
            j for j in ast["joins"]
            if j.get("on") or j["table"] not in tables_with_proper_join
        ]
        # Also remove any implicit join where the table equals the FROM table.
        from_tbl = ast["from"]["table"] if ast["from"] else ""
        if from_tbl:
            ast["joins"] = [
                j for j in ast["joins"]
                if not (j["table"] == from_tbl and not j.get("on"))
            ]

        # Inline aggregates into select list
        for agg in ast["aggregates"]:
            expr = f"{agg['func']}({agg['field']})"
            if agg.get("alias"):
                expr += f" AS {agg['alias']}"
            if expr not in ast["select"]:
                ast["select"].append(expr)

        # Inline CASE expressions into select list
        for case in ast["case"]:
            expr = ASTBuilder._build_case_expr(case)
            if expr and expr not in ast["select"]:
                ast["select"].append(expr)

        # Default select
        if not ast["select"]:
            ast["select"] = ["*"]

        return ast

    @staticmethod
    def _build_case_expr(case: dict) -> str:
        parts = ["CASE"]
        for when in case.get("whens", []):
            w = when.get("when", "").strip()
            t = when.get("then", "").strip()
            if w and t:
                parts.append(f"  WHEN {w} THEN {t}")
        else_val = case.get("else", "").strip()
        if else_val:
            parts.append(f"  ELSE {else_val}")
        parts.append("END")
        expr = "\n".join(parts)
        alias = case.get("alias", "").strip()
        if alias:
            expr += f" AS {alias}"
        return expr if len(parts) > 2 else ""
