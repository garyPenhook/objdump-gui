"""A dialog showing a unified diff of two binaries' (aligned) disassembly."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)


class _DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self._rules = []
        for pattern, color in (
            (r"^\+.*$", "#0dbc79"),     # added
            (r"^-.*$", "#f14c4c"),      # removed
            (r"^@@.*$", "#11a8cd"),     # hunk header
        ):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self._rules.append((QRegularExpression(pattern), fmt))

    def highlightBlock(self, text):
        for regex, fmt in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class DiffDialog(QDialog):
    def __init__(self, title: str, diff_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 700)
        self._diff_text = diff_text

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont("monospace")
        font.setStyleHint(QFont.Monospace)
        self.view.setFont(font)
        self.view.setPlainText(diff_text or "(no differences)")
        self._hl = _DiffHighlighter(self.view.document())
        layout.addWidget(self.view)

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton("Save Diff…", QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Close)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _save(self):
        if not self._diff_text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save diff", "", "Diff files (*.diff *.patch);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._diff_text)
        except OSError as exc:
            QMessageBox.warning(self, "Save diff", f"Could not write:\n{exc}")


class TextViewerDialog(QDialog):
    """A simple read-only monospaced viewer (used for section hex dumps)."""

    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont("monospace")
        font.setStyleHint(QFont.Monospace)
        view.setFont(font)
        view.setPlainText(text or "(empty)")
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
