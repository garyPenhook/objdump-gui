"""Tests for the aligned disassembly formatter across architectures."""

import pytest

from objdump_gui.prettyprint import format_disassembly, _BYTES_RE
from tests import fixtures as fx


@pytest.mark.parametrize("text", [
    fx.X86_DISASM, fx.AVR_DISASM, fx.ARM_THUMB_DISASM,
    fx.AARCH64_DISASM, fx.RISCV_DISASM,
])
def test_no_tabs_in_aligned_output(text):
    assert "\t" not in format_disassembly(text)
    assert "\t" not in format_disassembly(text, show_bytes=True)


def test_x86_alignment_and_labels():
    out = format_disassembly(fx.X86_DISASM)
    assert "main:" in out
    assert "push %rbp" in out
    # operands comma-spaced
    assert "mov  %rsp, %rbp" in out
    # raw bytes hidden by default
    assert "48 89 e5" not in out


def test_avr_tab_separated_operands_and_comment():
    out = format_disassembly(fx.AVR_DISASM)
    assert "add:" in out
    assert "add  r24, r22" in out
    # comment field (separate tab in source) survives, joined inline
    assert "; 255" in out
    # the all-hex mnemonic 'add'/'adc' was NOT mistaken for a byte column
    assert "add  r24, r22" in out and "adc  r25, r23" in out


@pytest.mark.parametrize("text,word,mnem", [
    (fx.ARM_THUMB_DISASM, "4408", "add"),
    (fx.AARCH64_DISASM, "0b010000", "add"),
    (fx.RISCV_DISASM, "9d2d", "addw"),
])
def test_contiguous_opcode_word_not_leaked_into_mnemonic(text, word, mnem):
    out = format_disassembly(text)
    # the byte word must be gone when bytes are hidden...
    assert word not in out
    # ...and the real mnemonic present
    assert mnem in out
    # ...and reappear in the byte column when requested
    assert word in format_disassembly(text, show_bytes=True)


def test_show_bytes_column_alignment():
    out = format_disassembly(fx.X86_DISASM, show_bytes=True)
    assert "48 89 e5" in out
    # mnemonic still present after the byte column
    assert "mov" in out


def test_non_disassembly_passthrough():
    junk = "random header line\n\tindented source code();\nplain text"
    assert format_disassembly(junk) == junk


def test_blank_line_between_functions():
    out = format_disassembly(fx.X86_DISASM + "\n\n" + fx.AVR_DISASM)
    # both function labels rendered
    assert "main:" in out and "add:" in out


@pytest.mark.parametrize("good", ["55", "48 89 e5", "4408", "0b010000", "9d2d",
                                  "80 91 00 00"])
def test_bytes_regex_accepts_real_byte_fields(good):
    assert _BYTES_RE.fullmatch(good)


@pytest.mark.parametrize("bad", ["add", "adc", "dec", "ret", "r24"])
def test_bytes_regex_rejects_mnemonics(bad):
    assert not _BYTES_RE.fullmatch(bad)
