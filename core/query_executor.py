from __future__ import annotations

import time
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal


class QueryExecutor(QThread):
    """
    Executes SQL queries in a background thread.
    Never touches the UI — communicates via signals.
    """

    result_ready = pyqtSignal(object)   # list[dict]  — rows as list of dicts
    columns_ready = pyqtSignal(list)    # list[str]   — column names
    error_occurred = pyqtSignal(str)    # error message string
    execution_time = pyqtSignal(float)  # duration in milliseconds
    row_count = pyqtSignal(int)         # number of affected/returned rows
    message = pyqtSignal(str)           # info/success message

    def __init__(self, engine, sql: str, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._sql = sql
        self._cancelled = False

    # ── Public ────────────────────────────────────────────────────────────────

    def cancel(self):
        self._cancelled = True
        self.requestInterruption()

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self):
        from sqlalchemy import text

        statements = self._split_statements(self._sql)
        total_rows = 0
        start = time.perf_counter()

        for stmt in statements:
            if self._cancelled or self.isInterruptionRequested():
                self.message.emit("Consulta cancelada pelo usuário.")
                return

            stmt = stmt.strip()
            if not stmt:
                continue

            try:
                with self._engine.connect() as conn:
                    result = conn.execute(text(stmt))

                    if result.returns_rows:
                        keys = list(result.keys())
                        rows = [dict(zip(keys, row)) for row in result.fetchall()]
                        elapsed = (time.perf_counter() - start) * 1000
                        self.columns_ready.emit(keys)
                        self.result_ready.emit(rows)
                        self.row_count.emit(len(rows))
                        self.execution_time.emit(elapsed)
                        total_rows += len(rows)
                        self.message.emit(
                            f"Consulta executada com êxito. ({len(rows)} linha(s) retornada(s))  [{elapsed:.0f} ms]"
                        )
                    else:
                        conn.commit()
                        affected = result.rowcount if result.rowcount >= 0 else 0
                        elapsed = (time.perf_counter() - start) * 1000
                        self.row_count.emit(affected)
                        self.execution_time.emit(elapsed)
                        self.result_ready.emit([])
                        self.columns_ready.emit([])
                        self.message.emit(
                            f"Comando executado com êxito. ({affected} linha(s) afetada(s))  [{elapsed:.0f} ms]"
                        )

            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                self.execution_time.emit(elapsed)
                self.error_occurred.emit(str(exc))
                return

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _split_statements(sql: str) -> List[str]:
        """
        Split SQL by semicolons, but not those inside strings or comments.
        Simple implementation suitable for most cases.
        """
        statements = []
        current = []
        in_single_quote = False
        in_double_quote = False
        in_line_comment = False
        in_block_comment = False
        i = 0
        chars = sql

        while i < len(chars):
            ch = chars[i]
            nxt = chars[i + 1] if i + 1 < len(chars) else ""

            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                current.append(ch)
            elif in_block_comment:
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    current.append(ch)
                    current.append(nxt)
                    i += 2
                    continue
                else:
                    current.append(ch)
            elif in_single_quote:
                current.append(ch)
                if ch == "'" and nxt != "'":
                    in_single_quote = False
                elif ch == "'" and nxt == "'":
                    current.append(nxt)
                    i += 2
                    continue
            elif in_double_quote:
                current.append(ch)
                if ch == '"':
                    in_double_quote = False
            else:
                if ch == "-" and nxt == "-":
                    in_line_comment = True
                    current.append(ch)
                elif ch == "/" and nxt == "*":
                    in_block_comment = True
                    current.append(ch)
                elif ch == "'":
                    in_single_quote = True
                    current.append(ch)
                elif ch == '"':
                    in_double_quote = True
                    current.append(ch)
                elif ch == ";":
                    stmt = "".join(current).strip()
                    if stmt:
                        statements.append(stmt)
                    current = []
                else:
                    current.append(ch)

            i += 1

        # Remaining statement (no trailing semicolon)
        remaining = "".join(current).strip()
        if remaining:
            statements.append(remaining)

        return statements if statements else [sql]
