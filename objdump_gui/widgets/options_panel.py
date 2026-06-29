"""The options panel — generated entirely from :func:`options.build_groups`.

Renders one collapsible-feeling group box per category with the right widget per
option kind, exposes :meth:`build_argv` for the command builder, and emits
:attr:`changed` on every edit so the command preview stays live. A search box
filters visible options by label/help.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..options import build_groups


class _Row:
    """Binds one OptSpec to its widget(s); knows how to read/reset its value."""

    def __init__(self, spec, widget, getter, setter, label_widget=None,
                 extra_widgets=None):
        self.spec = spec
        self.widget = widget
        self.getter = getter
        self.setter = setter
        self.label_widget = label_widget
        self.extra_widgets = extra_widgets or []

    def value(self):
        return self.getter()

    def reset(self):
        self.setter(self.spec.default)

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        hay = f"{self.spec.label} {self.spec.help} {self.spec.key}".lower()
        return needle in hay

    def set_visible(self, vis: bool):
        self.widget.setVisible(vis)
        if self.label_widget is not None:
            self.label_widget.setVisible(vis)
        for w in self.extra_widgets:
            w.setVisible(vis)


class OptionsPanel(QScrollArea):
    changed = Signal()

    def __init__(self, caps, parent=None):
        super().__init__(parent)
        self.caps = caps
        self.rows: list[_Row] = []
        self._groups_meta = build_groups(caps)

        container = QWidget()
        self._vbox = QVBoxLayout(container)
        self._vbox.setContentsMargins(6, 6, 6, 6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search options…")
        self.search.textChanged.connect(self._filter)
        self._vbox.addWidget(self.search)

        self._group_boxes: list[QGroupBox] = []
        for title, specs in self._groups_meta:
            box = self._build_group(title, specs)
            self._group_boxes.append(box)
            self._vbox.addWidget(box)
        self._vbox.addStretch(1)

        self.setWidget(container)
        self.setWidgetResizable(True)

    # -- group / widget construction ----------------------------------------

    def _build_group(self, title: str, specs) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        grid.setColumnStretch(1, 1)
        r = 0
        for spec in specs:
            r = self._build_row(spec, grid, r)
        return box

    def _build_row(self, spec, grid, r) -> int:
        kind = spec.kind
        if kind == "flag":
            cb = QCheckBox(spec.label)
            cb.setToolTip(spec.help)
            cb.setChecked(bool(spec.default))
            cb.toggled.connect(self.changed)
            grid.addWidget(cb, r, 0, 1, 2)
            self.rows.append(
                _Row(spec, cb, cb.isChecked,
                     lambda v, w=cb: w.setChecked(bool(v)))
            )
            return r + 1

        if kind in ("text", "int"):
            lbl = QLabel(spec.label)
            lbl.setToolTip(spec.help)
            le = QLineEdit()
            le.setPlaceholderText(spec.placeholder)
            le.setToolTip(spec.help)
            le.textChanged.connect(self.changed)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(le, r, 1)
            self.rows.append(
                _Row(spec, le, le.text, lambda v, w=le: w.setText(v or ""), lbl)
            )
            return r + 1

        if kind in ("sections",):
            lbl = QLabel(spec.label)
            lbl.setToolTip(spec.help)
            le = QLineEdit()
            le.setPlaceholderText(spec.placeholder)
            le.setToolTip(spec.help)
            le.textChanged.connect(self.changed)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(le, r, 1)
            self.rows.append(
                _Row(spec, le, le.text, lambda v, w=le: w.setText(v or ""), lbl)
            )
            return r + 1

        if kind == "choice":
            lbl = QLabel(spec.label)
            lbl.setToolTip(spec.help)
            combo = QComboBox()
            combo.setToolTip(spec.help)
            for disp, data in spec.choices:
                combo.addItem(disp, data)
            combo.currentIndexChanged.connect(self.changed)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(combo, r, 1)
            self.rows.append(
                _Row(spec, combo, combo.currentData,
                     lambda v, w=combo: w.setCurrentIndex(max(0, w.findData(v))), lbl)
            )
            return r + 1

        if kind == "dwarf":
            return self._build_dwarf(spec, grid, r)

        return r

    def _build_dwarf(self, spec, grid, r) -> int:
        lbl = QLabel(spec.label)
        lbl.setToolTip(spec.help)
        grid.addWidget(lbl, r, 0, 1, 2)
        r += 1
        holder = QWidget()
        hgrid = QGridLayout(holder)
        hgrid.setContentsMargins(8, 0, 0, 0)
        checks: list[QCheckBox] = []
        per_col = 3
        for i, (disp, data) in enumerate(spec.choices):
            cb = QCheckBox(disp)
            cb.toggled.connect(self.changed)
            checks.append(cb)
            hgrid.addWidget(cb, i // per_col, i % per_col)
        grid.addWidget(holder, r, 0, 1, 2)

        def getter():
            return [c.text() for c in checks if c.isChecked()]

        def setter(_v):
            for c in checks:
                c.setChecked(False)

        self.rows.append(_Row(spec, holder, getter, setter, lbl, checks))
        return r + 1

    # -- public API ---------------------------------------------------------

    def build_argv(self) -> list[str]:
        argv: list[str] = []
        for row in self.rows:
            argv += row.spec.build(row.value())
        return argv

    def has_any_display_option(self) -> bool:
        """True if at least one option that produces output is selected."""
        return bool(self.build_argv())

    def reset(self) -> None:
        for row in self.rows:
            row.reset()
        self.changed.emit()

    def set_section_filter(self, section: str) -> None:
        """Populate the -j 'limit to sections' field (used by the navigator)."""
        for row in self.rows:
            if row.spec.key == "j":
                row.setter(section)
                self.changed.emit()
                return

    def set_disassemble_symbol(self, name: str) -> None:
        for row in self.rows:
            if row.spec.key == "disassemble_sym":
                row.setter(name)
                self.changed.emit()
                return

    def _filter(self, text: str) -> None:
        needle = text.lower().strip()
        for box, (_title, _specs) in zip(self._group_boxes, self._groups_meta):
            any_visible = False
            for row in self.rows:
                if row.spec in _specs:
                    vis = row.matches(needle)
                    row.set_visible(vis)
                    any_visible = any_visible or vis
            box.setVisible(any_visible)
