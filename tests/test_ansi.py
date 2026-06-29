"""Tests for the ANSI SGR parser used to render --disassembler-color output."""

from objdump_gui.ansi import has_ansi, parse_ansi


def test_has_ansi():
    assert has_ansi("\x1b[33mpush\x1b[0m")
    assert not has_ansi("push %rbp")


def test_parse_ansi_splits_runs_and_preserves_text():
    text = "  401115:\t55\t\x1b[33mpush   \x1b[0m\x1b[34m%rbp\x1b[0m"
    runs = parse_ansi(text)
    # reassembled text equals the input minus the escape codes
    joined = "".join(seg for seg, _ in runs)
    assert "\x1b" not in joined
    assert joined == "  401115:\t55\tpush   %rbp"
    # the colored segments carry a format, the leading plain part does not
    fmts = {seg.strip(): fmt for seg, fmt in runs if seg.strip()}
    assert fmts["push"] is not None
    assert fmts["%rbp"] is not None


def test_parse_ansi_plain_text_single_run_no_format():
    runs = parse_ansi("no colors here")
    assert runs == [("no colors here", None)]


def test_parse_ansi_handles_bold_and_reset():
    runs = parse_ansi("\x1b[1mBOLD\x1b[0mplain")
    segs = {seg: fmt for seg, fmt in runs}
    assert segs["BOLD"] is not None
    assert segs["plain"] is None
