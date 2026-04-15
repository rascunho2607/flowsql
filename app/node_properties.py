from __future__ import annotations
"""
node_properties.py — Right-side panel showing editable properties for the
selected node AND a live SQL preview with basic keyword highlighting.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QSpinBox, QPushButton, QScrollArea,
    QFrame, QSizePolicy, QPlainTextEdit, QApplication,
)

from app.flow_nodes import BaseNode

_TITLE_FONT = QFont("Segoe UI", 9, QFont.Bold)
_LABEL_FONT = QFont("Segoe UI", 8)
_SQL_FONT   = QFont("Consolas", 9)

_SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL",
    "OUTER", "CROSS", "ON", "AND", "OR", "NOT", "AS", "DISTINCT", "TOP",
    "GROUP", "BY", "HAVING", "ORDER", "LIMIT", "OFFSET", "INSERT", "UPDATE",
    "DELETE", "CASE", "WHEN", "THEN", "ELSE", "END", "IN", "IS", "NULL",
    "LIKE", "BETWEEN", "EXISTS", "UNION", "ALL", "ASC", "DESC", "COUNT",
    "SUM", "AVG", "MAX", "MIN",
}


class _SqlHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, theme: str = "dark"):
        super().__init__(doc)
        self._theme = theme
        self._kw_fmt = QTextCharFormat()
        self._apply_theme(theme)

    def _apply_theme(self, theme: str):
        self._theme = theme
        kw_color = "#569cd6" if theme == "dark" else "#0000cc"
        self._kw_fmt.setForeground(QColor(kw_color))
        self._kw_fmt.setFontWeight(QFont.Bold)
        self.rehighlight()

    def highlightBlock(self, text: str):
        import re
        for m in re.finditer(r"\b[A-Z_]+\b", text.upper()):
            word = m.group()
            if word in _SQL_KEYWORDS:
                self.setFormat(m.start(), m.end() - m.start(), self._kw_fmt)

    def set_theme(self, theme: str):
        self._apply_theme(theme)


# ── Field builders ────────────────────────────────────────────────────────────

def _label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_LABEL_FONT)
    lbl.setObjectName("prop_label")
    return lbl


def _edit(value: str, placeholder: str = "") -> QLineEdit:
    ed = QLineEdit(str(value))
    ed.setPlaceholderText(placeholder)
    ed.setFont(QFont("Consolas", 9))
    return ed


def _combo(options: list, current: str) -> QComboBox:
    cb = QComboBox()
    for o in options:
        cb.addItem(o)
    idx = cb.findText(current)
    if idx >= 0:
        cb.setCurrentIndex(idx)
    return cb


class _ListEditor(QWidget):
    """Editable list of strings with + / - buttons."""

    changed = pyqtSignal(list)

    def __init__(self, items: list, placeholder: str = "valor", parent=None):
        super().__init__(parent)
        self._placeholder = placeholder
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._editors: list[QLineEdit] = []

        for item in items:
            self._add_row(str(item))

        btn_add = QPushButton("+ Adicionar")
        btn_add.setObjectName("prop_add_btn")
        btn_add.clicked.connect(lambda: (self._add_row(""), self._emit()))
        self._layout.addWidget(btn_add)

    def _add_row(self, value: str):
        row = QWidget()
        rl  = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        ed = QLineEdit(value)
        ed.setPlaceholderText(self._placeholder)
        ed.setFont(QFont("Consolas", 9))
        ed.textChanged.connect(self._emit)
        btn_rm = QPushButton("✕")
        btn_rm.setFixedWidth(22)
        btn_rm.setObjectName("prop_rm_btn")
        btn_rm.clicked.connect(lambda: self._remove_row(row, ed))
        rl.addWidget(ed, 1)
        rl.addWidget(btn_rm)
        self._editors.append(ed)
        # Insert before the last widget (the "+ Adicionar" button)
        self._layout.insertWidget(self._layout.count() - 1, row)

    def _remove_row(self, row: QWidget, ed: QLineEdit):
        self._editors.remove(ed)
        row.setParent(None)
        row.deleteLater()
        self._emit()

    def _emit(self):
        self.changed.emit([ed.text() for ed in self._editors])

    def values(self) -> list:
        return [ed.text() for ed in self._editors]


# ── Main panel ────────────────────────────────────────────────────────────────

class NodePropertiesPanel(QWidget):
    """Right-side panel: node properties + live SQL preview."""

    execute_sql_requested = pyqtSignal(str)   # "Run" button in SQL preview
    open_in_editor        = pyqtSignal(str)   # "Open in Editor" button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("node_properties_panel")
        self.setFixedWidth(210)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header = QLabel("  Propriedades")
        header.setObjectName("palette_header")
        header.setFixedHeight(28)
        header.setFont(_TITLE_FONT)
        root.addWidget(header)

        # ── Scrollable properties area ─────────────────────────────────────
        props_scroll = QScrollArea()
        props_scroll.setWidgetResizable(True)
        props_scroll.setFrameShape(QFrame.NoFrame)
        props_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._props_widget = QWidget()
        self._props_layout = QVBoxLayout(self._props_widget)
        self._props_layout.setContentsMargins(8, 8, 8, 8)
        self._props_layout.setSpacing(4)
        self._props_layout.addStretch()
        props_scroll.setWidget(self._props_widget)
        root.addWidget(props_scroll, 1)

        # ── Separator ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        # ── SQL preview ───────────────────────────────────────────────────
        sql_header = QLabel("  SQL Gerado")
        sql_header.setObjectName("palette_header")
        sql_header.setFixedHeight(24)
        sql_header.setFont(_LABEL_FONT)
        root.addWidget(sql_header)

        self._sql_preview = QPlainTextEdit()
        self._sql_preview.setObjectName("sql_preview")
        self._sql_preview.setReadOnly(True)
        self._sql_preview.setFont(_SQL_FONT)
        self._sql_preview.setMinimumHeight(120)
        self._sql_preview.setMaximumHeight(200)
        self._highlighter = _SqlHighlighter(self._sql_preview.document())
        root.addWidget(self._sql_preview)

        # ── SQL preview buttons ────────────────────────────────────────────
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(4, 2, 4, 2)
        btn_layout.setSpacing(4)

        btn_copy = QPushButton("Copiar")
        btn_copy.setObjectName("prop_sql_btn")
        btn_copy.clicked.connect(self._copy_sql)

        btn_exec = QPushButton("▶ Executar")
        btn_exec.setObjectName("btn_execute")
        btn_exec.clicked.connect(
            lambda: self.execute_sql_requested.emit(self._sql_preview.toPlainText())
        )

        btn_editor = QPushButton("↗ Editor")
        btn_editor.setObjectName("prop_sql_btn")
        btn_editor.clicked.connect(
            lambda: self.open_in_editor.emit(self._sql_preview.toPlainText())
        )

        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_exec)
        btn_layout.addWidget(btn_editor)
        root.addWidget(btn_row)

        self._current_node: BaseNode | None = None
        self._theme = "dark"

    # ── Public API ────────────────────────────────────────────────────────────
    def set_theme(self, theme: str):
        self._theme = theme
        self._highlighter.set_theme(theme)

    def set_sql(self, sql: str):
        self._sql_preview.setPlainText(sql)

    def show_node(self, node: BaseNode | None):
        self._current_node = node
        self._clear_props()
        if node is None:
            return
        self._build_props(node)

    # ── Props building ────────────────────────────────────────────────────────
    def _clear_props(self):
        # Remove all widgets except the trailing stretch
        while self._props_layout.count() > 1:
            item = self._props_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _build_props(self, node: BaseNode):
        lo = self._props_layout

        # Node type badge
        badge = QLabel(node.label())
        badge.setObjectName("prop_type_badge")
        badge.setFont(_TITLE_FONT)
        badge.setAlignment(Qt.AlignCenter)
        lo.insertWidget(lo.count() - 1, badge)

        # Node ID (read-only info)
        id_lbl = QLabel(f"id: {node.node_id}")
        id_lbl.setObjectName("prop_id_label")
        id_lbl.setFont(QFont("Consolas", 7))
        id_lbl.setAlignment(Qt.AlignRight)
        lo.insertWidget(lo.count() - 1, id_lbl)

        ntype = node.node_type

        if ntype == "table":
            self._field("nome",    node, "name",  "ex: users")
            self._field("alias",   node, "alias", "ex: u")

        elif ntype == "join":
            self._combo_field("tipo", node, "join_type",
                              ["INNER", "LEFT", "RIGHT", "FULL OUTER", "CROSS"])
            # Pair conditions are set via port connections; show read-only summary
            pairs = node._data.get("pairs", [])
            if pairs:
                lo.insertWidget(lo.count() - 1, _label("condições ON:"))
                for p in pairs:
                    lbl = _label(f"{p.get('left_field','')} = {p.get('right_field','')}")
                    lo.insertWidget(lo.count() - 1, lbl)
            else:
                lo.insertWidget(lo.count() - 1, _label("(conecte portas de campo)"))

        elif ntype == "select":
            self._select_editor(node)

        elif ntype == "where":
            self._where_editor(node)

        elif ntype == "having":
            self._combo_field("operador", node, "operator", ["AND", "OR"])
            self._list_field("condições", node, "conditions")

        elif ntype == "group_by":
            self._list_field("campos", node, "fields")

        elif ntype == "order_by":
            self._order_by_editor(node)

        elif ntype == "limit":
            self._spin_field("LIMIT",  node, "value",  0, 1_000_000)
            self._spin_field("OFFSET", node, "offset", 0, 1_000_000)

        elif ntype == "aggregate":
            self._combo_field("função", node, "func",
                              ["COUNT", "SUM", "AVG", "MAX", "MIN"])
            self._field("campo", node, "field", "ex: o.total")
            self._field("alias", node, "alias", "ex: total")

        elif ntype == "case":
            self._case_editor(node)

        elif ntype == "result":
            rc  = node.get_data("row_count")
            ela = node.get_data("elapsed_ms")
            lo.insertWidget(lo.count() - 1, _label(f"Linhas: {rc if rc is not None else '—'}"))
            lo.insertWidget(lo.count() - 1, _label(f"Tempo:  {ela} ms" if ela is not None else "Tempo: —"))

        elif ntype == "function":
            self._function_editor(node)

        elif ntype == "procedure":
            self._procedure_editor(node)

        elif ntype == "union":
            self._combo_field("tipo", node, "union_type",
                              ["UNION", "UNION ALL", "INTERSECT", "EXCEPT"])

        elif ntype == "update":
            self._update_editor(node)

        elif ntype == "delete":
            self._delete_editor(node)

    # ── Field helpers ─────────────────────────────────────────────────────────
    def _field(self, label: str, node: BaseNode, key: str, placeholder: str = ""):
        lbl  = _label(label)
        edit = _edit(node.get_data(key, ""), placeholder)
        edit.textChanged.connect(lambda v: self._on_change(node, key, v))
        self._props_layout.insertWidget(self._props_layout.count() - 1, lbl)
        self._props_layout.insertWidget(self._props_layout.count() - 1, edit)

    def _combo_field(self, label: str, node: BaseNode, key: str, options: list):
        lbl = _label(label)
        cb  = _combo(options, node.get_data(key, options[0]))
        cb.currentTextChanged.connect(lambda v: self._on_change(node, key, v))
        self._props_layout.insertWidget(self._props_layout.count() - 1, lbl)
        self._props_layout.insertWidget(self._props_layout.count() - 1, cb)

    def _check_field(self, label: str, node: BaseNode, key: str):
        chk = QCheckBox(label)
        chk.setChecked(bool(node.get_data(key, False)))
        chk.toggled.connect(lambda v: self._on_change(node, key, v))
        self._props_layout.insertWidget(self._props_layout.count() - 1, chk)

    def _spin_field(self, label: str, node: BaseNode, key: str,
                    min_val: int, max_val: int):
        lbl = _label(label)
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(int(node.get_data(key, 0)))
        spin.valueChanged.connect(lambda v: self._on_change(node, key, v))
        self._props_layout.insertWidget(self._props_layout.count() - 1, lbl)
        self._props_layout.insertWidget(self._props_layout.count() - 1, spin)

    def _list_field(self, label: str, node: BaseNode, key: str):
        lbl    = _label(label)
        editor = _ListEditor(node.get_data(key, []))
        editor.changed.connect(lambda v: self._on_change(node, key, v))
        self._props_layout.insertWidget(self._props_layout.count() - 1, lbl)
        self._props_layout.insertWidget(self._props_layout.count() - 1, editor)

    def _order_by_editor(self, node: BaseNode):
        lbl = _label("campos")
        self._props_layout.insertWidget(self._props_layout.count() - 1, lbl)
        for i, entry in enumerate(node.get_data("fields", [])):
            name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
            direction = entry.get("direction", "ASC") if isinstance(entry, dict) else "ASC"
            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            ed = QLineEdit(name)
            ed.setFont(QFont("Consolas", 9))
            cb = _combo(["ASC", "DESC"], direction)

            def _make_updater(idx):
                def _update(*_):
                    fields = list(node.get_data("fields", []))
                    if idx < len(fields):
                        fields[idx] = {
                            "name": ed.text(),
                            "direction": cb.currentText(),
                        }
                        self._on_change(node, "fields", fields)
                return _update

            upd = _make_updater(i)
            ed.textChanged.connect(upd)
            cb.currentTextChanged.connect(upd)
            rl.addWidget(ed, 1)
            rl.addWidget(cb)
            self._props_layout.insertWidget(self._props_layout.count() - 1, row)

    def _case_editor(self, node: BaseNode):
        self._list_field("alias", node, "alias_dummy")  # reuse as single field
        self._field("alias", node, "alias", "ex: categoria")
        whens = node.get_data("whens", [])
        lbl = _label("WHEN / THEN")
        self._props_layout.insertWidget(self._props_layout.count() - 1, lbl)
        for i, when in enumerate(whens):
            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)
            w_ed = QLineEdit(when.get("when", ""))
            w_ed.setPlaceholderText("WHEN")
            t_ed = QLineEdit(when.get("then", ""))
            t_ed.setPlaceholderText("THEN")

            def _make_upd(idx):
                def _upd(*_):
                    ws = list(node.get_data("whens", []))
                    if idx < len(ws):
                        ws[idx] = {"when": w_ed.text(), "then": t_ed.text()}
                        self._on_change(node, "whens", ws)
                return _upd

            upd = _make_upd(i)
            w_ed.textChanged.connect(upd)
            t_ed.textChanged.connect(upd)
            rl.addWidget(w_ed, 1)
            rl.addWidget(t_ed, 1)
            self._props_layout.insertWidget(self._props_layout.count() - 1, row)

        self._field("ELSE", node, "else_value", "valor padrão")

    def _where_editor(self, node: BaseNode):
        """Build the WhereNode properties UI."""
        lo = self._props_layout
        _COND_OPS = ["=", "<>", ">", "<", ">=", "<=",
                     "IS NULL", "IS NOT NULL", "LIKE", "IN", "BETWEEN",
                     "IS NOT NULL AND <> ''"]
        _NO_VALUE_OPS = {"IS NULL", "IS NOT NULL", "IS NOT NULL AND <> ''"}

        # AND / OR toggle
        op_lbl = _label("operador")
        op_cb  = _combo(["AND", "OR"], node._data.get("operator", "AND"))
        op_cb.currentTextChanged.connect(
            lambda v: self._on_change(node, "operator", v)
        )
        lo.insertWidget(lo.count() - 1, op_lbl)
        lo.insertWidget(lo.count() - 1, op_cb)

        conditions = node._data.get("conditions", [])
        available  = getattr(node, "_available_columns", [])

        for i, cond in enumerate(conditions):
            field_val = cond.get("field", "")
            cond_op   = cond.get("op", "=")
            val_val   = cond.get("value", "")
            is_connected = any(
                p.port_id == f"in_field_{i}" and p.connected
                for p in node.in_ports
            )

            row_w = QWidget()
            row_l = QVBoxLayout(row_w)
            row_l.setContentsMargins(0, 2, 0, 2)
            row_l.setSpacing(2)

            # ── Field widget ─────────────────────────────────────────────
            if is_connected:
                # Read-only when driven by a port connection
                field_w = QLabel(field_val if field_val else "(via porta)")
                field_w.setFont(QFont("Consolas", 9))
            elif available:
                field_w = QComboBox()
                field_w.addItem("")
                for col in available:
                    field_w.addItem(col.get("name", str(col)))
                idx = field_w.findText(field_val)
                if idx >= 0:
                    field_w.setCurrentIndex(idx)

                def _make_field_updater(ci, fw):
                    def _upd(txt):
                        conds = list(node._data.get("conditions", []))
                        if ci < len(conds):
                            conds[ci]["field"] = txt
                            self._on_change(node, "conditions", conds)
                    return _upd

                field_w.currentTextChanged.connect(_make_field_updater(i, field_w))
            else:
                field_w = QLineEdit(field_val)
                field_w.setPlaceholderText("campo")
                field_w.setFont(QFont("Consolas", 9))

                def _make_field_le_updater(ci, fw):
                    def _upd(txt):
                        conds = list(node._data.get("conditions", []))
                        if ci < len(conds):
                            conds[ci]["field"] = txt
                            self._on_change(node, "conditions", conds)
                    return _upd

                field_w.textChanged.connect(_make_field_le_updater(i, field_w))

            # ── Operator combo ───────────────────────────────────────────
            op_combo = _combo(_COND_OPS, cond_op)

            # ── Value line edit ──────────────────────────────────────────
            val_edit = QLineEdit(val_val)
            val_edit.setPlaceholderText("valor")
            val_edit.setFont(QFont("Consolas", 9))
            val_edit.setVisible(cond_op not in _NO_VALUE_OPS)

            def _make_op_updater(ci, ve):
                def _upd(op_str):
                    conds = list(node._data.get("conditions", []))
                    if ci < len(conds):
                        conds[ci]["op"] = op_str
                        self._on_change(node, "conditions", conds)
                    ve.setVisible(op_str not in _NO_VALUE_OPS)
                return _upd

            def _make_val_updater(ci):
                def _upd(txt):
                    conds = list(node._data.get("conditions", []))
                    if ci < len(conds):
                        conds[ci]["value"] = txt
                        self._on_change(node, "conditions", conds)
                return _upd

            op_combo.currentTextChanged.connect(_make_op_updater(i, val_edit))
            val_edit.textChanged.connect(_make_val_updater(i))

            row_l.addWidget(field_w)
            row_l.addWidget(op_combo)
            row_l.addWidget(val_edit)
            lo.insertWidget(lo.count() - 1, row_w)

    def _on_change(self, node: BaseNode, key: str, value):
        node.set_data(key, value)

    # ── SelectNode props ──────────────────────────────────────────────────────
    def _select_editor(self, node: BaseNode):
        lo = self._props_layout
        self._check_field("DISTINCT", node, "distinct")

        available = getattr(node, "_available_columns", [])
        selected  = node._data.get("fields", [])

        if available:
            from PyQt5.QtWidgets import QScrollArea as _SA, QCheckBox as _CB
            lo.insertWidget(lo.count() - 1, _label("colunas:"))
            col_area = QWidget()
            col_lo   = QVBoxLayout(col_area)
            col_lo.setContentsMargins(0, 0, 0, 0)
            col_lo.setSpacing(1)

            def _make_toggler(col_name):
                def _tog(checked):
                    fields = list(node._data.get("fields", []))
                    if checked and col_name not in fields:
                        fields.append(col_name)
                    elif not checked and col_name in fields:
                        fields.remove(col_name)
                    self._on_change(node, "fields", fields)
                return _tog

            for col in available:
                name = col.get("name", str(col)) if isinstance(col, dict) else str(col)
                cb   = QCheckBox(name)
                cb.setChecked(name in selected or not selected)
                cb.toggled.connect(_make_toggler(name))
                col_lo.addWidget(cb)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(col_area)
            scroll.setMaximumHeight(120)
            scroll.setFrameShape(QFrame.NoFrame)
            lo.insertWidget(lo.count() - 1, scroll)
        else:
            self._list_field("campos", node, "fields")

    # ── FunctionNode props ────────────────────────────────────────────────────
    def _function_editor(self, node: BaseNode):
        lo = self._props_layout
        from app.flow_nodes import _FUNC_NAMES

        # Mode selector
        mode_lbl = _label("modo")
        mode_cb  = _combo(["simples", "fórmula"],
                          "fórmula" if node._data.get("mode") == "formula" else "simples")

        # Simple mode widgets
        func_lbl  = _label("função")
        func_cb   = _combo(_FUNC_NAMES, node._data.get("func", "SUM"))

        # Formula mode widgets
        formula_lbl  = _label("fórmula")
        formula_edit = QPlainTextEdit(node._data.get("formula", ""))
        formula_edit.setFont(QFont("Consolas", 9))
        formula_edit.setMaximumHeight(60)

        # Alias (always shown)
        alias_lbl  = _label("alias")
        alias_edit = _edit(node._data.get("alias", ""), "ex: total")

        def _set_mode(mode_str: str):
            is_simple = (mode_str == "simples")
            func_lbl.setVisible(is_simple)
            func_cb.setVisible(is_simple)
            formula_lbl.setVisible(not is_simple)
            formula_edit.setVisible(not is_simple)
            self._on_change(node, "mode", "simple" if is_simple else "formula")
            node._rebuild_input_ports()

        mode_cb.currentTextChanged.connect(_set_mode)
        func_cb.currentTextChanged.connect(lambda v: self._on_change(node, "func", v))
        formula_edit.textChanged.connect(
            lambda: self._on_change(node, "formula", formula_edit.toPlainText())
        )
        alias_edit.textChanged.connect(lambda v: self._on_change(node, "alias", v))

        for w in (mode_lbl, mode_cb, func_lbl, func_cb,
                  formula_lbl, formula_edit, alias_lbl, alias_edit):
            lo.insertWidget(lo.count() - 1, w)

        # Apply initial visibility
        _set_mode(mode_cb.currentText())

    # ── ProcedureNode props ───────────────────────────────────────────────────
    def _procedure_editor(self, node: BaseNode):
        lo = self._props_layout
        name = node._data.get("name", "")
        lo.insertWidget(lo.count() - 1, _label(f"Procedure: {name}"))

        for p in node._data.get("params_in", []):
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            row_l.addWidget(_label(f"IN  {p['name']}:"))
            val_ed = _edit(p.get("value", ""), "valor")

            def _make_param_updater(param, editor):
                def _upd(txt):
                    param["value"] = txt
                    self._on_change(node, "params_in", node._data.get("params_in", []))
                return _upd

            val_ed.textChanged.connect(_make_param_updater(p, val_ed))
            row_l.addWidget(val_ed, 1)
            lo.insertWidget(lo.count() - 1, row_w)

        for p in node._data.get("params_out", []):
            lo.insertWidget(lo.count() - 1, _label(f"OUT {p['name']} ({p.get('type','')})"))



    # ── UpdateNode props ──────────────────────────────────────────────────────
    def _update_editor(self, node: BaseNode):
        lo = self._props_layout

        self._check_field("Confirmar execução", node, "confirm")

        # Amber warning
        warn = QLabel("⚠ Modifica dados existentes")
        warn.setObjectName("prop_warn_amber")
        warn.setFont(_LABEL_FONT)
        warn.setStyleSheet("color: #f59e0b; font-weight: bold;")
        warn.setWordWrap(True)
        lo.insertWidget(lo.count() - 1, warn)

        sets = node._data.get("sets", [])
        if sets:
            lo.insertWidget(lo.count() - 1, _label("Colunas SET:"))
        for i, s in enumerate(sets):
            col  = s.get("col", "")
            val  = s.get("val", "")
            is_connected = any(
                p.port_id == f"in_set_{i}" and p.connected
                for p in node.in_ports
            )
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)

            if is_connected:
                col_w = QLabel(col or "(via porta)")
                col_w.setFont(QFont("Consolas", 9))
            else:
                col_w = QLineEdit(col)
                col_w.setPlaceholderText("coluna")
                col_w.setFont(QFont("Consolas", 9))

                def _make_col_upd(ci, fw):
                    def _upd(txt):
                        ss = list(node._data.get("sets", []))
                        if ci < len(ss):
                            ss[ci]["col"] = txt
                            self._on_change(node, "sets", ss)
                    return _upd

                col_w.textChanged.connect(_make_col_upd(i, col_w))

            row_l.addWidget(col_w, 1)
            row_l.addWidget(QLabel("="))

            val_w = QLineEdit(val)
            val_w.setPlaceholderText("valor")
            val_w.setFont(QFont("Consolas", 9))

            def _make_val_upd(ci, vw):
                def _upd(txt):
                    ss = list(node._data.get("sets", []))
                    if ci < len(ss):
                        ss[ci]["val"] = txt
                        self._on_change(node, "sets", ss)
                return _upd

            val_w.textChanged.connect(_make_val_upd(i, val_w))
            row_l.addWidget(val_w, 1)
            lo.insertWidget(lo.count() - 1, row_w)

    # ── DeleteNode props ──────────────────────────────────────────────────────
    def _delete_editor(self, node: BaseNode):
        lo = self._props_layout

        self._check_field("Confirmar exclusão", node, "confirm")

        warn = QLabel("⛔ Esta operação é irreversível e não pode ser desfeita.")
        warn.setObjectName("prop_warn_red")
        warn.setFont(_LABEL_FONT)
        warn.setStyleSheet("color: #ef4444; font-weight: bold;")
        warn.setWordWrap(True)
        lo.insertWidget(lo.count() - 1, warn)

    # ── SQL copy ──────────────────────────────────────────────────────────────
    def _copy_sql(self):
        sql = self._sql_preview.toPlainText()
        if sql:
            QApplication.clipboard().setText(sql)
