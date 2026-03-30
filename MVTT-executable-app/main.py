# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
MVTT Battlemap — Python desktop application.
Entry point. Creates the GM window and starts the tkinter event loop.
"""
import os
import ctypes

from gm_window import GmWindow
import tkinter as tk


def configure_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return

    # Use the highest available mode first (Per-Monitor V2).
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        # Best effort only. On unsupported systems, Tk keeps default behavior.
        pass


def main() -> None:
    configure_windows_dpi_awareness()
    root = tk.Tk()
    GmWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
