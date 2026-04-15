from __future__ import annotations

import difflib
import re
from typing import Dict, List, Set

from PyQt5.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QCompleter, QAbstractItemView
from PyQt5.QtCore import Qt, QRect, QSize, pyqtSignal, QStringListModel, QPoint, QTimer
from PyQt5.QtGui import (
    QColor, QTextFormat, QPainter, QSyntaxHighlighter, QTextCharFormat,
    QFont, QFontMetrics, QKeySequence, QTextCursor
)


# ── SQL Keywords & Functions ──────────────────────────────────────────────────

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL",
    "OUTER", "CROSS", "ON", "AS", "AND", "OR", "NOT", "IN", "BETWEEN",
    "LIKE", "IS", "NULL", "ORDER", "BY", "GROUP", "HAVING", "LIMIT",
    "OFFSET", "UNION", "ALL", "DISTINCT", "INSERT", "UPDATE", "DELETE",
    "INTO", "VALUES", "SET", "CREATE", "DROP", "ALTER", "TABLE", "VIEW",
    "INDEX", "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "DEFAULT",
    "CONSTRAINT", "UNIQUE", "CHECK", "WITH", "CASE", "WHEN", "THEN",
    "ELSE", "END", "EXISTS", "TOP", "PROCEDURE", "FUNCTION", "TRIGGER",
    "SCHEMA", "DATABASE", "USE", "EXEC", "BEGIN", "COMMIT", "ROLLBACK",
    "TRUNCATE", "GRANT", "REVOKE", "DECLARE", "CURSOR", "FETCH", "OPEN",
    "CLOSE", "DEALLOCATE", "RETURN", "IF", "ELSE", "WHILE", "BREAK",
    "CONTINUE", "GOTO", "PRINT", "RAISERROR", "TRY", "CATCH", "THROW",
    "MERGE", "MATCHED", "OUTPUT", "INSERTED", "DELETED", "OVER",
    "PARTITION", "ROWS", "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING",
    "CURRENT", "ROW", "ASC", "DESC", "NULLS", "FIRST", "LAST", "TRANSACTION"
}

SQL_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MAX", "MIN", "COALESCE", "ISNULL", "NULLIF",
    "CAST", "CONVERT", "LEN", "LENGTH", "SUBSTRING", "SUBSTR", "TRIM",
    "LTRIM", "RTRIM", "UPPER", "LOWER", "REPLACE", "CHARINDEX", "PATINDEX",
    "STUFF", "REVERSE", "SPACE", "REPLICATE", "CONCAT", "STRING_AGG",
    "GETDATE", "GETUTCDATE", "SYSDATETIME", "NOW", "CURDATE", "CURTIME",
    "YEAR", "MONTH", "DAY", "DATEPART", "DATEDIFF", "DATEADD", "FORMAT",
    "ROUND", "CEILING", "FLOOR", "ABS", "POWER", "SQRT", "LOG", "LOG10",
    "EXP", "SIGN", "RAND", "NEWID", "ROW_NUMBER", "RANK", "DENSE_RANK",
    "NTILE", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE", "IIF",
    "CHOOSE", "PARSE", "TRY_CAST", "TRY_CONVERT", "TRY_PARSE",
    "SCOPE_IDENTITY", "IDENT_CURRENT", "OBJECT_ID", "OBJECT_NAME",
    "COL_NAME", "TYPE_NAME", "COLUMNPROPERTY", "OBJECTPROPERTY",
}


# ── Syntax Highlighter ────────────────────────────────────────────────────────

class SqlHighlighter(QSyntaxHighlighter):
    """QSyntaxHighlighter for SQL. Theme-aware via apply_theme()."""

    def __init__(self, document, theme: str = "dark"):
        super().__init__(document)
        self._theme = theme
        self._rules: list[tuple] = []
        self._build_rules()

    def apply_theme(self, theme: str):
        self._theme = theme
        self._build_rules()
        self.rehighlight()

    def _fmt(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build_rules(self):
        dark = self._theme == "dark"
        self._rules = []

        # Keywords
        kw_color = "#569cd6" if dark else "#0000ff"
        kw_fmt = self._fmt(kw_color, bold=True)
        kw_pattern = r"\b(" + "|".join(SQL_KEYWORDS) + r")\b"
        self._rules.append((re.compile(kw_pattern, re.IGNORECASE), kw_fmt))

        # Functions
        fn_color = "#dcdcaa" if dark else "#795e26"
        fn_fmt = self._fmt(fn_color)
        fn_pattern = r"\b(" + "|".join(SQL_FUNCTIONS) + r")\b"
        self._rules.append((re.compile(fn_pattern, re.IGNORECASE), fn_fmt))

        # Numbers
        num_color = "#b5cea8" if dark else "#098658"
        self._rules.append((re.compile(r"\b\d+(\.\d+)?\b"), self._fmt(num_color)))

        # Single-line comment
        cmt_color = "#6a9955" if dark else "#008000"
        self._line_comment_fmt = self._fmt(cmt_color, italic=True)
        self._rules.append((re.compile(r"--[^\n]*"), self._line_comment_fmt))

        # Strings (single-quoted)
        str_color = "#ce9178" if dark else "#a31515"
        self._string_fmt = self._fmt(str_color)

        # Block comment (handled separately in highlightBlock)
        self._block_comment_fmt = self._fmt(cmt_color, italic=True)

        # Operators
        op_color = "#d4d4d4" if dark else "#1e1e1e"
        self._rules.append((
            re.compile(r"[=<>!]+|(\bAND\b|\bOR\b|\bNOT\b)", re.IGNORECASE),
            self._fmt(op_color)
        ))

    # States for multi-line block comments
    _NORMAL = 0
    _IN_BLOCK_COMMENT = 1

    def highlightBlock(self, text: str):
        # Apply single-line rules first (except strings handled specially)
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Strings: handle '' escapes
        str_pattern = re.compile(r"'(?:[^']|'')*'")
        for m in str_pattern.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._string_fmt)

        # Block comments (multi-line state machine)
        self.setCurrentBlockState(self._NORMAL)
        start_expr = re.compile(r"/\*")
        end_expr = re.compile(r"\*/")

        start_pos = 0
        if self.previousBlockState() == self._IN_BLOCK_COMMENT:
            end_match = end_expr.search(text)
            if end_match:
                self.setFormat(0, end_match.end(), self._block_comment_fmt)
                start_pos = end_match.end()
            else:
                self.setFormat(0, len(text), self._block_comment_fmt)
                self.setCurrentBlockState(self._IN_BLOCK_COMMENT)
                return

        while True:
            sm = start_expr.search(text, start_pos)
            if not sm:
                break
            em = end_expr.search(text, sm.end())
            if em:
                self.setFormat(sm.start(), em.end() - sm.start(), self._block_comment_fmt)
                start_pos = em.end()
            else:
                self.setFormat(sm.start(), len(text) - sm.start(), self._block_comment_fmt)
                self.setCurrentBlockState(self._IN_BLOCK_COMMENT)
                break


# ── Line Number Area ──────────────────────────────────────────────────────────

class LineNumberArea(QWidget):
    """Painted widget shown to the left of the editor for line numbers."""

    def __init__(self, editor: "SqlEditorWidget"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


# ── SQL Editor Widget ─────────────────────────────────────────────────────────

class SqlEditorWidget(QPlainTextEdit):
    """
    Full-featured SQL editor:
    - Line numbers
    - Syntax highlighting
    - Current-line highlight
    - Autocomplete
    - SSMS keyboard shortcuts
    """

    execute_requested = pyqtSignal(str)   # emitted on F5 / Ctrl+Enter

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._schema_words: List[str] = []
        self._known_objects: Set[str] = set()
        self._schema_words_map: Dict[str, str] = {}   # lowercase → original-case
        self._autocomplete_enabled = True
        self._syntax_check_enabled = True
        self._object_check_enabled = True
        self._autocorrect_syntax_enabled = True
        self._autocorrect_objects_enabled = True

        # Font
        font = QFont("Consolas", 13)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # Tab stop
        metrics = QFontMetrics(font)
        self.setTabStopDistance(metrics.horizontalAdvance(" ") * 4)

        # Line wrap off (like SSMS)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Line number area
        self._line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_width(0)
        self._highlight_current_line()

        # Syntax highlighter
        self._highlighter = SqlHighlighter(self.document(), "dark")

        # Autocomplete
        self._completer = QCompleter(self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.activated.connect(self._insert_completion)
        self._update_completer_list()

        # Linter debounce timer
        self._lint_timer = QTimer(self)
        self._lint_timer.setSingleShot(True)
        self._lint_timer.setInterval(700)
        self._lint_timer.timeout.connect(self._run_lint)
        self.textChanged.connect(self._schedule_lint)

    # ── Settings toggles ──────────────────────────────────────────────────────

    def set_autocomplete_enabled(self, enabled: bool):
        self._autocomplete_enabled = enabled
        if not enabled:
            self._completer.popup().hide()

    def set_syntax_check_enabled(self, enabled: bool):
        self._syntax_check_enabled = enabled
        self._schedule_lint()

    def set_object_check_enabled(self, enabled: bool):
        self._object_check_enabled = enabled
        self._schedule_lint()

    def set_autocorrect_syntax_enabled(self, enabled: bool):
        self._autocorrect_syntax_enabled = enabled

    def set_autocorrect_objects_enabled(self, enabled: bool):
        self._autocorrect_objects_enabled = enabled

    # ── Theme ─────────────────────────────────────────────────────────────────

    def set_theme(self, theme: str):
        self._theme = theme
        self._highlighter.apply_theme(theme)
        self._highlight_current_line()

    # ── Schema words for autocomplete ─────────────────────────────────────────

    def set_schema_words(self, words: List[str]):
        """Set ALL autocomplete words (tables + views + procs + columns).
        Does NOT update _known_objects — call set_object_words() for that."""
        self._schema_words = words
        self._update_completer_list()
        self._schedule_lint()

    def set_object_words(self, words: List[str]):
        """Set DB object names (tables / views / procs) used by linter and autocorrect.
        Must be called separately from set_schema_words so that column names are
        NOT included in the fuzzy-match pool (which would cause false corrections)."""
        self._known_objects = {w.lower() for w in words}
        self._schema_words_map = {w.lower(): w for w in words}
        self._schedule_lint()

    def _update_completer_list(self):
        words = sorted(set(list(SQL_KEYWORDS) + list(SQL_FUNCTIONS) + self._schema_words))
        model = QStringListModel(words, self._completer)
        self._completer.setModel(model)

    # ── Line numbers ──────────────────────────────────────────────────────────

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        space = 6 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def _update_line_number_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event):
        painter = QPainter(self._line_number_area)

        if self._theme == "dark":
            bg_color = QColor("#1e1e1e")
            text_color = QColor("#4a4a4a")
            current_bg = QColor("#252526")
            current_text = QColor("#858585")
        else:
            bg_color = QColor("#f5f5f5")
            text_color = QColor("#aaaaaa")
            current_bg = QColor("#e8e8e8")
            current_text = QColor("#555555")

        painter.fillRect(event.rect(), bg_color)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        offset = self.contentOffset()
        top = round(self.blockBoundingGeometry(block).translated(offset).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        current_line = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_line:
                    painter.fillRect(
                        0, top, self._line_number_area.width() - 1,
                        self.fontMetrics().height(), current_bg
                    )
                    painter.setPen(current_text)
                else:
                    painter.setPen(text_color)
                painter.drawText(
                    0, top,
                    self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        # Keep existing lint underlines (those without FullWidthSelection)
        lint_sels = [
            s for s in self.extraSelections()
            if not s.format.property(QTextFormat.FullWidthSelection)
        ]
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            if self._theme == "dark":
                line_color = QColor("#282828")
            else:
                line_color = QColor("#fffbd1")
            sel.format.setBackground(line_color)
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            self.setExtraSelections([sel] + lint_sels)
        else:
            self.setExtraSelections(lint_sels)

    # ── Key handling ──────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        # Autocomplete navigation
        if self._completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab,
                                Qt.Key_Escape, Qt.Key_Backtab):
                event.ignore()
                return

        key = event.key()
        mods = event.modifiers()

        # F5 / Ctrl+Enter → execute
        if key == Qt.Key_F5 or (key in (Qt.Key_Return, Qt.Key_Enter) and mods == Qt.ControlModifier):
            sql = self._get_selected_or_all()
            self.execute_requested.emit(sql)
            return

        # Ctrl+] → indent
        if key == Qt.Key_BracketRight and mods == Qt.ControlModifier:
            self._indent_selection()
            return

        # Ctrl+[ → dedent
        if key == Qt.Key_BracketLeft and mods == Qt.ControlModifier:
            self._dedent_selection()
            return

        # Ctrl+L → select line
        if key == Qt.Key_L and mods == Qt.ControlModifier:
            self._select_current_line()
            return

        # Ctrl+D → duplicate line
        if key == Qt.Key_D and mods == Qt.ControlModifier:
            self._duplicate_line()
            return

        # Auto-closing brackets
        if key == Qt.Key_ParenLeft:
            self._insert_pair("(", ")")
            return
        if key == Qt.Key_BraceLeft:
            self._insert_pair("{", "}")
            return
        if key == Qt.Key_BracketLeft and mods == Qt.NoModifier:
            self._insert_pair("[", "]")
            return
        if key == Qt.Key_Apostrophe and mods == Qt.NoModifier:
            self._insert_pair("'", "'")
            return

        # Auto-correct on space / newline (before inserting the separator)
        if key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and mods == Qt.NoModifier:
            if self._autocorrect_syntax_enabled or self._autocorrect_objects_enabled:
                self._try_autocorrect_before_space()

        super().keyPressEvent(event)

        # Trigger autocomplete after typing
        if key not in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter,
                       Qt.Key_Escape, Qt.Key_Backspace):
            self._maybe_show_completer()

    def _get_selected_or_all(self) -> str:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return cursor.selectedText().replace("\u2029", "\n")
        return self.toPlainText()

    # ── Selection helpers ──────────────────────────────────────────────────────

    def _indent_selection(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfBlock)
        while cursor.position() <= end:
            cursor.insertText("    ")
            end += 4
            if not cursor.movePosition(QTextCursor.NextBlock):
                break
        cursor.endEditBlock()

    def _dedent_selection(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfBlock)
        while cursor.position() <= end:
            line_cursor = self.textCursor()
            line_cursor.setPosition(cursor.position())
            line_cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            line_text = line_cursor.selectedText()
            removed = 0
            for ch in line_text[:4]:
                if ch == " ":
                    removed += 1
                else:
                    break
            if removed:
                line_cursor.setPosition(cursor.position())
                for _ in range(removed):
                    line_cursor.deleteChar()
                end -= removed
            if not cursor.movePosition(QTextCursor.NextBlock):
                break
        cursor.endEditBlock()

    def comment_selection(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfBlock)
        while cursor.position() <= end:
            cursor.insertText("-- ")
            end += 3
            if not cursor.movePosition(QTextCursor.NextBlock):
                break
        cursor.endEditBlock()

    def uncomment_selection(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfBlock)
        while cursor.position() <= end:
            line_cursor = self.textCursor()
            line_cursor.setPosition(cursor.position())
            line_cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            line_text = line_cursor.selectedText()
            if line_text.startswith("-- "):
                line_cursor.setPosition(cursor.position())
                line_cursor.deleteChar()
                line_cursor.deleteChar()
                line_cursor.deleteChar()
                end -= 3
            elif line_text.startswith("--"):
                line_cursor.setPosition(cursor.position())
                line_cursor.deleteChar()
                line_cursor.deleteChar()
                end -= 2
            if not cursor.movePosition(QTextCursor.NextBlock):
                break
        cursor.endEditBlock()

    def _select_current_line(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)

    def _duplicate_line(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        text = cursor.selectedText()
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.insertText("\n" + text)
        self.setTextCursor(cursor)

    def _insert_pair(self, open_ch: str, close_ch: str):
        cursor = self.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(open_ch + selected + close_ch)
        else:
            cursor.insertText(open_ch + close_ch)
            cursor.movePosition(QTextCursor.Left)
            self.setTextCursor(cursor)

    # ── Autocomplete ──────────────────────────────────────────────────────────

    def _current_word(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        return cursor.selectedText()

    def _maybe_show_completer(self):
        if not self._autocomplete_enabled:
            return
        word = self._current_word()
        if len(word) < 2:
            self._completer.popup().hide()
            return

        self._completer.setCompletionPrefix(word)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setLeft(cr.left() + self.line_number_area_width())
        cr.setWidth(
            self._completer.popup().sizeHintForColumn(0)
            + self._completer.popup().verticalScrollBar().sizeHint().width()
            + 20
        )
        self._completer.complete(cr)

    def _insert_completion(self, completion: str):
        """Replace the whole word under the cursor with the chosen completion."""
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    # ── Fuzzy autocorrect ─────────────────────────────────────────────────────

    @staticmethod
    def _best_fuzzy_match(word: str, candidates, cutoff: float) -> str | None:
        """
        Find the best fuzzy match for *word* in *candidates*.
        Uses SequenceMatcher ratio but adds a length-proximity bonus so that
        a length-equal candidate beats a longer one even if the longer one has
        a slightly higher raw ratio (e.g. "form" → "from" not "format").
        """
        best_score: float = cutoff - 1e-9   # must exceed cutoff
        best_cand:  str | None = None
        for cand in candidates:
            ratio = difflib.SequenceMatcher(None, word, cand).ratio()
            if ratio < cutoff:
                continue
            # Penalise length difference so shorter/equal candidates are preferred
            len_diff = abs(len(cand) - len(word))
            adjusted = ratio - len_diff * 0.03
            if adjusted > best_score:
                best_score = adjusted
                best_cand  = cand
        return best_cand

    def _word_before_cursor(self) -> tuple:
        """Return (word, start, end) of the token immediately before the cursor."""
        cursor = self.textCursor()
        pos    = cursor.position()
        text   = self.toPlainText()
        end    = pos
        start  = end
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            start -= 1
        return text[start:end], start, end

    # Keywords after which the next identifier is a table / view / proc name.
    _TABLE_CONTEXT_KWS = frozenset([
        'from', 'join', 'into', 'update', 'exec', 'execute',
        'table', 'view', 'truncate',
    ])

    def _in_table_context(self, start: int) -> bool:
        """
        Return True when the cursor is in a "table-name position" —
        i.e. after FROM / JOIN / INTO / UPDATE / EXEC / EXECUTE / TABLE.
        This prevents correcting column names (e.g. idContrato) against
        the DB object list.
        """
        text = self.toPlainText()[:start]
        # Skip backwards past the word already handled by caller
        i = len(text) - 1
        while i >= 0 and text[i].isspace():
            i -= 1
        # If the immediately preceding token ends with a comma, check further
        # back to see if we're in a FROM … , … table list
        if i >= 0 and text[i] == ',':
            # Comma-separated table list: scan back for a FROM/JOIN
            snippet = text[:i].upper()
            tokens = re.findall(r'\b([A-Z]+)\b', snippet)
            for tok in reversed(tokens):
                if tok in ('FROM', 'JOIN', 'INTO', 'UPDATE', 'TRUNCATE', 'EXEC', 'EXECUTE', 'TABLE', 'VIEW'):
                    return True
                # Stop at any clause boundary so we don't search the whole doc
                if tok in ('SELECT', 'WHERE', 'SET', 'HAVING', 'ON', 'BEGIN', 'DECLARE'):
                    return False
            return False
        # General case: find last SQL keyword before current word
        tokens = re.findall(r'\b([a-zA-Z_]\w*)\b', text)
        for tok in reversed(tokens):
            tok_l = tok.lower()
            if tok_l in self._TABLE_CONTEXT_KWS:
                return True
            if tok_l in SQL_KEYWORDS and tok_l not in self._TABLE_CONTEXT_KWS:
                return False
        return False

    @staticmethod
    def _looks_like_identifier(word: str) -> bool:
        """
        Return True when the word looks like a user-defined identifier rather
        than a mistyped SQL keyword, so we do NOT autocorrect it against keywords.

        Heuristics:
          * Contains an underscore  →  snake_case  (id_contrato, num_licitacao)
          * Starts with a lowercase letter AND contains at least one uppercase
            →  camelCase  (idContrato, numLicitacao, dtEmissao)
        SQL keywords are ALL_CAPS or purely lowercase (from user typing); they
        never start with a lowercase letter followed by an uppercase one.
        """
        if '_' in word:
            return True
        if word[0].islower() and any(c.isupper() for c in word[1:]):
            return True
        return False

    def _try_autocorrect_before_space(self):
        """Fuzzy-correct the word immediately before the cursor (before space/enter)."""
        word, start, end = self._word_before_cursor()
        if not word or len(word) < 3:
            return
        word_lower = word.lower()

        corrected_text = None

        # ── 1. Check SQL keywords / functions ─────────────────────────────────
        # Skip if the word looks like a camelCase/snake_case identifier — those
        # can never be SQL keywords and produce false positives (idContrato, etc.)
        if self._autocorrect_syntax_enabled and not self._looks_like_identifier(word):
            kw_map = {kw.lower(): kw for kw in SQL_KEYWORDS}
            kw_map.update({fn.lower(): fn for fn in SQL_FUNCTIONS})
            if word_lower not in kw_map:
                match = self._best_fuzzy_match(word_lower, kw_map.keys(), cutoff=0.72)
                if match:
                    corrected_text = kw_map[match]

        # ── 2. Check DB objects (only when in table-name position) ────────────
        if (corrected_text is None
                and self._autocorrect_objects_enabled
                and self._known_objects
                and self._in_table_context(start)):
            if word_lower not in self._known_objects:
                match = self._best_fuzzy_match(word_lower, self._known_objects, cutoff=0.65)
                if match:
                    corrected_text = self._schema_words_map.get(match, match)

        # ── Apply correction ──────────────────────────────────────────────────
        if corrected_text and corrected_text.lower() != word_lower:
            cursor = self.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.insertText(corrected_text)
            self.setTextCursor(cursor)

    # ── Linter ────────────────────────────────────────────────────────────────

    def _schedule_lint(self):
        if self._syntax_check_enabled or self._object_check_enabled:
            self._lint_timer.start()
        else:
            # Clear any existing lint marks
            self._clear_lint_marks()

    def _clear_lint_marks(self):
        # Remove only lint-related extra selections (keep current-line highlight)
        self.setExtraSelections([
            s for s in self.extraSelections()
            if s.format.property(QTextFormat.FullWidthSelection)
        ])

    def _run_lint(self):
        if not self._syntax_check_enabled and not self._object_check_enabled:
            self._clear_lint_marks()
            return

        text = self.toPlainText()
        errors: list = []

        if self._syntax_check_enabled:
            errors.extend(self._lint_syntax(text))

        if self._object_check_enabled and self._known_objects:
            errors.extend(self._lint_objects(text))

        # Preserve only the current-line highlight (FullWidthSelection), discard old lint
        current_line = [
            s for s in self.extraSelections()
            if s.format.property(QTextFormat.FullWidthSelection)
        ]
        self.setExtraSelections(current_line + errors)

    # ── Syntax linter ─────────────────────────────────────────────────────────

    def _lint_syntax(self, text: str) -> list:
        """Check for unbalanced parentheses and unclosed string literals."""
        errors = []
        dark = self._theme == "dark"
        warn_color = QColor("#cc8800" if dark else "#b86800")

        # Strip comments for syntax analysis
        clean = re.sub(r"--[^\n]*", "", text)          # remove line comments
        # Remove block comments (non-greedy)
        clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)

        # Check unclosed string literals (look in original text by position)
        for m in re.finditer(r"'(?:[^'\n]|'')*$", text, re.MULTILINE):
            errors.append(self._make_lint_selection(m.start(), m.end() - m.start(),
                                                    warn_color, "String n\u00e3o fechada"))

        # Check unbalanced parentheses
        depth = 0
        last_open_pos = -1
        for i, ch in enumerate(clean):
            if ch == "(":
                depth += 1
                last_open_pos = i
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    errors.append(self._make_lint_selection(i, 1, warn_color,
                                                             "Par\u00eantese fechado sem abrir"))
                    depth = 0
        if depth > 0 and last_open_pos >= 0:
            errors.append(self._make_lint_selection(last_open_pos, 1, warn_color,
                                                     "Par\u00eantese n\u00e3o fechado"))
        return errors

    # ── Object linter ─────────────────────────────────────────────────────────

    def _lint_objects(self, text: str) -> list:
        """Underline unknown identifiers that are not keywords/functions/objects."""
        if not self._known_objects:
            return []

        errors = []
        dark = self._theme == "dark"
        err_color = QColor("#f44747" if dark else "#c00000")

        all_known_lower = (
            {kw.lower() for kw in SQL_KEYWORDS}
            | {fn.lower() for fn in SQL_FUNCTIONS}
            | self._known_objects
        )

        # Build a version of text with strings and comments blanked out
        # so we don't flag words inside strings/comments
        blanked = self._blank_literals(text)

        # Find identifiers: [schema.]name patterns that follow FROM/JOIN/INTO/UPDATE/TABLE/EXEC keywords
        # This reduces false positives from aliases, column names, etc.
        context_pattern = re.compile(
            r"\b(FROM|JOIN|INTO|UPDATE|TABLE|EXEC(?:UTE)?|VIEW|PROCEDURE)\s+"
            r"(\[?[a-zA-Z_][a-zA-Z0-9_]*\]?(?:\.\[?[a-zA-Z_][a-zA-Z0-9_]*\]?)?)",
            re.IGNORECASE,
        )
        for m in context_pattern.finditer(blanked):
            obj_start = m.start(2)
            obj_raw   = m.group(2)
            # Strip square brackets for lookup
            obj_name  = re.sub(r"[\[\]]", "", obj_raw).lower()
            # Only flag the unqualified last part (after last dot)
            short = obj_name.split(".")[-1]
            if short and short not in all_known_lower:
                errors.append(self._make_lint_selection(
                    obj_start, len(obj_raw), err_color,
                    f"Objeto desconhecido: {obj_raw}"
                ))
        return errors

    @staticmethod
    def _blank_literals(text: str) -> str:
        """Replace string literals and comments with same-length spaces."""
        result = list(text)
        # Blank single-quoted strings
        for m in re.finditer(r"'(?:[^']|'')*'", text):
            for i in range(m.start() + 1, m.end() - 1):
                result[i] = " "
        # Blank line comments
        for m in re.finditer(r"--[^\n]*", text):
            for i in range(m.start(), m.end()):
                result[i] = " "
        # Blank block comments
        for m in re.finditer(r"/\*.*?\*/", text, re.DOTALL):
            for i in range(m.start(), m.end()):
                result[i] = " "
        return "".join(result)

    def _make_lint_selection(self, pos: int, length: int,
                             color: QColor, tooltip: str
                             ) -> QTextEdit.ExtraSelection:
        sel = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        fmt.setUnderlineColor(color)
        fmt.setToolTip(tooltip)
        sel.format = fmt
        cursor = self.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.KeepAnchor)
        sel.cursor = cursor
        return sel
