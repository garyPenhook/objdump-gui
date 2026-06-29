"""Main application window: menus, toolbar, dockable navigators/options, the
central syntax-highlighted output, a live command preview and the run/cancel
lifecycle around :class:`ObjdumpRunner`."""

from __future__ import annotations

import difflib
import json
import os
import shlex
import subprocess

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import introspect
from .ansi import has_ansi
from .parsers import strip_ansi
from .prettyprint import format_disassembly
from .runner import ObjdumpRunner, run_capture
from .widgets.navigators import SectionsNavigator, SymbolsNavigator
from .widgets.options_panel import OptionsPanel
from .widgets.output_view import OutputView

ORG = "objdump-gui"
APP = "objdump-gui"
MAX_RECENT = 10


class MainWindow(QMainWindow):
    def __init__(self, caps):
        super().__init__()
        self.caps = caps
        self.settings = QSettings(ORG, APP)
        self.current_file: str | None = None
        self._dark = self.settings.value("dark", True, type=bool)
        self._raw_output = ""   # last run's raw text, kept so the aligned/raw
                                # toggle re-renders without re-running objdump
        self._toolchains = introspect.discover_objdumps()

        self.runner = ObjdumpRunner(caps.path, self)
        self.runner.started.connect(self._on_run_started)
        self.runner.finished.connect(self._on_run_finished)

        self.setWindowTitle("objdump GUI")
        self.resize(1500, 950)

        self.output = OutputView(dark=self._dark,
                                 arch=introspect.arch_family(caps))
        self.setCentralWidget(self._wrap_central())

        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()

        self.options.changed.connect(self._update_preview)
        self.output.navigate_symbol.connect(self._jump_to_symbol)
        self._connect_navigators()
        self._apply_theme()
        self._update_preview()
        self._refresh_recent_menu()
        self._set_busy(False)
        self.act_pretty_bytes.setEnabled(self.act_aligned.isChecked())
        self.act_pretty_spacing.setEnabled(self.act_aligned.isChecked())
        self._restore_layout()
        self._restore_last_options()

    # -- central layout (output + command preview) --------------------------

    def _wrap_central(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(self.output, 1)

        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(4, 2, 4, 2)
        h.addWidget(QLabel("Command:"))
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet("font-family: monospace;")
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_command)
        h.addWidget(self.preview, 1)
        h.addWidget(copy_btn)
        v.addWidget(bar)
        return w

    # -- docks --------------------------------------------------------------

    def _build_docks(self) -> None:
        self.options = OptionsPanel(self.caps)
        self.options_dock = QDockWidget("Options", self)
        self.options_dock.setObjectName("dock_options")
        self.options_dock.setWidget(self.options)
        self.addDockWidget(Qt.RightDockWidgetArea, self.options_dock)

        self.sections_nav = SectionsNavigator()
        self.sections_dock = QDockWidget("Sections", self)
        self.sections_dock.setObjectName("dock_sections")
        self.sections_dock.setWidget(self.sections_nav)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sections_dock)

        self.symbols_nav = SymbolsNavigator()
        self.symbols_dock = QDockWidget("Symbols", self)
        self.symbols_dock.setObjectName("dock_symbols")
        self.symbols_dock.setWidget(self.symbols_nav)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.symbols_dock)

        self.dis_opts_dock = QDockWidget("Disassembler Options (-M)", self)
        self.dis_opts_dock.setObjectName("dock_disopts")
        self.dis_opts_dock.setWidget(self._build_disasm_opts())
        self.addDockWidget(Qt.RightDockWidgetArea, self.dis_opts_dock)
        self.tabifyDockWidget(self.options_dock, self.dis_opts_dock)
        self.options_dock.raise_()

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setStyleSheet("font-family: monospace;")
        self.log_dock = QDockWidget("Messages / stderr", self)
        self.log_dock.setObjectName("dock_log")
        self.log_dock.setWidget(self.log)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)

    def _build_disasm_opts(self) -> QWidget:
        """Checkable list of the probed architecture-specific -M options."""
        scroll = QScrollArea()
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.addWidget(QLabel("Toggle to append to the -M field:"))
        self._disasm_checks: list[QCheckBox] = []
        opts = self.caps.disasm_options or ["(none reported by this objdump)"]
        for opt in opts:
            cb = QCheckBox(opt)
            if not self.caps.disasm_options:
                cb.setEnabled(False)
            else:
                cb.toggled.connect(self._sync_disasm_opts)
            self._disasm_checks.append(cb)
            v.addWidget(cb)
        v.addStretch(1)
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        return scroll

    def _sync_disasm_opts(self) -> None:
        chosen = [c.text() for c in self._disasm_checks if c.isChecked()]
        for row in self.options.rows:
            if row.spec.key == "M":
                row.setter(",".join(chosen))
                break

    # -- actions / menus / toolbar -----------------------------------------

    def _build_actions(self) -> None:
        self.act_open = QAction("&Open…", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_file)

        self.act_reload = QAction("&Reload", self)
        self.act_reload.setShortcut("F5")
        self.act_reload.triggered.connect(self._reload)

        self.act_run = QAction("&Run objdump", self)
        self.act_run.setShortcut("Ctrl+R")
        self.act_run.triggered.connect(self.run)

        self.act_cancel = QAction("&Cancel", self)
        self.act_cancel.setShortcut("Esc")
        self.act_cancel.triggered.connect(self.runner.cancel)

        self.act_save = QAction("&Save Output…", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self._save_output)

        self.act_copy_cmd = QAction("&Copy Command", self)
        self.act_copy_cmd.triggered.connect(self._copy_command)

        self.act_find = QAction("&Find", self)
        self.act_find.setShortcut(QKeySequence.Find)
        self.act_find.triggered.connect(self.output.show_find)

        self.act_goto = QAction("&Go to Address…", self)
        self.act_goto.setShortcut("Ctrl+G")
        self.act_goto.triggered.connect(self._goto_address)

        self.act_follow = QAction("Follow Symbol Under Cursor", self)
        self.act_follow.setShortcut("Ctrl+]")
        self.act_follow.triggered.connect(self.output.follow_under_cursor)

        self.act_reset = QAction("Reset Options", self)
        self.act_reset.triggered.connect(self.options.reset)

        self.act_quit = QAction("&Quit", self)
        self.act_quit.setShortcut(QKeySequence.Quit)
        self.act_quit.triggered.connect(self.close)

        self.act_dark = QAction("&Dark Theme", self, checkable=True)
        self.act_dark.setChecked(self._dark)
        self.act_dark.toggled.connect(self._toggle_theme)

        self.act_aligned = QAction("&Aligned Disassembly", self, checkable=True)
        self.act_aligned.setShortcut("Ctrl+Shift+A")
        self.act_aligned.setToolTip(
            "Reformat disassembly into aligned columns (display only)"
        )
        self.act_aligned.setChecked(
            self.settings.value("aligned", True, type=bool)
        )
        self.act_aligned.toggled.connect(self._on_format_changed)

        self.act_pretty_bytes = QAction("Show Raw Bytes (aligned)", self,
                                        checkable=True)
        self.act_pretty_bytes.setChecked(
            self.settings.value("aligned_bytes", False, type=bool)
        )
        self.act_pretty_bytes.toggled.connect(self._on_format_changed)

        self.act_pretty_spacing = QAction("Space Operands (aligned)", self,
                                          checkable=True)
        self.act_pretty_spacing.setChecked(
            self.settings.value("aligned_spacing", True, type=bool)
        )
        self.act_pretty_spacing.toggled.connect(self._on_format_changed)

        self.act_about = QAction("&About", self)
        self.act_about.triggered.connect(self._about)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        m_file.addAction(self.act_open)
        self.recent_menu = m_file.addMenu("Open &Recent")
        m_file.addAction(self.act_reload)
        m_file.addSeparator()
        m_file.addAction(self.act_save)
        m_export = m_file.addMenu("&Export")
        m_export.addAction("Raw output…").triggered.connect(self._export_raw)
        m_export.addAction("Aligned output…").triggered.connect(
            self._export_aligned)
        m_export.addAction("Highlighted HTML…").triggered.connect(
            self._export_html)
        m_file.addSeparator()
        self.toolchain_menu = m_file.addMenu("Backend &Toolchain")
        self._refresh_toolchain_menu()
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_run = mb.addMenu("&Run")
        m_run.addAction(self.act_run)
        m_run.addAction(self.act_cancel)
        m_run.addAction(self.act_copy_cmd)
        m_run.addAction(self.act_reset)

        self.presets_menu = mb.addMenu("&Presets")
        self._refresh_presets_menu()

        m_tools = mb.addMenu("&Tools")
        m_tools.addAction("Compare With Binary…").triggered.connect(
            self._compare_binary)
        m_tools.addAction("Section Hex Dump…").triggered.connect(self._hex_dump)

        m_edit = mb.addMenu("&Edit")
        m_edit.addAction(self.act_find)
        m_edit.addAction(self.act_goto)
        m_edit.addAction(self.act_follow)

        m_view = mb.addMenu("&View")
        for dock in (self.options_dock, self.dis_opts_dock, self.sections_dock,
                     self.symbols_dock, self.log_dock):
            m_view.addAction(dock.toggleViewAction())
        m_view.addSeparator()
        m_view.addAction(self.act_aligned)
        m_view.addAction(self.act_pretty_bytes)
        m_view.addAction(self.act_pretty_spacing)
        m_view.addSeparator()
        m_view.addAction(self.act_dark)

        m_help = mb.addMenu("&Help")
        m_help.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setObjectName("toolbar_main")
        tb.setMovable(False)
        for act in (self.act_open, self.act_reload, self.act_run,
                    self.act_cancel, self.act_save, self.act_find,
                    self.act_goto):
            tb.addAction(act)
        tb.addSeparator()
        tb.addAction(self.act_aligned)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_file = QLabel("No file")
        self.lbl_arch = QLabel(self.caps.version or "objdump")
        self.lbl_status = QLabel("Idle")
        self.lbl_lines = QLabel("")
        sb.addWidget(self.lbl_file, 1)
        sb.addPermanentWidget(self.lbl_lines)
        sb.addPermanentWidget(self.lbl_status)
        sb.addPermanentWidget(self.lbl_arch)

    def _connect_navigators(self) -> None:
        # The navigators are created once and live for the window's lifetime, so
        # these are connected exactly once (in __init__). The section filter is
        # routed through a stable slot here rather than bound to self.options
        # directly, so rebuilding the options panel needs no reconnection (and
        # cannot accumulate duplicate connections that fire slots N+1 times).
        self.sections_nav.section_activated.connect(self._apply_section_filter)
        self.symbols_nav.symbol_activated.connect(self._jump_to_symbol)
        self.symbols_nav.symbol_disassemble.connect(self._disassemble_symbol)

    def _apply_section_filter(self, name: str) -> None:
        self.options.set_section_filter(name)

    # -- file lifecycle -----------------------------------------------------

    def open_file(self) -> None:
        start = self.settings.value("last_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open object / executable / archive", start,
            "All files (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        import os
        if not os.path.exists(path):
            QMessageBox.warning(self, "Open", f"File not found:\n{path}")
            return
        self.current_file = path
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._push_recent(path)
        self.setWindowTitle(f"objdump GUI — {os.path.basename(path)}")
        self.lbl_file.setText(path)
        self._update_preview()
        self._load_metadata()
        self.run()

    def _reload(self) -> None:
        if self.current_file:
            self.load_file(self.current_file)
        else:
            self.run()

    def _load_metadata(self) -> None:
        if not self.current_file:
            return
        # Sections via -h, symbols via -t -C; independent of the main options.
        # run_capture parents each QProcess to self and deleteLater()s it on
        # completion, so no manual tracking/cleanup is needed.
        run_capture(
            self.caps.path, ["-h", "--", self.current_file], self,
            lambda out, code: self.sections_nav.load(strip_ansi(out)),
        )
        run_capture(
            self.caps.path, ["-t", "-C", "--", self.current_file], self,
            lambda out, code: self.symbols_nav.load(strip_ansi(out)),
        )

    # -- run lifecycle ------------------------------------------------------

    def run(self) -> None:
        if not self.current_file:
            self.lbl_status.setText("Open a file first")
            self.log.appendPlainText("No file selected — use File ▸ Open.")
            return
        argv = self.options.build_argv()
        if not argv:
            self.lbl_status.setText("No display options selected")
            self.log.appendPlainText(
                "Select at least one display option (e.g. -d, -x) before running."
            )
            return
        argv = argv + ["--", self.current_file]
        self.log.appendPlainText("$ " + self._command_string())
        self.runner.run(argv)

    def _on_run_started(self) -> None:
        self._set_busy(True)
        self.lbl_status.setText("Running…")

    def _on_run_finished(self, out: str, err: str, code: int, crashed: bool) -> None:
        self._set_busy(False)
        # Keep ANSI intact so --disassembler-color can render real colors in raw
        # mode; stripping happens per-render path below.
        self._raw_output = out
        self._render_output()
        if err.strip():
            self.log.appendPlainText(err.rstrip())
        if crashed:
            self.lbl_status.setText("Cancelled / crashed")
        elif code == 0:
            self.lbl_status.setText("Done")
        else:
            self.lbl_status.setText(f"objdump exited {code}")

    def _render_output(self) -> None:
        """Display the last run's output: aligned, ANSI-colored, or plain."""
        raw = self._raw_output
        if self.act_aligned.isChecked():
            # Aligned reformatting is incompatible with inline ANSI spans, so
            # strip color and rely on the syntax highlighter.
            text = format_disassembly(
                strip_ansi(raw),
                show_bytes=self.act_pretty_bytes.isChecked(),
                space_operands=self.act_pretty_spacing.isChecked(),
            )
            self.output.set_text(text)
        elif has_ansi(raw):
            self.output.set_colored(raw)
            text = strip_ansi(raw)
        else:
            text = strip_ansi(raw)
            self.output.set_text(text)
        self.lbl_lines.setText(f"{text.count(chr(10)):,} lines")

    def _on_format_changed(self) -> None:
        self.settings.setValue("aligned", self.act_aligned.isChecked())
        self.settings.setValue("aligned_bytes", self.act_pretty_bytes.isChecked())
        self.settings.setValue("aligned_spacing",
                               self.act_pretty_spacing.isChecked())
        self.act_pretty_bytes.setEnabled(self.act_aligned.isChecked())
        self.act_pretty_spacing.setEnabled(self.act_aligned.isChecked())
        self._render_output()

    def _set_busy(self, busy: bool) -> None:
        # Guard every run-triggering control during the transition so the user
        # cannot launch a second objdump over a live one. This includes the
        # navigators, whose double-click/context actions call run() directly and
        # would otherwise bypass the disabled Run action.
        self.act_run.setEnabled(not busy)
        self.act_reload.setEnabled(not busy)
        self.act_open.setEnabled(not busy)
        self.act_cancel.setEnabled(busy)
        self.symbols_nav.setEnabled(not busy)
        self.sections_nav.setEnabled(not busy)

    # -- navigator interactions --------------------------------------------

    def _jump_to_symbol(self, name: str) -> None:
        # Prefer the function definition (raw "<name>:" or aligned "name:")
        # over call sites ("<name>"); fall back to any occurrence.
        for needle in (f"<{name}>:", f"{name}:", f"<{name}>", name):
            if self.output.goto_text(needle):
                return
        self.lbl_status.setText(f"'{name}' not in current output")

    def _disassemble_symbol(self, name: str) -> None:
        self.options.set_disassemble_symbol(name)
        self.run()

    def _goto_address(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Go to Address", "Address (hex, e.g. 0x401136 or 401136):"
        )
        if not ok or not text.strip():
            return
        if self.output.goto_address(text):
            self.lbl_status.setText(f"Jumped to {text.strip()}")
        else:
            self.lbl_status.setText(f"Address {text.strip()} not in output")

    # -- tools: compare & hex dump -----------------------------------------

    def _objdump_text(self, argv: list[str], path: str) -> str:
        try:
            cp = subprocess.run(            # noqa: S603 (list argv, no shell)
                [self.caps.path, *argv, "--", path],
                capture_output=True, text=True, timeout=120, check=False,
            )
            return strip_ansi(cp.stdout or "")
        except (OSError, subprocess.SubprocessError) as exc:
            return f"<error running objdump: {exc}>"

    def _compare_binary(self) -> None:
        if not self.current_file:
            QMessageBox.information(self, "Compare", "Open a file first.")
            return
        other, _ = QFileDialog.getOpenFileName(
            self, "Compare with…", self.settings.value("last_dir", ""),
            "All files (*)"
        )
        if not other:
            return
        argv = self.options.build_argv()
        if not any(a in argv for a in ("-d", "-D")):
            argv = ["-d", *argv]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            a = format_disassembly(self._objdump_text(argv, self.current_file))
            b = format_disassembly(self._objdump_text(argv, other))
        finally:
            QApplication.restoreOverrideCursor()
        diff = "\n".join(difflib.unified_diff(
            a.splitlines(), b.splitlines(),
            fromfile=os.path.basename(self.current_file),
            tofile=os.path.basename(other), lineterm="",
        ))
        from .widgets.diff_dialog import DiffDialog
        title = (f"Diff: {os.path.basename(self.current_file)} "
                 f"↔ {os.path.basename(other)}")
        DiffDialog(title, diff, self).exec()

    def _hex_dump(self) -> None:
        if not self.current_file:
            QMessageBox.information(self, "Hex Dump", "Open a file first.")
            return
        names = self.sections_nav.section_names()
        if not names:
            QMessageBox.information(self, "Hex Dump", "No sections loaded yet.")
            return
        sec, ok = QInputDialog.getItem(
            self, "Section Hex Dump", "Section:", names, 0, False
        )
        if not ok:
            return
        from .widgets.diff_dialog import TextViewerDialog
        text = self._objdump_text(["-s", "-j", sec], self.current_file)
        TextViewerDialog(f"Hex dump: {sec}", text, self).exec()

    # -- export -------------------------------------------------------------

    def _export_to(self, content: str, what: str, default_ext: str) -> None:
        if not content:
            QMessageBox.information(self, "Export", f"There is no {what} yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {what}", self.settings.value("last_dir", ""),
            default_ext,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self.lbl_status.setText(f"Exported {what} to {path}")
        except OSError as exc:
            QMessageBox.warning(self, "Export", f"Could not write:\n{exc}")

    def _export_raw(self) -> None:
        self._export_to(strip_ansi(self._raw_output), "raw output",
                        "Text files (*.txt);;All files (*)")

    def _export_aligned(self) -> None:
        text = format_disassembly(
            strip_ansi(self._raw_output),
            show_bytes=self.act_pretty_bytes.isChecked(),
            space_operands=self.act_pretty_spacing.isChecked(),
        )
        self._export_to(text, "aligned output",
                        "Text files (*.txt);;All files (*)")

    def _export_html(self) -> None:
        # The syntax highlighter formats the document, so toHtml() carries colors.
        html = self.output.editor.document().toHtml()
        self._export_to(html if self.output.text() else "", "highlighted HTML",
                        "HTML files (*.html);;All files (*)")

    # -- option presets -----------------------------------------------------

    def _presets(self) -> dict:
        raw = self.settings.value("presets", "{}")
        try:
            return json.loads(raw) if isinstance(raw, str) else {}
        except (ValueError, TypeError):
            return {}

    def _save_presets(self, presets: dict) -> None:
        self.settings.setValue("presets", json.dumps(presets))
        self._refresh_presets_menu()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        name = name.strip()
        if not ok or not name:
            return
        presets = self._presets()
        presets[name] = self.options.get_state()
        self._save_presets(presets)
        self.lbl_status.setText(f"Saved preset '{name}'")

    def _load_preset(self, name: str) -> None:
        presets = self._presets()
        if name in presets:
            self.options.set_state(presets[name])
            self.lbl_status.setText(f"Loaded preset '{name}'")
            if self.current_file:
                self.run()

    def _delete_preset(self) -> None:
        presets = self._presets()
        if not presets:
            return
        name, ok = QInputDialog.getItem(
            self, "Delete Preset", "Preset:", list(presets), 0, False
        )
        if ok and name in presets:
            del presets[name]
            self._save_presets(presets)
            self.lbl_status.setText(f"Deleted preset '{name}'")

    def _refresh_presets_menu(self) -> None:
        self.presets_menu.clear()
        self.presets_menu.addAction("Save Current As…").triggered.connect(
            self._save_preset
        )
        presets = self._presets()
        if presets:
            self.presets_menu.addSeparator()
            for name in sorted(presets):
                self.presets_menu.addAction(name).triggered.connect(
                    lambda _=False, n=name: self._load_preset(n)
                )
            self.presets_menu.addSeparator()
            self.presets_menu.addAction("Delete Preset…").triggered.connect(
                self._delete_preset
            )

    # -- command preview / clipboard ---------------------------------------

    def _command_string(self) -> str:
        argv = self.options.build_argv()
        target = ["--", self.current_file] if self.current_file else ["<file>"]
        return shlex.join([self.caps.path, *argv, *target])

    def _update_preview(self) -> None:
        self.preview.setText(self._command_string())

    def _copy_command(self) -> None:
        QGuiApplication.clipboard().setText(self._command_string())
        self.lbl_status.setText("Command copied")

    # -- output saving ------------------------------------------------------

    def _save_output(self) -> None:
        text = self.output.text()
        if not text:
            QMessageBox.information(self, "Save", "There is no output to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save output", self.settings.value("last_dir", ""),
            "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.lbl_status.setText(f"Saved {path}")
        except OSError as exc:
            QMessageBox.warning(self, "Save", f"Could not save:\n{exc}")

    # -- binary selection ---------------------------------------------------

    def _choose_binary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select an objdump binary (e.g. a cross toolchain)", "",
            "All files (*)"
        )
        if path:
            self._switch_binary(path)

    def _switch_binary(self, path: str) -> None:
        """Switch the active objdump backend (e.g. to avr-objdump) and re-probe."""
        if path == self.caps.path:
            return
        if self.runner.busy:
            self.runner.cancel()
        caps = introspect.probe(path)
        if not caps.version:
            QMessageBox.warning(
                self, "objdump",
                f"'{path}' does not look like a working GNU objdump."
            )
            self._refresh_toolchain_menu()   # restore the checked state
            return
        self.caps = caps
        self.runner.set_program(path)
        self.lbl_arch.setText(caps.version)
        self.output.set_arch(introspect.arch_family(caps))
        self._rebuild_options()
        self._refresh_toolchain_menu()
        if self.current_file:
            self._load_metadata()
            self.run()
        self._update_preview()

    def _rebuild_options(self) -> None:
        new_panel = OptionsPanel(self.caps)
        new_panel.changed.connect(self._update_preview)
        self.options_dock.setWidget(new_panel)
        self.options = new_panel
        # Navigators stay connected to stable MainWindow slots, so they are NOT
        # reconnected here (doing so would duplicate the connections).
        # Rebuild the -M dock for the new architecture too.
        self.dis_opts_dock.setWidget(self._build_disasm_opts())

    def _refresh_toolchain_menu(self) -> None:
        import os
        self.toolchain_menu.clear()
        group = QActionGroup(self)
        group.setExclusive(True)
        self._toolchain_group = group        # keep a ref so it isn't GC'd
        current = self.caps.path
        cur_real = os.path.realpath(current) if current else ""
        paths = list(self._toolchains)
        if current and current not in paths:
            paths.insert(0, current)
        for p in paths:
            act = self.toolchain_menu.addAction(os.path.basename(p))
            act.setCheckable(True)
            act.setChecked(os.path.realpath(p) == cur_real)
            act.setToolTip(p)
            group.addAction(act)
            act.triggered.connect(
                lambda _=False, path=p: self._switch_binary(path)
            )
        if not paths:
            empty = self.toolchain_menu.addAction("(no GNU objdump found)")
            empty.setEnabled(False)
        self.toolchain_menu.addSeparator()
        self.toolchain_menu.addAction("Rescan PATH").triggered.connect(
            self._rescan_toolchains
        )
        self.toolchain_menu.addAction("Browse for objdump…").triggered.connect(
            self._choose_binary
        )

    def _rescan_toolchains(self) -> None:
        self._toolchains = introspect.discover_objdumps()
        self._refresh_toolchain_menu()

    # -- recent files -------------------------------------------------------

    def _recent(self) -> list[str]:
        return list(self.settings.value("recent", [], type=list) or [])

    def _push_recent(self, path: str) -> None:
        recent = [p for p in self._recent() if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent", recent[:MAX_RECENT])
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self._recent()
        if not recent:
            act = self.recent_menu.addAction("(empty)")
            act.setEnabled(False)
            return
        for p in recent:
            act = self.recent_menu.addAction(p)
            act.triggered.connect(lambda _=False, path=p: self.load_file(path))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction("Clear list")
        clear.triggered.connect(self._clear_recent)

    def _clear_recent(self) -> None:
        self.settings.setValue("recent", [])
        self._refresh_recent_menu()

    # -- theme --------------------------------------------------------------

    def _toggle_theme(self, dark: bool) -> None:
        self._dark = dark
        self.settings.setValue("dark", dark)
        self.output.set_theme(dark)
        self._apply_theme()

    def _apply_theme(self) -> None:
        if self._dark:
            self.setStyleSheet(_DARK_QSS)
        else:
            self.setStyleSheet("")

    # -- misc ---------------------------------------------------------------

    def _about(self) -> None:
        QMessageBox.about(
            self, "About objdump GUI",
            "<h3>objdump GUI</h3>"
            "<p>A professional front-end for GNU binutils <code>objdump</code>, "
            "exposing every option with live command preview, syntax-highlighted "
            "disassembly, and section/symbol navigators.</p>"
            f"<p><b>Backend:</b> {self.caps.version}<br>"
            f"<b>Path:</b> {self.caps.path}</p>"
        )

    def _restore_layout(self) -> None:
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        state = self.settings.value("windowState")
        if state is not None:
            self.restoreState(state)

    def _restore_last_options(self) -> None:
        raw = self.settings.value("last_options")
        if not raw:
            return
        try:
            state = json.loads(raw)
        except (ValueError, TypeError):
            return
        self.options.set_state(state)

    def closeEvent(self, event):
        # Persist window geometry, dock/toolbar layout and last-used options.
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("last_options",
                               json.dumps(self.options.get_state()))
        self.runner.cancel()
        super().closeEvent(event)


_DARK_QSS = """
QMainWindow, QWidget { background: #1e1e1e; color: #d4d4d4; }
QPlainTextEdit, QLineEdit, QTableWidget, QScrollArea {
    background: #252526; color: #d4d4d4; border: 1px solid #333;
}
QGroupBox { border: 1px solid #3a3a3a; margin-top: 8px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #4ec9b0; }
QHeaderView::section { background: #2d2d30; color: #d4d4d4; border: 0; padding: 3px; }
QTableWidget { alternate-background-color: #2a2a2b; gridline-color: #333; }
QMenuBar, QMenu, QToolBar, QStatusBar { background: #2d2d30; color: #d4d4d4; }
QMenu::item:selected, QMenuBar::item:selected { background: #094771; }
QPushButton, QToolButton {
    background: #333337; border: 1px solid #444; padding: 3px 8px;
}
QPushButton:hover, QToolButton:hover { background: #3f3f46; }
QPushButton:disabled { color: #777; }
QCheckBox, QLabel { color: #d4d4d4; }
QDockWidget::title { background: #2d2d30; padding: 4px; }
QComboBox { background: #3c3c3c; border: 1px solid #444; padding: 2px; }
"""
