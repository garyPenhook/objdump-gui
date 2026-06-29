"""Asynchronous objdump execution via QProcess.

The main, possibly-large disassembly run streams through :class:`ObjdumpRunner`
so the UI never blocks and the run is cancellable. Small metadata queries (the
Sections / Symbols navigators) use :func:`run_capture`, a fire-and-forget
QProcess that calls back with the full output.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal


class ObjdumpRunner(QObject):
    """A single reusable, cancellable runner for the primary output view."""

    started = Signal()
    # finished(stdout, stderr, exit_code, crashed)
    finished = Signal(str, str, int, bool)

    def __init__(self, program: str, parent=None):
        super().__init__(parent)
        self.program = program
        self._proc: QProcess | None = None
        self._out = bytearray()
        self._err = bytearray()

    @property
    def busy(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def set_program(self, program: str) -> None:
        self.program = program

    def run(self, args: list[str]) -> None:
        # Guard: never start a second run on top of a live one. Callers disable
        # the Run action while busy, but enforce it here too.
        if self.busy:
            self.cancel()
        # Defensively detach any prior process still lingering (e.g. a kill that
        # didn't reap within cancel()'s wait), so its late signals can never
        # read/write the new run's buffers or null out the new self._proc.
        self._detach(self._proc)
        self._out = bytearray()
        self._err = bytearray()
        proc = QProcess(self)
        self._proc = proc
        proc.readyReadStandardOutput.connect(self._read_out)
        proc.readyReadStandardError.connect(self._read_err)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self.started.emit()
        proc.start(self.program, args)

    def cancel(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(2000)

    def _detach(self, proc) -> None:
        """Disconnect and schedule deletion of a finished/abandoned process."""
        if proc is None:
            return
        try:
            proc.readyReadStandardOutput.disconnect(self._read_out)
            proc.readyReadStandardError.disconnect(self._read_err)
            proc.finished.disconnect(self._on_finished)
            proc.errorOccurred.disconnect(self._on_error)
        except (RuntimeError, TypeError):
            pass
        proc.deleteLater()
        if self._proc is proc:
            self._proc = None

    # -- internals ----------------------------------------------------------

    def _read_out(self) -> None:
        if self._proc:
            self._out += bytes(self._proc.readAllStandardOutput())

    def _read_err(self) -> None:
        if self._proc:
            self._err += bytes(self._proc.readAllStandardError())

    def _on_finished(self, code: int, status) -> None:
        self._read_out()
        self._read_err()
        crashed = status == QProcess.CrashExit
        out = self._out.decode("utf-8", "replace")
        err = self._err.decode("utf-8", "replace")
        self._detach(self._proc)
        self.finished.emit(out, err, code, crashed)

    def _on_error(self, err) -> None:
        if err == QProcess.FailedToStart:
            self._detach(self._proc)
            self.finished.emit(
                "", f"Failed to start '{self.program}'. Is it installed?", -1, True
            )


def run_capture(program: str, args: list[str], parent, callback) -> QProcess:
    """Run a short command, calling ``callback(stdout_str, exit_code)`` once.

    The QProcess is parented to ``parent`` so it stays alive until completion,
    then schedules its own deletion. The callback fires exactly once even though
    a crash emits both ``errorOccurred`` and ``finished``.
    """
    proc = QProcess(parent)
    buf = bytearray()
    state = {"done": False}

    def _drain():
        buf.extend(bytes(proc.readAllStandardOutput()))
        buf.extend(bytes(proc.readAllStandardError()))

    def _finish(out: str, code: int):
        if state["done"]:
            return
        state["done"] = True
        proc.deleteLater()
        callback(out, code)

    def _done(code, _status):
        _drain()
        _finish(buf.decode("utf-8", "replace"), code)

    proc.readyReadStandardOutput.connect(_drain)
    proc.readyReadStandardError.connect(_drain)
    proc.finished.connect(_done)
    proc.errorOccurred.connect(lambda *_: _finish("", -1))
    proc.start(program, args)
    return proc
