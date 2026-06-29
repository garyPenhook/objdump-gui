"""Application bootstrap: locate objdump, probe its capabilities, show the
window, and optionally load a file passed on the command line."""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import introspect
from .main_window import MainWindow


def _load_icon() -> QIcon | None:
    path = os.path.join(os.path.dirname(__file__), "..", "packaging",
                        "objdump-gui.svg")
    return QIcon(path) if os.path.exists(path) else None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("objdump-gui")
    app.setOrganizationName("objdump-gui")
    icon = _load_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    # Allow an explicit binary via env (OBJDUMP) or first --objdump=… style arg.
    preferred = None
    files: list[str] = []
    for a in argv[1:]:
        if a.startswith("--objdump="):
            preferred = a.split("=", 1)[1]
        elif not a.startswith("-"):
            files.append(a)

    path = introspect.find_objdump(preferred)
    if not path:
        QMessageBox.critical(
            None, "objdump not found",
            "No 'objdump' binary was found on PATH.\n\n"
            "Install GNU binutils, or start with --objdump=/path/to/objdump."
        )
        return 2

    caps = introspect.probe(path)
    win = MainWindow(caps)
    win.show()
    if files:
        win.load_file(files[0])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
