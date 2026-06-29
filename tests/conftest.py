"""Shared pytest fixtures. Tests are hermetic: they run against captured objdump
output fixtures and synthetic Capabilities, so no binutils toolchain is required."""

import os

# Qt must run headless under CI / test runners.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from objdump_gui.introspect import Capabilities


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def x86_caps():
    return Capabilities(
        path="objdump",
        version="GNU objdump (GNU Binutils) 2.46",
        targets=["elf64-x86-64", "elf32-i386"],
        architectures=["i386", "i386:x86-64", "i8086"],
        disasm_options=["intel", "att", "x86-64"],
        demangle_styles=["auto", "gnu-v3", "rust"],
    )
