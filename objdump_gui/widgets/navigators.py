"""Left-hand navigator panes populated from dedicated metadata runs.

These give the user a browsable index of the binary independent of the main
options: a Sections table (from ``objdump -h``) and a filterable Symbols table
(from ``objdump -t -C``). Activating a row emits a signal the main window uses to
jump to / disassemble that location.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..parsers import Section, Symbol, parse_sections, parse_symbols


class SectionsNavigator(QWidget):
    section_activated = Signal(str)   # section name (double-click)

    COLUMNS = ["Name", "Size", "VMA", "LMA", "Flags"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter sections…")
        self.filter.textChanged.connect(self._apply_filter)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        _setup_table(self.table)
        self.table.itemDoubleClicked.connect(self._on_activate)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.filter)
        lay.addWidget(self.table)
        self._sections: list[Section] = []

    def load(self, text: str) -> None:
        self._sections = parse_sections(text)
        self.table.setRowCount(0)
        for s in self._sections:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, val in enumerate(
                [s.name, s.size, s.vma, s.lma, s.flags]
            ):
                item = QTableWidgetItem(val)
                if c in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.filter.text().lower()
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0)
            self.table.setRowHidden(
                r, bool(needle) and needle not in (name.text().lower() if name else "")
            )

    def _on_activate(self, item: QTableWidgetItem) -> None:
        name = self.table.item(item.row(), 0)
        if name:
            self.section_activated.emit(name.text())


class SymbolsNavigator(QWidget):
    symbol_activated = Signal(str)         # symbol name (double-click)
    symbol_disassemble = Signal(str)       # request --disassemble=name

    COLUMNS = ["Address", "Flags", "Section", "Size", "Name"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter symbols…  (substring)")
        self.filter.textChanged.connect(self._apply_filter)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        _setup_table(self.table)
        self.table.itemDoubleClicked.connect(self._on_activate)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context)
        # Re-apply the substring filter after a header sort: setRowHidden flags
        # are tied to row index, so re-sorting would otherwise hide wrong rows.
        self.table.horizontalHeader().sortIndicatorChanged.connect(
            lambda *_: self._apply_filter()
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.filter)
        lay.addWidget(self.table)
        self._symbols: list[Symbol] = []

    def load(self, text: str) -> None:
        self._symbols = parse_symbols(text)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for s in self._symbols:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, val in enumerate(
                [s.address, s.flags, s.section, s.size, s.name]
            ):
                item = QTableWidgetItem(val)
                if c in (0, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.filter.text().lower()
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 4)
            self.table.setRowHidden(
                r, bool(needle) and needle not in (name.text().lower() if name else "")
            )

    def _name_at_row(self, row: int) -> str | None:
        if row < 0:
            return None
        item = self.table.item(row, 4)
        return item.text() if item else None

    def _on_activate(self, item: QTableWidgetItem) -> None:
        name = self.table.item(item.row(), 4)
        if name and name.text():
            self.symbol_activated.emit(name.text())

    def _on_context(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        # Resolve the symbol under the cursor, not the (possibly different)
        # currently-selected row: right-click does not move the selection.
        name = self._name_at_row(self.table.indexAt(pos).row())
        if not name:
            return
        menu = QMenu(self)
        act_find = menu.addAction("Find in output")
        act_dis = menu.addAction(f"Disassemble {name} (--disassemble=)")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == act_find:
            self.symbol_activated.emit(name)
        elif chosen == act_dis:
            self.symbol_disassemble.emit(name)


def _setup_table(table: QTableWidget) -> None:
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    hdr = table.horizontalHeader()
    hdr.setStretchLastSection(True)
    hdr.setSectionResizeMode(QHeaderView.Interactive)
