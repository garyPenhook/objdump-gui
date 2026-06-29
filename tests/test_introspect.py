"""Tests for objdump capability parsing and architecture classification."""

from objdump_gui.introspect import Capabilities, arch_family, _parse_disasm_options
from tests import fixtures as fx


def _caps(arches):
    return Capabilities(path="x", architectures=arches)


def test_arch_family():
    assert arch_family(_caps(["avr", "avr:5"])) == "avr"
    assert arch_family(_caps(["riscv:rv64", "riscv:rv32"])) == "riscv"
    assert arch_family(_caps(["aarch64", "armv7"])) == "arm"
    assert arch_family(_caps(["arm"])) == "arm"
    assert arch_family(_caps(["i386", "i386:x86-64"])) == "x86"
    assert arch_family(_caps(["mystery"])) == "generic"
    assert arch_family(_caps([])) == "generic"


def test_parse_disasm_options_excludes_wrapped_descriptions():
    opts = _parse_disasm_options(fx.HELP_DISASM_OPTIONS)
    assert opts == ["x86-64", "att", "att-mnemonic", "intel"]
    # the wrapped continuation line must not leak in
    assert "Display" not in opts
    assert "with" not in opts


def test_parse_disasm_options_empty_when_absent():
    assert _parse_disasm_options("no options block here") == []
