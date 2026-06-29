"""Tests for the tolerant section/symbol parsers and ANSI stripping."""

from objdump_gui.parsers import parse_sections, parse_symbols, strip_ansi
from tests import fixtures as fx


def test_parse_sections_basic():
    secs = {s.name: s for s in parse_sections(fx.SECTIONS_TEXT)}
    assert ".data" in secs and ".bss" in secs
    assert secs[".data"].size == "00000010"
    assert "ALLOC" in secs[".data"].flags and "DATA" in secs[".data"].flags


def test_parse_sections_single_flag_no_comma():
    # Regression: ".bss" has a flag line of just "ALLOC" (no comma).
    secs = {s.name: s for s in parse_sections(fx.SECTIONS_TEXT)}
    assert secs[".bss"].flags == "ALLOC"


def test_parse_symbols_basic():
    syms = parse_symbols(fx.SYMBOLS_TEXT)
    by_name = {s.name: s for s in syms}
    assert "add" in by_name
    add = by_name["add"]
    assert add.address == "00000000"
    assert add.section == ".text"
    assert add.size == "0000000e"
    assert "F" in add.flags


def test_parse_symbols_ignores_header():
    syms = parse_symbols(fx.SYMBOLS_TEXT)
    assert all(s.name != "SYMBOL TABLE:" for s in syms)


def test_strip_ansi():
    colored = "\x1b[31mmov\x1b[0m \x1b[32m%eax\x1b[0m"
    assert strip_ansi(colored) == "mov %eax"
    assert strip_ansi("plain") == "plain"
