"""Minimal ANSI SGR parser for rendering objdump's --disassembler-color output.

objdump emits standard SGR foreground codes (31-37 / 90-97) plus bold (1) and
reset (0). :func:`parse_ansi` splits text into ``(segment, QTextCharFormat|None)``
runs so the output view can render real colors instead of stripping them.
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QTextCharFormat

_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

# A readable 16-colour palette (works on dark or light backgrounds).
_FG = {
    30: "#555555", 31: "#cd3131", 32: "#0dbc79", 33: "#b58900",
    34: "#2472c8", 35: "#bc3fbc", 36: "#11a8cd", 37: "#999999",
    90: "#666666", 91: "#f14c4c", 92: "#23d18b", 93: "#d7a500",
    94: "#3b8eea", 95: "#d670d6", 96: "#29b8db", 97: "#cccccc",
}


def has_ansi(text: str) -> bool:
    return "\x1b[" in text


def parse_ansi(text: str):
    """Return a list of (segment_text, QTextCharFormat | None) runs."""
    runs = []
    fg = None
    bold = False

    def fmt():
        if fg is None and not bold:
            return None
        f = QTextCharFormat()
        if fg is not None:
            f.setForeground(QColor(fg))
        if bold:
            f.setFontWeight(QFont.Bold)
        return f

    last = 0
    for m in _SGR_RE.finditer(text):
        if m.start() > last:
            runs.append((text[last:m.start()], fmt()))
        codes = m.group(1)
        for tok in (codes.split(";") if codes else ["0"]):
            try:
                n = int(tok or "0")
            except ValueError:
                continue
            if n == 0:
                fg, bold = None, False
            elif n == 1:
                bold = True
            elif n == 22:
                bold = False
            elif n == 39:
                fg = None
            elif n in _FG:
                fg = _FG[n]
        last = m.end()
    if last < len(text):
        runs.append((text[last:], fmt()))
    return runs
