"""Widget-level tests that require a QApplication (run headless / offscreen)."""

import pytest

from objdump_gui.widgets.options_panel import OptionsPanel
from objdump_gui.widgets.output_view import OutputView
from tests import fixtures as fx


def test_options_panel_build_argv(qapp, x86_caps):
    panel = OptionsPanel(x86_caps)
    # default: -d and -h are on
    argv = panel.build_argv()
    assert "-d" in argv and "-h" in argv
    # set the architecture choice and confirm space-separated token
    for row in panel.rows:
        if row.spec.key == "m":
            row.setter("i386")
    argv = panel.build_argv()
    assert argv[argv.index("-m") + 1] == "i386"


def test_options_panel_reset(qapp, x86_caps):
    panel = OptionsPanel(x86_caps)
    for row in panel.rows:
        if row.spec.key == "x":
            row.setter(True)
    assert "-x" in panel.build_argv()
    panel.reset()
    assert "-x" not in panel.build_argv()


def test_output_view_find_counts(qapp):
    ov = OutputView(dark=True, arch="x86")
    ov.set_text(fx.X86_DISASM)
    ov.show_find()
    ov.find_input.setText("mov")
    assert "match" in ov.count_label.text()


@pytest.mark.parametrize("pat", [r"\b", "a*", "x?", ".*", "(?=m)"])
def test_output_view_zero_width_regex_bounded(qapp, pat):
    ov = OutputView(dark=True, arch="x86")
    ov.set_text("abc\n" * 50)
    ov.show_find()
    ov.regex_cb.setChecked(True)
    ov.find_input.setText(pat)
    # must not hang or explode; count label is set (bounded)
    assert "match" in ov.count_label.text()


def test_output_view_goto_text(qapp):
    ov = OutputView(dark=True, arch="x86")
    ov.set_text(fx.X86_DISASM)
    assert ov.goto_text("<helper>")
    assert not ov.goto_text("nonexistent_symbol_xyz")


def test_output_view_arch_switch(qapp):
    ov = OutputView(dark=True, arch="x86")
    ov.set_arch("avr")
    assert ov.highlighter._arch == "avr"


def _drain_threadpool(qapp):
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()


def test_symbols_navigator_load_filter_sort(qapp):
    from objdump_gui.widgets.navigators import SymbolsNavigator
    nav = SymbolsNavigator()
    nav.load(fx.SYMBOLS_TEXT)
    _drain_threadpool(qapp)
    assert nav.count() == 3
    # substring filter on the Name column
    nav.filter.setText("add")
    qapp.processEvents()
    assert nav.proxy.rowCount() == 1
    nav.filter.setText("")
    qapp.processEvents()
    # numeric sort by Address column does not raise
    nav.proxy.sort(0)
    assert nav.proxy.rowCount() == 3


def test_sections_navigator_load(qapp):
    from objdump_gui.widgets.navigators import SectionsNavigator
    nav = SectionsNavigator()
    nav.load(fx.SECTIONS_TEXT)
    _drain_threadpool(qapp)
    assert nav.count() == 2


def test_symbols_navigator_stale_load_discarded(qapp):
    from objdump_gui.widgets.navigators import SymbolsNavigator
    nav = SymbolsNavigator()
    nav.load(fx.SYMBOLS_TEXT)
    nav.load("SYMBOL TABLE:\n")   # newer load with no symbols supersedes
    _drain_threadpool(qapp)
    assert nav.count() == 0


def test_options_panel_state_roundtrip(qapp, x86_caps):
    p = OptionsPanel(x86_caps)
    for row in p.rows:
        if row.spec.key == "x":
            row.setter(True)
        if row.spec.key == "insn_width":
            row.setter("7")
        if row.spec.key == "m":
            row.setter("i386")
    state = p.get_state()
    p.reset()
    assert "-x" not in p.build_argv()
    p.set_state(state)
    argv = p.build_argv()
    assert "-x" in argv and "--insn-width=7" in argv
    assert argv[argv.index("-m") + 1] == "i386"


def test_output_view_goto_address(qapp):
    ov = OutputView(dark=True, arch="x86")
    ov.set_text(fx.X86_DISASM)
    assert ov.goto_address("0x401115")
    assert ov.goto_address("401124")
    assert not ov.goto_address("0xdeadbeef")
    assert not ov.goto_address("nothex")


def test_output_view_invalid_regex_feedback(qapp):
    ov = OutputView(dark=True, arch="x86")
    ov.set_text("abc\nabc")
    ov.show_find()
    ov.regex_cb.setChecked(True)
    ov.find_input.setText("(")          # unbalanced -> invalid
    assert ov.count_label.text() == "invalid regex"
    ov.find_input.setText("a")          # valid again
    assert "match" in ov.count_label.text()


def test_output_view_follow_symbol(qapp):
    ov = OutputView(dark=True, arch="x86")
    got = []
    ov.navigate_symbol.connect(got.append)
    ov.set_text(fx.X86_DISASM)
    assert ov.editor.find("<helper>")   # places cursor on the token
    ov.follow_under_cursor()
    assert got == ["helper"]
