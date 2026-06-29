"""Tests for the architecture-specific register highlight patterns."""

from PySide6.QtCore import QRegularExpression

from objdump_gui.highlight import _REGISTERS


def _matches(arch, text):
    rx = QRegularExpression(_REGISTERS[arch])
    it = rx.globalMatch(text)
    out = []
    while it.hasNext():
        out.append(it.next().captured(0))
    return out


def test_all_patterns_compile():
    for arch, pat in _REGISTERS.items():
        assert QRegularExpression(pat).isValid(), arch


def test_x86_registers():
    assert _matches("x86", "mov %rsp,%rbp") == ["%rsp", "%rbp"]


def test_avr_registers():
    assert _matches("avr", "add r24, r22") == ["r24", "r22"]
    assert _matches("avr", "st X+, r0") == ["X", "r0"]
    assert _matches("avr", "ld r24, -Y") == ["r24", "Y"]
    # mnemonics and immediates must not match
    assert _matches("avr", "ldi 0xFF") == []


def test_arm_registers():
    assert _matches("arm", "add r0, r1") == ["r0", "r1"]
    assert set(_matches("arm", "str wzr, [sp, #12]")) == {"wzr", "sp"}
    assert _matches("arm", "bx lr") == ["lr"]
    assert set(_matches("arm", "mov x0, sp")) == {"x0", "sp"}


def test_riscv_registers():
    assert set(_matches("riscv", "sd ra, 0x18(sp)")) == {"ra", "sp"}
    assert set(_matches("riscv", "mul a0, a1, a0")) == {"a0", "a1"}
    assert set(_matches("riscv", "fmadd.d fa0, fa1, fa5")) == {"fa0", "fa1", "fa5"}
    assert set(_matches("riscv", "sd s11, 0(s0)")) == {"s11", "s0"}
