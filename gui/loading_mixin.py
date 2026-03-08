"""
gui/loading_mixin.py
--------------------
Reusable visual-feedback utilities for all interactive actions.

Every button click, tab switch, dialog open, or async operation that takes
noticeable time should show the user SOMETHING is happening.  This module
provides three lightweight helpers that any widget can mix in:

    LoadingMixin        — add to any QWidget subclass
    with_busy_cursor()  — context manager (cursor only, no widget needed)
    btn_loading()       — context manager that animates a QPushButton

Usage examples
──────────────

# 1. Mix into a QWidget class
class MyDialog(QDialog, LoadingMixin):
    def __init__(self):
        super().__init__()
        self._loading_init()          # call once in __init__

    def _fetch_data(self):
        with self.busy_cursor():      # show wait cursor
            data = heavy_operation()

    def _open_sub_dialog(self):
        with self.btn_loading(self.btn_open, "Opening…"):
            dlg = SubDialog(self)
            dlg.exec_()


# 2. Standalone context manager (no mixin needed)
from gui.loading_mixin import with_busy_cursor, btn_loading

with with_busy_cursor():
    result = blocking_call()

with btn_loading(self.btn_start, "Starting…"):
    self.engine.start()
"""

from __future__ import annotations

import contextlib
import logging
from typing import Optional, Generator

from PyQt5.QtCore  import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QPushButton, QWidget

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone context managers (no class needed)
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def with_busy_cursor() -> Generator[None, None, None]:
    """
    Set the application-wide wait cursor for the duration of the block.

    with with_busy_cursor():
        slow_thing()
    """
    try:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        yield
    finally:
        QApplication.restoreOverrideCursor()


@contextlib.contextmanager
def btn_loading(
    button:       QPushButton,
    loading_text: str = "Loading…",
    *,
    disable: bool = True,
) -> Generator[None, None, None]:
    """
    Show a loading label on a QPushButton and optionally disable it for the
    duration of the block. The original text and enabled-state are restored
    automatically — even if an exception is raised.

    with btn_loading(self.btn_start, "Starting…"):
        self.engine.start()
    """
    if button is None:
        yield
        return

    original_text    = button.text()
    original_enabled = button.isEnabled()
    try:
        button.setText(loading_text)
        if disable:
            button.setEnabled(False)
        QApplication.processEvents()
        yield
    finally:
        button.setText(original_text)
        if disable:
            button.setEnabled(original_enabled)
        QApplication.processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# Mixin for QWidget subclasses
# ─────────────────────────────────────────────────────────────────────────────

class LoadingMixin:
    """
    Mixin that adds visual-feedback helpers to any QWidget subclass.

    Call self._loading_init() once in __init__ after super().__init__().

    Provides
    ────────
    self.busy_cursor()           → context manager: wait cursor
    self.btn_loading(btn, text)  → context manager: button animation
    self.show_loading(text)      → show an inline loading indicator (optional)
    self.hide_loading()          → hide the inline indicator
    self.set_status(text, color) → update an optional status label (if wired)

    Optional wiring
    ────────────────
    If you create a QLabel named `self._status_label` the mixin will write
    status messages to it via `set_status()`.
    """

    def _loading_init(self) -> None:
        """Call once in the widget's __init__."""
        self.__loading_active = False

    # ── Wait cursor ───────────────────────────────────────────────────────────

    @contextlib.contextmanager
    def busy_cursor(self) -> Generator[None, None, None]:
        """Set app-wide wait cursor while the block runs."""
        with with_busy_cursor():
            yield

    # ── Button animation ──────────────────────────────────────────────────────

    @contextlib.contextmanager
    def btn_loading(
        self,
        button:       Optional[QPushButton],
        loading_text: str  = "Loading…",
        *,
        disable: bool = True,
    ) -> Generator[None, None, None]:
        """Animate a button while the block runs."""
        with btn_loading(button, loading_text, disable=disable):
            yield

    # ── Inline loading indicator ──────────────────────────────────────────────

    def show_loading(self, text: str = "Loading…") -> None:
        """
        Show a loading message.

        If self._status_label exists it will be used.  Otherwise this is a
        no-op — subclasses can override for richer UI.
        """
        self.__loading_active = True
        self.set_status(text)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

    def hide_loading(self) -> None:
        """Hide the loading indicator and restore normal state."""
        self.__loading_active = False
        self.set_status("")
        QApplication.restoreOverrideCursor()
        QApplication.processEvents()

    def is_loading(self) -> bool:
        return getattr(self, "__loading_active", False)

    # ── Optional status label ─────────────────────────────────────────────────

    def set_status(self, text: str, color: Optional[str] = None) -> None:
        """
        Write a message to self._status_label if it exists.

        Subclasses can override this to route messages elsewhere.
        """
        try:
            label = getattr(self, "_status_label", None)
            if label is None:
                return
            label.setText(text)
            if color:
                label.setStyleSheet(
                    f"color: {color}; background: transparent; border: none;"
                )
        except Exception as exc:
            logger.debug(f"[LoadingMixin.set_status] {exc}")