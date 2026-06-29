"""Tolerant parsers for the structured navigator panes.

These turn the textual output of dedicated ``objdump -h`` / ``objdump -t`` runs
into row tuples for the Sections and Symbols tables. They are deliberately
forgiving: anything that doesn't match is skipped rather than raising.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Section:
    idx: str
    name: str
    size: str
    vma: str
    lma: str
    file_off: str
    algn: str
    flags: str = ""


@dataclass
class Symbol:
    address: str
    flags: str
    section: str
    size: str
    name: str


_SEC_RE = re.compile(
    r"^\s*(\d+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+"
    r"([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+(\S+)"
)

# objdump -t: "<addr> <7-char flags> <section>\t<size> <name>"
_SYM_RE = re.compile(
    r"^([0-9a-fA-F]+)\s(.{7})\s(\S+)\t([0-9a-fA-F]+)\s+(.*)$"
)


def parse_sections(text: str) -> list[Section]:
    out: list[Section] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _SEC_RE.match(line)
        if not m:
            continue
        flags = ""
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            # The flag line is one or more UPPER-CASE tokens (comma-separated).
            # Single-flag sections such as ".bss ALLOC" have no comma, so the
            # match must not require one.
            if nxt and re.fullmatch(r"[A-Z0-9_]+(?:,\s*[A-Z0-9_]+)*", nxt):
                flags = nxt
        idx, name, size, vma, lma, file_off, algn = m.groups()
        out.append(Section(idx, name, size, vma, lma, file_off, algn, flags))
    return out


def parse_symbols(text: str) -> list[Symbol]:
    out: list[Symbol] = []
    for line in text.splitlines():
        m = _SYM_RE.match(line)
        if not m:
            continue
        addr, flags, section, size, name = m.groups()
        out.append(Symbol(addr, flags.strip(), section, size, name.strip()))
    return out


# ANSI escape sequences (from --disassembler-color) would render as garbage in a
# Qt text widget, so we strip them everywhere before display.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)
