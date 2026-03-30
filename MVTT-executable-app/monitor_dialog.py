# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
Monitor detection and selection dialog for the MVTT Battlemap player window.

Provides:
- get_available_monitors()  — list of monitors excluding the GM window's monitor
- show_monitor_selector()   — modal dialog to pick from multiple monitors
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Optional

try:
    import screeninfo

    _SCREENINFO_AVAILABLE = True
except ImportError:
    _SCREENINFO_AVAILABLE = False

# Color palette matching the app design system.
_BG = "#0c1117"
_PANEL = "#101722"
_INK = "#e7edf8"
_MUTED = "#98a8bf"
_LINE = "#27364a"
_BUTTON_BG = "#d9ecff"
_BUTTON_FG = "#102033"
_BUTTON_HOVER = "#f2f9ff"


def get_available_monitors(gm_window: tk.Tk) -> list:
    """
    Returns monitors not currently occupied by gm_window.
    Returns an empty list if screeninfo is unavailable or only one monitor exists.
    """
    if not _SCREENINFO_AVAILABLE:
        return []

    all_monitors = screeninfo.get_monitors()
    if len(all_monitors) <= 1:
        return []

    gm_monitor = _monitor_for_window(gm_window, all_monitors)
    return [m for m in all_monitors if m is not gm_monitor]


def show_monitor_selector(parent: tk.Tk, monitors: list) -> Optional[object]:
    """
    Shows a monitor selection dialog and returns the chosen monitor, or None if cancelled.
    If only one monitor is in the list, returns it directly without showing a dialog.
    """
    if len(monitors) == 1:
        return monitors[0]

    dialog = _MonitorSelectorDialog(parent, monitors)
    parent.wait_window(dialog.window)
    return dialog.result


def _monitor_for_window(window: tk.Tk, monitors: list) -> object:
    """Returns the monitor that contains the center point of the given window."""
    cx = window.winfo_x() + window.winfo_width() // 2
    cy = window.winfo_y() + window.winfo_height() // 2

    for monitor in monitors:
        within_x = monitor.x <= cx < monitor.x + monitor.width
        within_y = monitor.y <= cy < monitor.y + monitor.height
        if within_x and within_y:
            return monitor

    return monitors[0]


class _MonitorSelectorDialog:
    """Modal dialog for selecting the target display for the player window."""

    def __init__(self, parent: tk.Tk, monitors: list) -> None:
        self.result: Optional[object] = None
        self._monitors = monitors

        self.window = tk.Toplevel(parent)
        self.window.title("Select Player Display")
        self.window.configure(bg=_BG)
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        self._build_ui()
        self.window.update_idletasks()
        self._center_on_parent(parent)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.window, bg=_BG, padx=16, pady=16)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="Choose the display for the Player Window:",
            bg=_BG,
            fg=_INK,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 8))

        list_frame = tk.Frame(
            outer,
            bg=_PANEL,
            highlightthickness=1,
            highlightbackground=_LINE,
        )
        list_frame.pack(fill="both")

        self._listbox = tk.Listbox(
            list_frame,
            bg=_PANEL,
            fg=_INK,
            selectbackground="#1a3a5c",
            selectforeground=_INK,
            font=("Segoe UI", 10),
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            width=44,
            height=min(len(self._monitors), 6),
        )
        self._listbox.pack(fill="both")

        for i, monitor in enumerate(self._monitors):
            entry = f"Display {i + 1}  —  {monitor.width}×{monitor.height}  at ({monitor.x}, {monitor.y})"
            if getattr(monitor, "is_primary", False):
                entry += "  [Primary]"
            self._listbox.insert(tk.END, entry)

        self._listbox.selection_set(0)

        btn_row = tk.Frame(outer, bg=_BG)
        btn_row.pack(fill="x", pady=(12, 0))

        cancel_btn = tk.Button(
            btn_row,
            text="Cancel",
            command=self._on_cancel,
            bg=_PANEL,
            fg=_INK,
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            activebackground=_LINE,
            activeforeground=_INK,
        )
        cancel_btn.pack(side="right", padx=(6, 0))

        open_btn = tk.Button(
            btn_row,
            text="Open Player Window",
            command=self._on_confirm,
            bg=_BUTTON_BG,
            fg=_BUTTON_FG,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            activebackground=_BUTTON_HOVER,
            activeforeground=_BUTTON_FG,
        )
        open_btn.pack(side="right")

        self._listbox.bind("<Double-1>", lambda _: self._on_confirm())
        self.window.bind("<Return>", lambda _: self._on_confirm())
        self.window.bind("<Escape>", lambda _: self._on_cancel())

    def _on_confirm(self) -> None:
        selection = self._listbox.curselection()
        if selection:
            self.result = self._monitors[selection[0]]
        self.window.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        w = self.window.winfo_width()
        h = self.window.winfo_height()
        px = parent.winfo_x() + (parent.winfo_width() - w) // 2
        py = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.window.geometry(f"+{px}+{py}")
