# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
Player window — opens borderless on the selected monitor and fills it completely.
Receives state updates from GmWindow via refresh().
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from PIL import Image, ImageTk

from renderer import render_player
from state import AppState


class PlayerWindow:
    """Borderless window that renders the player's view on the selected monitor."""

    def __init__(
        self,
        parent: tk.Tk,
        state: AppState,
        image: Optional[Image.Image],
        monitor,
    ) -> None:
        self._state = state
        self._image = image
        self._photo: Optional[ImageTk.PhotoImage] = None
        self.closed = False

        self._window = tk.Toplevel(parent)
        self._window.title("MVTT — Player View")
        self._window.configure(bg="#000000")
        # Remove OS title bar and place precisely on the target monitor.
        self._window.overrideredirect(True)
        self._window.geometry(
            f"{monitor.width}x{monitor.height}+{monitor.x}+{monitor.y}"
        )

        self._canvas = tk.Canvas(
            self._window, bg="#000000", highlightthickness=0, cursor="none"
        )
        self._canvas.pack(fill="both", expand=True)

        self._window.bind("<Escape>", lambda _: self.destroy())
        self._window.bind("<Configure>", lambda _: self._schedule_render())
        self._window.protocol("WM_DELETE_WINDOW", self.destroy)

        self._window.lift()
        self._window.focus_force()

    def refresh(self, state: AppState, image: Optional[Image.Image]) -> None:
        """Called by GmWindow when state or image changes."""
        self._state = state
        self._image = image
        self._schedule_render()

    def destroy(self) -> None:
        """Closes the player window."""
        self.closed = True
        self._window.destroy()

    def _schedule_render(self) -> None:
        """Defers render to allow the canvas to settle its dimensions first."""
        self._window.after(0, self._render)

    def _render(self) -> None:
        if self.closed:
            return

        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()

        # Canvas dimensions may not be available immediately after creation.
        if w < 2 or h < 2:
            self._window.after(50, self._render)
            return

        frame = render_player(w, h, self._state, self._image)
        self._photo = ImageTk.PhotoImage(frame)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
