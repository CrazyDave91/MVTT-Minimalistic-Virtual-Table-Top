# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
GM window — main application window with toolbar, canvas, and interaction logic.

Interaction model (mirrors battlemap-local-app/app.js):
  Left-click drag on viewport interior  → move viewport
  Left-click drag on viewport corner    → resize viewport (fixed aspect ratio)
  Right-click drag                       → draw a new reveal rectangle
"""
from __future__ import annotations

import tkinter as tk
import time
from tkinter import filedialog, messagebox
from typing import Optional

from PIL import Image, ImageTk

from icons import left_mouse_icon, right_mouse_icon
from monitor_dialog import get_available_monitors, show_monitor_selector
from player_window import PlayerWindow
from renderer import HANDLE_SIZE, compute_contain_transform, render_gm
from state import (
    AppState,
    MIN_VIEWPORT_SIZE,
    Rect,
    clamp_viewport,
    create_centered_viewport,
    pop_history,
    push_history,
)

# Color palette — mirrors battlemap-local-app/styles.css design tokens.
_BG = "#0c1117"
_PANEL = "#101722"
_INK = "#e7edf8"
_MUTED = "#98a8bf"
_LINE = "#27364a"
_BUTTON_BG = "#d9ecff"
_BUTTON_FG = "#102033"
_BUTTON_HOVER = "#f2f9ff"

_WINDOW_MIN_WIDTH = 900
_WINDOW_MIN_HEIGHT = 600
_DEFAULT_PLAYER_ASPECT = 16 / 9


class GmWindow:
    """Main GM window: toolbar controls and interactive battlemap canvas."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._state = AppState()
        self._image: Optional[Image.Image] = None
        self._history: list[dict] = []
        self._player_window: Optional[PlayerWindow] = None
        self._photo: Optional[ImageTk.PhotoImage] = None

        # Cached contain-transform result, updated on every render.
        self._transform: Optional[tuple[int, int, int, int]] = None

        # Active mouse interaction state.
        self._interaction: Optional[dict] = None
        self._reveal_start: Optional[tuple[float, float]] = None
        self._reveal_current: Optional[tuple[float, float]] = None
        self._hover_handle: str = "none"

        # Throttle rendering and player sync during drag interactions.
        self._last_render_time: float = 0.0
        self._last_player_sync_time: float = 0.0
        self._initial_geom: str = ""  # GM window geometry before player opens
        self._initial_scaling: float = 1.0

        self._player_aspect: float = _DEFAULT_PLAYER_ASPECT
        self._status_text: str = ""

        self._build_window()
        self._build_toolbar()
        self._build_canvas()
        self._render_gm()

    # -------------------------------------------------------------------------
    # Window and widget setup
    # -------------------------------------------------------------------------

    def _build_window(self) -> None:
        self._root.title("MVTT Battlemap — GM")
        self._root.configure(bg=_BG)
        self._root.minsize(_WINDOW_MIN_WIDTH, _WINDOW_MIN_HEIGHT)
        self._root.geometry("1280x720")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Keep a stable baseline for Tk logical scaling (DPI handling).
        self._root.update_idletasks()
        self._initial_scaling = float(self._root.tk.call("tk", "scaling"))

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self._root, bg=_PANEL, pady=6, padx=8)
        toolbar.pack(side="top", fill="x")

        tk.Label(
            toolbar, text="MVTT", bg=_PANEL, fg=_INK, font=("Segoe UI", 10, "bold")
        ).pack(side="left", padx=(0, 12))

        self._make_button(toolbar, "Load Image", self._on_load_image).pack(
            side="left", padx=3
        )
        self._make_button(toolbar, "Open Player Window", self._on_open_player).pack(
            side="left", padx=3
        )
        self._make_button(toolbar, "Rotate", self._on_rotate).pack(
            side="left", padx=3
        )
        self._make_button(toolbar, "Revert Last", self._on_undo).pack(
            side="left", padx=3
        )
        self._make_button(toolbar, "Reset Fog", self._on_reset_fog).pack(
            side="left", padx=3
        )

        # Legend with mouse button icons
        self._lmb_photo = ImageTk.PhotoImage(left_mouse_icon(size=18))
        self._rmb_photo = ImageTk.PhotoImage(right_mouse_icon(size=18))

        legend_frame = tk.Frame(toolbar, bg=_PANEL)
        legend_frame.pack(side="right", padx=4)

        tk.Label(legend_frame, image=self._lmb_photo, bg=_PANEL).pack(
            side="left", padx=2
        )
        tk.Label(
            legend_frame,
            text="move / scale",
            bg=_PANEL,
            fg=_MUTED,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=2)

        tk.Label(legend_frame, text="|", bg=_PANEL, fg=_MUTED, font=("Segoe UI", 10)).pack(
            side="left", padx=2
        )

        tk.Label(legend_frame, image=self._rmb_photo, bg=_PANEL).pack(
            side="left", padx=2
        )
        tk.Label(
            legend_frame,
            text="reveal",
            bg=_PANEL,
            fg=_MUTED,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=2)

    def _make_button(self, parent: tk.Frame, text: str, command) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=_BUTTON_BG,
            fg=_BUTTON_FG,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            activebackground=_BUTTON_HOVER,
            activeforeground=_BUTTON_FG,
        )
        btn.bind("<Enter>", lambda _: btn.configure(bg=_BUTTON_HOVER))
        btn.bind("<Leave>", lambda _: btn.configure(bg=_BUTTON_BG))
        return btn

    def _build_canvas(self) -> None:
        frame = tk.Frame(
            self._root,
            bg="#090f17",
            highlightthickness=1,
            highlightbackground=_LINE,
        )
        frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self._canvas = tk.Canvas(frame, bg="#090f17", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<Button-1>", self._on_left_down)
        self._canvas.bind("<Button-3>", self._on_right_down)
        self._canvas.bind("<B1-Motion>", self._on_left_drag)
        self._canvas.bind("<B3-Motion>", self._on_right_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_left_up)
        self._canvas.bind("<ButtonRelease-3>", self._on_right_up)
        self._canvas.bind("<Motion>", self._on_hover)
        self._canvas.bind("<Configure>", lambda _: self._render_gm())

    # -------------------------------------------------------------------------
    # Toolbar button handlers
    # -------------------------------------------------------------------------

    def _on_close(self) -> None:
        if self._player_window and not self._player_window.closed:
            self._player_window.destroy()
        self._root.destroy()

    def _on_load_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Battlemap Image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            img = Image.open(path).convert("RGB")
        except (IOError, OSError) as exc:
            messagebox.showerror("Load Error", f"Could not open image:\n{exc}")
            return

        push_history(self._history, self._state)
        self._image = img
        self._state.image_width = img.width
        self._state.image_height = img.height
        self._state.reveals = []
        self._state.viewport = create_centered_viewport(
            img.width, img.height, self._player_aspect
        )
        self._status_text = ""
        self._render_gm()
        self._sync_player()

    def _on_open_player(self) -> None:
        """
        Opens the player window on a user-selected monitor.
        The GM window's current monitor is excluded from the selection.
        Shows an info message if no second monitor is available.
        """
        # Preserve GM geometry and Tk scaling before opening any additional window.
        self._initial_geom = self._root.geometry()
        self._initial_scaling = float(self._root.tk.call("tk", "scaling"))

        available = get_available_monitors(self._root)

        if not available:
            messagebox.showinfo(
                "No Second Monitor",
                "No second monitor detected.\n\n"
                "Connect a second display and try again.",
            )
            return

        # Destroy existing player window before opening a new one.
        if self._player_window and not self._player_window.closed:
            self._player_window.destroy()

        chosen = show_monitor_selector(self._root, available)
        if chosen is None:
            return

        self._player_window = PlayerWindow(
            self._root, self._state, self._image, chosen
        )

        # Restore GM geometry and scaling to avoid unwanted resize/reflow.
        self._root.after(120, self._restore_gm_window_metrics)

    def _restore_gm_window_metrics(self) -> None:
        self._root.tk.call("tk", "scaling", self._initial_scaling)
        self._root.geometry(self._initial_geom)
        self._root.update_idletasks()
        self._render_gm()

    def _on_rotate(self) -> None:
        if self._image is None:
            return

        push_history(self._history, self._state)

        old_w = self._state.image_width
        old_h = self._state.image_height

        # ROTATE_270 in PIL = 90° clockwise, matching the JS canvas rotation.
        rotated = self._image.transpose(Image.ROTATE_270)
        self._image = rotated
        self._state.image_width = rotated.width
        self._state.image_height = rotated.height

        # Viewport is a display specification (player aspect), not an image region.
        # After rotation, recenter the viewport without rotating it.
        # Preserve the current player aspect ratio.
        self._state.viewport = create_centered_viewport(
            rotated.width,
            rotated.height,
            self._player_aspect,
        )

        # Reveals must be rotated with the image (they are marked on the battlemap).
        self._state.reveals = [
            _rotate_rect_clockwise(r, old_w, old_h) for r in self._state.reveals
        ]

        self._render_gm()
        self._sync_player()

    def _on_undo(self) -> None:
        if pop_history(self._history, self._state):
            self._render_gm()
            self._sync_player()

    def _on_reset_fog(self) -> None:
        if not self._state.reveals:
            return
        push_history(self._history, self._state)
        self._state.reveals = []
        self._render_gm()
        self._sync_player()

    # -------------------------------------------------------------------------
    # Mouse interaction handlers
    # -------------------------------------------------------------------------

    def _on_hover(self, event: tk.Event) -> None:
        if self._image is None or self._transform is None:
            self._canvas.configure(cursor="arrow")
            return

        hit = self._hit_type(event.x, event.y)
        if hit != self._hover_handle:
            self._hover_handle = hit
            self._render_gm()

        self._canvas.configure(cursor=_cursor_for_hit(hit))

    def _on_left_down(self, event: tk.Event) -> None:
        if self._image is None or self._transform is None:
            return

        hit = self._hit_type(event.x, event.y)
        if hit == "none":
            return

        img_pt = self._to_image_coords(event.x, event.y)
        if img_pt is None:
            return

        push_history(self._history, self._state)

        if hit == "move":
            self._interaction = {
                "type": "move",
                "offset_x": img_pt[0] - self._state.viewport.x,
                "offset_y": img_pt[1] - self._state.viewport.y,
            }
        else:
            self._interaction = {
                "type": "resize",
                "handle": hit,
                "anchor": _anchor_for_handle(self._state.viewport, hit),
            }

        self._canvas.configure(cursor=_cursor_for_hit(hit))

    def _on_right_down(self, event: tk.Event) -> None:
        if self._image is None or self._transform is None:
            return
        img_pt = self._to_image_coords(event.x, event.y)
        if img_pt is None:
            return
        self._reveal_start = img_pt
        self._reveal_current = img_pt
        self._canvas.configure(cursor="crosshair")

    def _on_left_drag(self, event: tk.Event) -> None:
        if self._interaction is None or self._transform is None:
            return

        img_pt = self._to_image_coords(event.x, event.y)
        if img_pt is None:
            return

        if self._interaction["type"] == "move":
            new_vp = Rect(
                img_pt[0] - self._interaction["offset_x"],
                img_pt[1] - self._interaction["offset_y"],
                self._state.viewport.width,
                self._state.viewport.height,
            )
            self._state.viewport = clamp_viewport(
                new_vp, self._state.image_width, self._state.image_height
            )

        elif self._interaction["type"] == "resize":
            self._state.viewport = _resize_viewport_fixed_aspect(
                self._interaction,
                img_pt,
                self._player_aspect,
                self._state.image_width,
                self._state.image_height,
            )

        self._canvas.configure(
            cursor=_cursor_for_hit(self._interaction.get("handle", "move"))
        )

        # Throttle GM canvas render: max ~30 FPS during drag (smooth, no jank)
        now = time.perf_counter()
        if now - self._last_render_time >= 0.033:  # ~30 FPS
            self._render_gm()
            self._last_render_time = now

        # Throttle player sync: min 2 FPS (500ms) during drag
        if now - self._last_player_sync_time >= 0.5:
            self._sync_player()
            self._last_player_sync_time = now

    def _on_right_drag(self, event: tk.Event) -> None:
        if self._reveal_start is None or self._transform is None:
            return
        img_pt = self._to_image_coords(event.x, event.y)
        if img_pt is not None:
            self._reveal_current = img_pt

        # Throttle render: max ~30 FPS during drag
        now = time.perf_counter()
        if now - self._last_render_time >= 0.033:
            self._render_gm()
            self._last_render_time = now

    def _on_left_up(self, _: tk.Event) -> None:
        self._interaction = None
        self._render_gm()
        self._sync_player()
        self._canvas.configure(cursor=_cursor_for_hit(self._hover_handle))

    def _on_right_up(self, _: tk.Event) -> None:
        if self._reveal_start and self._reveal_current:
            rect = _rect_from_points(self._reveal_start, self._reveal_current)
            if rect.width >= 2 and rect.height >= 2:
                push_history(self._history, self._state)
                self._state.reveals.append(rect)

        self._reveal_start = None
        self._reveal_current = None
        self._canvas.configure(cursor="arrow")
        self._render_gm()
        self._sync_player()

    # -------------------------------------------------------------------------
    # Coordinate helpers
    # -------------------------------------------------------------------------

    def _hit_type(self, canvas_x: int, canvas_y: int) -> str:
        """Returns the interaction zone at the given canvas coordinates."""
        if self._transform is None:
            return "none"

        tx, ty, tw, th = self._transform
        scale_x = tw / self._state.image_width
        scale_y = th / self._state.image_height
        vp = self._state.viewport

        vx = int(tx + vp.x * scale_x)
        vy = int(ty + vp.y * scale_y)
        vw = int(vp.width * scale_x)
        vh = int(vp.height * scale_y)

        corners = {
            "nw": (vx, vy),
            "ne": (vx + vw, vy),
            "se": (vx + vw, vy + vh),
            "sw": (vx, vy + vh),
        }
        for handle, (hx, hy) in corners.items():
            if abs(canvas_x - hx) <= HANDLE_SIZE and abs(canvas_y - hy) <= HANDLE_SIZE:
                return handle

        within = vx <= canvas_x <= vx + vw and vy <= canvas_y <= vy + vh
        return "move" if within else "none"

    def _to_image_coords(
        self, canvas_x: int, canvas_y: int
    ) -> Optional[tuple[float, float]]:
        """Converts canvas pixel position to image-space coordinates."""
        if self._transform is None:
            return None

        tx, ty, tw, th = self._transform
        if not (tx <= canvas_x <= tx + tw and ty <= canvas_y <= ty + th):
            return None

        nx = (canvas_x - tx) / tw
        ny = (canvas_y - ty) / th
        return nx * self._state.image_width, ny * self._state.image_height

    # -------------------------------------------------------------------------
    # Rendering and player sync
    # -------------------------------------------------------------------------

    def _render_gm(self) -> None:
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 2 or h < 2:
            return

        self._transform = (
            compute_contain_transform(
                w, h, self._state.image_width, self._state.image_height
            )
            if self._image is not None
            else None
        )

        preview = (
            _rect_from_points(self._reveal_start, self._reveal_current)
            if self._reveal_start and self._reveal_current
            else None
        )

        frame = render_gm(
            w,
            h,
            self._state,
            self._image,
            interaction_preview=preview,
            active_handle=self._hover_handle,
            status_text=self._status_text,
        )

        # Store reference to prevent garbage collection by the Python runtime.
        self._photo = ImageTk.PhotoImage(frame)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)

    def _sync_player(self) -> None:
        """Pushes current state and image to the player window, if open."""
        if self._player_window and not self._player_window.closed:
            self._player_window.refresh(self._state, self._image)


# -------------------------------------------------------------------------
# Pure helper functions
# -------------------------------------------------------------------------


def _cursor_for_hit(hit: str) -> str:
    return {
        "move": "fleur",
        "nw": "top_left_corner",
        "se": "bottom_right_corner",
        "ne": "top_right_corner",
        "sw": "bottom_left_corner",
    }.get(hit, "arrow")


def _anchor_for_handle(viewport: Rect, handle: str) -> tuple[float, float]:
    return {
        "nw": (viewport.x + viewport.width, viewport.y + viewport.height),
        "ne": (viewport.x, viewport.y + viewport.height),
        "se": (viewport.x, viewport.y),
        "sw": (viewport.x + viewport.width, viewport.y),
    }[handle]


def _resize_viewport_fixed_aspect(
    interaction: dict,
    pointer: tuple[float, float],
    ratio: float,
    img_w: int,
    img_h: int,
) -> Rect:
    """Resizes the viewport from the given corner handle, keeping aspect ratio fixed."""
    anchor = interaction["anchor"]
    handle = interaction["handle"]
    px, py = pointer

    width_delta = anchor[0] - px if handle in ("nw", "sw") else px - anchor[0]
    height_delta = anchor[1] - py if handle in ("nw", "ne") else py - anchor[1]

    # Enforce minimum size and fixed aspect ratio.
    proposed_w = max(
        MIN_VIEWPORT_SIZE, max(abs(width_delta), abs(height_delta) * ratio)
    )
    proposed_h = proposed_w / ratio

    if handle == "nw":
        new_vp = Rect(anchor[0] - proposed_w, anchor[1] - proposed_h, proposed_w, proposed_h)
    elif handle == "ne":
        new_vp = Rect(anchor[0], anchor[1] - proposed_h, proposed_w, proposed_h)
    elif handle == "se":
        new_vp = Rect(anchor[0], anchor[1], proposed_w, proposed_h)
    else:  # sw
        new_vp = Rect(anchor[0] - proposed_w, anchor[1], proposed_w, proposed_h)

    return clamp_viewport(new_vp, img_w, img_h)


def _rotate_rect_clockwise(rect: Rect, source_w: int, source_h: int) -> Rect:
    """Transforms a rect's coordinates after a 90° clockwise image rotation."""
    return Rect(
        x=source_h - (rect.y + rect.height),
        y=rect.x,
        width=rect.height,
        height=rect.width,
    )


def _rect_from_points(
    a: tuple[float, float], b: tuple[float, float]
) -> Rect:
    return Rect(
        x=min(a[0], b[0]),
        y=min(a[1], b[1]),
        width=abs(a[0] - b[0]),
        height=abs(a[1] - b[1]),
    )
