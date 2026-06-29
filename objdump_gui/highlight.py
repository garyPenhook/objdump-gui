"""Syntax highlighting for objdump's disassembly / dump output.

A single regex-rule highlighter colours addresses, raw bytes, mnemonics,
registers, immediates, comments, section banners and symbol labels. It is theme
aware: :func:`make_palette` returns colours tuned for dark or light backgrounds.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFontItalic(True)
    return f


DARK = {
    "address": "#6a9955",
    "bytes": "#808080",
    "mnemonic": "#569cd6",
    "register": "#9cdcfe",
    "immediate": "#b5cea8",
    "comment": "#6a9955",
    "label": "#dcdcaa",
    "section": "#c586c0",
    "string": "#ce9178",
}

LIGHT = {
    "address": "#098658",
    "bytes": "#888888",
    "mnemonic": "#0000ff",
    "register": "#0070c1",
    "immediate": "#098658",
    "comment": "#008000",
    "label": "#795e26",
    "section": "#af00db",
    "string": "#a31515",
}


def make_palette(dark: bool) -> dict:
    return DARK if dark else LIGHT


# Per-architecture register sets. The active one is chosen from the loaded
# objdump's reported architecture so each toolchain's disassembly colours its
# own registers (x86 %rax…, AVR r0–r31 / X/Y/Z, ARM r0…/x0…/sp/lr/pc).
_REGISTERS = {
    # x86: GP/extended/segment/vector registers.
    "x86": (
        r"%?\b(?:r[abcd]x|r[sd]i|r[bs]p|r(?:8|9|1[0-5])[dwb]?|e?[abcd]x|"
        r"e?[sd]i|e?[bs]p|[abcd][hl]|[cdesfg]s|[xyz]mm\d+|mm\d+|st\d?|"
        r"rip|eip|eflags|cr\d|dr\d)\b"
    ),
    # AVR: r0–r31 and the X/Y/Z pointer registers (as printed, e.g. X+, -Y).
    "avr": r"(?<![\w.])(?:r\d{1,2}|[XYZ])(?![\w])",
    # ARM / AArch64: GP, special, and SIMD/FP registers.
    "arm": (
        r"\b(?:r\d{1,2}|[wx]\d{1,2}|sp|lr|pc|fp|ip|sl|sb|"
        r"wzr|xzr|wsp|[sdqvh]\d{1,2})\b"
    ),
    # RISC-V: numeric (x0-x31, f0-f31) and the ABI names that GNU/LLVM print by
    # default. The ABI families here were grounded in real disassembly tokens
    # (a0-a7, ra, sp, fp, s0-s11, fa0-fa7, ...), not from memory.
    "riscv": (
        r"\b(?:x\d{1,2}|f\d{1,2}|zero|ra|sp|gp|tp|fp|t[0-6]|"
        r"s(?:1[01]|[0-9])|a[0-7]|ft(?:1[01]|[0-9])|fs(?:1[01]|[0-9])|"
        r"fa[0-7])\b"
    ),
}


class AsmHighlighter(QSyntaxHighlighter):
    def __init__(self, document, dark: bool = True, arch: str = "x86"):
        super().__init__(document)
        self._arch = arch
        self.set_theme(dark)

    def set_arch(self, arch: str) -> None:
        if arch != self._arch:
            self._arch = arch
            self.set_theme(self._dark)

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        c = make_palette(dark)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat, int]] = []
        R = QRegularExpression

        def add(pattern, fmt, group=0):
            self._rules.append((R(pattern), fmt, group))

        # Section banner: "Disassembly of section .text:"
        add(r"^Disassembly of section .*:$", _fmt(c["section"], bold=True))
        # Symbol label lines: "0000000000001050 <_start>:"
        add(r"<[^>]+>", _fmt(c["label"], bold=True))
        # Aligned-view function labels: a bare "name:" on its own line.
        add(r"^[A-Za-z_.$][\w.$@]*:$", _fmt(c["label"], bold=True))
        # Leading address (start of line, before bytes/label).
        add(r"^\s*[0-9a-fA-F]{4,16}(?=:|\s)", _fmt(c["address"]))
        # Raw instruction bytes block after "addr:\t".
        add(r"(?<=:)\t(?:[0-9a-fA-F]{2} )+", _fmt(c["bytes"]))
        # Registers (architecture-specific; omitted for unknown targets).
        reg_pattern = _REGISTERS.get(self._arch)
        if reg_pattern:
            add(reg_pattern, _fmt(c["register"]))
        # Immediates / hex literals.
        add(r"\$?0x[0-9a-fA-F]+", _fmt(c["immediate"]))
        # Comments and strings must come LAST: setFormat lets later rules repaint
        # earlier ranges, so this guarantees register/immediate tokens that appear
        # inside a comment (objdump appends "# 0x... <sym>") stay comment-colored.
        # Comments use both # and ; depending on architecture.
        add(r"[#;].*$", _fmt(c["comment"], italic=True))
        # Quoted strings (in -s / string dumps).
        add(r'"[^"]*"', _fmt(c["string"]))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for regex, fmt, group in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                start = m.capturedStart(group)
                length = m.capturedLength(group)
                if length > 0:
                    self.setFormat(start, length, fmt)
