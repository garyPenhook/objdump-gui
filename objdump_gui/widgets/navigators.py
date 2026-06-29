"""Left-hand navigator panes (Sections, Symbols), backed by a model/view.

Using QAbstractTableModel + QSortFilterProxyModel keeps population instant and
filtering/sorting cheap even for binaries with tens of thousands of symbols, and
the potentially-expensive text parsing runs on a worker thread so the UI never
blocks. A per-pane generation counter discards results from superseded loads
(e.g. when the user switches files rapidly).
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    QSortFilterProxyModel,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..parsers import parse_sections, parse_symbols


# (header, attribute, numeric) per column.
_SECTION_COLS = [
    ("Name", "name", False), ("Size", "size", True), ("VMA", "vma", True),
    ("LMA", "lma", True), ("Flags", "flags", False),
]
_SYMBOL_COLS = [
    ("Address", "address", True), ("Flags", "flags", False),
    ("Section", "section", False), ("Size", "size", True), ("Name", "name", False),
]


class ObjTableModel(QAbstractTableModel):
    """Generic read-only table over a list of dataclass rows."""

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self._cols = columns
        self._rows: list = []

    def set_rows(self, rows: list) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._cols)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._cols[section][0]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        _header, attr, numeric = self._cols[index.column()]
        val = getattr(self._rows[index.row()], attr, "")
        if role == Qt.DisplayRole:
            return val
        if role == Qt.UserRole:
            # Sort role: numeric columns sort by integer value, others by text.
            if numeric:
                try:
                    return int(val, 16)
                except (ValueError, TypeError):
                    return 0
            return val
        if role == Qt.TextAlignmentRole and numeric:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None


class _ParseSignals(QObject):
    done = Signal(int, object)   # generation, rows


class _ParseWorker(QRunnable):
    def __init__(self, fn, text, generation, signals):
        super().__init__()
        self._fn, self._text = fn, text
        self._gen, self._signals = generation, signals

    def run(self):
        try:
            rows = self._fn(self._text)
        except Exception:            # parsing is best-effort; never crash a thread
            rows = []
        self._signals.done.emit(self._gen, rows)


class _Navigator(QWidget):
    """Base navigator: filter box + sortable table + threaded parse."""

    _COLS: list = []
    _PARSE = staticmethod(lambda text: [])
    _NAME_COL = 0
    _FILTER_HINT = "Filter…"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gen = 0
        self._signals = _ParseSignals()
        self._signals.done.connect(self._on_parsed)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText(self._FILTER_HINT)

        self.model = ObjTableModel(self._COLS, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)
        self.proxy.setFilterRole(Qt.DisplayRole)
        self.proxy.setFilterKeyColumn(self._NAME_COL)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)

        self.view = QTableView()
        self.view.setModel(self.proxy)
        _setup_view(self.view)
        self.view.doubleClicked.connect(self._on_double_click)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.filter)
        lay.addWidget(self.view)

    def load(self, text: str) -> None:
        self._gen += 1
        worker = _ParseWorker(self._PARSE, text, self._gen, self._signals)
        QThreadPool.globalInstance().start(worker)

    def _on_parsed(self, generation: int, rows: list) -> None:
        if generation != self._gen:
            return                   # a newer load() superseded this one
        self.model.set_rows(rows)

    def count(self) -> int:
        return self.model.rowCount()

    def _name_at(self, proxy_index) -> str | None:
        if not proxy_index.isValid():
            return None
        src = self.proxy.mapToSource(proxy_index)
        return self.model.data(self.model.index(src.row(), self._NAME_COL))

    def _on_double_click(self, proxy_index):
        raise NotImplementedError


class SectionsNavigator(_Navigator):
    section_activated = Signal(str)

    _COLS = _SECTION_COLS
    _PARSE = staticmethod(parse_sections)
    _NAME_COL = 0
    _FILTER_HINT = "Filter sections…"

    def section_names(self) -> list[str]:
        return [self.model.data(self.model.index(r, 0))
                for r in range(self.model.rowCount())]

    def _on_double_click(self, proxy_index):
        name = self._name_at(proxy_index)
        if name:
            self.section_activated.emit(name)


class SymbolsNavigator(_Navigator):
    symbol_activated = Signal(str)
    symbol_disassemble = Signal(str)

    _COLS = _SYMBOL_COLS
    _PARSE = staticmethod(parse_symbols)
    _NAME_COL = 4
    _FILTER_HINT = "Filter symbols…  (substring)"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context)

    def _on_double_click(self, proxy_index):
        name = self._name_at(proxy_index)
        if name:
            self.symbol_activated.emit(name)

    def _on_context(self, pos):
        name = self._name_at(self.view.indexAt(pos))
        if not name:
            return
        menu = QMenu(self)
        act_find = menu.addAction("Find in output")
        act_dis = menu.addAction(f"Disassemble {name} (--disassemble=)")
        chosen = menu.exec(self.view.viewport().mapToGlobal(pos))
        if chosen == act_find:
            self.symbol_activated.emit(name)
        elif chosen == act_dis:
            self.symbol_disassemble.emit(name)


def _setup_view(view: QTableView) -> None:
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setAlternatingRowColors(True)
    view.setSortingEnabled(True)
    view.setShowGrid(False)
    view.verticalHeader().setVisible(False)
    hdr = view.horizontalHeader()
    hdr.setStretchLastSection(True)
    hdr.setSectionResizeMode(QHeaderView.Interactive)
