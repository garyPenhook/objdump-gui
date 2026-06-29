"""The central output pane: a monospaced, syntax-highlighted viewer with an
integrated incremental find bar (plain / case-sensitive / regex, with match
count and next/prev navigation)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from ..highlight import AsmHighlighter


class OutputView(QWidget):
    def __init__(self, dark: bool = True, arch: str = "x86", parent=None):
        super().__init__(parent)
        self._dark = dark

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setUndoRedoEnabled(False)
        font = QFont("monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.editor.setFont(font)

        self.highlighter = AsmHighlighter(self.editor.document(), dark=dark,
                                          arch=arch)

        self.find_bar = self._build_find_bar()
        self.find_bar.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.find_bar)
        layout.addWidget(self.editor)

    # -- find bar -----------------------------------------------------------

    def _build_find_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(4, 2, 4, 2)

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find… (Enter = next, Shift+Enter = prev)")
        self.find_input.textChanged.connect(self._on_find_changed)
        self.find_input.returnPressed.connect(self.find_next)

        self.case_cb = QCheckBox("Aa")
        self.case_cb.setToolTip("Case sensitive")
        self.case_cb.toggled.connect(self._on_find_changed)
        self.regex_cb = QCheckBox(".*")
        self.regex_cb.setToolTip("Regular expression")
        self.regex_cb.toggled.connect(self._on_find_changed)

        self.count_label = QLabel("")
        self.count_label.setMinimumWidth(70)

        prev_btn = QToolButton()
        prev_btn.setText("▲")
        prev_btn.setToolTip("Previous match")
        prev_btn.clicked.connect(self.find_prev)
        next_btn = QToolButton()
        next_btn.setText("▼")
        next_btn.setToolTip("Next match")
        next_btn.clicked.connect(self.find_next)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.clicked.connect(self.hide_find)

        for w in (QLabel("Find:"), self.find_input, self.case_cb, self.regex_cb,
                  prev_btn, next_btn, self.count_label, close_btn):
            h.addWidget(w)
        h.setStretch(1, 1)
        return bar

    def show_find(self) -> None:
        self.find_bar.setVisible(True)
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.find_input.setText(cursor.selectedText())
        self.find_input.setFocus()
        self.find_input.selectAll()
        self._on_find_changed()

    def hide_find(self) -> None:
        self.find_bar.setVisible(False)
        self._clear_extra_selections()
        self.editor.setFocus()

    def _flags(self) -> QTextDocument.FindFlags:
        flags = QTextDocument.FindFlags()
        if self.case_cb.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def _pattern(self):
        text = self.find_input.text()
        if not text:
            return None
        if self.regex_cb.isChecked():
            opts = QRegularExpression.NoPatternOption
            if not self.case_cb.isChecked():
                opts |= QRegularExpression.CaseInsensitiveOption
            return QRegularExpression(text, opts)
        return text

    def _on_find_changed(self) -> None:
        self._highlight_all_matches()

    def find_next(self) -> None:
        self._find(False)

    def find_prev(self) -> None:
        self._find(True)

    def _find(self, backward: bool) -> None:
        pat = self._pattern()
        if pat is None:
            return
        flags = self._flags()
        if backward:
            flags |= QTextDocument.FindBackward
        found = self.editor.find(pat, flags) if not isinstance(pat, str) \
            else self.editor.find(pat, flags)
        if not found:
            # Wrap around.
            cursor = self.editor.textCursor()
            cursor.movePosition(
                QTextCursor.End if backward else QTextCursor.Start
            )
            self.editor.setTextCursor(cursor)
            self.editor.find(pat, flags)

    def goto_text(self, needle: str) -> bool:
        """Jump to the first occurrence of a literal string (used by navigators)."""
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cursor)
        found = self.editor.find(needle)
        if found:
            self.editor.centerCursor()
        return found

    def _clear_extra_selections(self) -> None:
        self.editor.setExtraSelections([])
        self.count_label.setText("")

    def _highlight_all_matches(self) -> None:
        pat = self._pattern()
        if pat is None:
            self._clear_extra_selections()
            return
        doc = self.editor.document()
        hl = QColor("#665500") if self._dark else QColor("#ffe680")
        fmt = QTextCharFormat()
        fmt.setBackground(hl)
        selections = []
        cursor = QTextCursor(doc)
        count = 0
        flags = self._flags()
        while True:
            cursor = doc.find(pat, cursor, flags)
            if cursor.isNull():
                break
            if cursor.selectionStart() == cursor.selectionEnd():
                # Zero-width match (e.g. \b, ^, a*): the next search would start
                # at the same position and never advance, so step past it and do
                # not count/highlight an empty hit.
                pos = cursor.selectionEnd() + 1
                # Valid positions are 0..characterCount-1; pos == characterCount
                # is past the end. Using '>' here let setPosition() clamp back to
                # the last position, re-match the same zero-width hit and loop
                # forever (e.g. pattern "a*" matching empty at EOF).
                if pos >= doc.characterCount():
                    break
                cursor.setPosition(pos)
                continue
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            selections.append(sel)
            count += 1
            if count > 50000:  # guard pathological patterns
                break
        self.editor.setExtraSelections(selections)
        self.count_label.setText(f"{count} match{'es' if count != 1 else ''}")

    # -- content ------------------------------------------------------------

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)
        if self.find_bar.isVisible():
            self._highlight_all_matches()

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        self.highlighter.set_theme(dark)
        if self.find_bar.isVisible():
            self._highlight_all_matches()

    def set_arch(self, arch: str) -> None:
        self.highlighter.set_arch(arch)
