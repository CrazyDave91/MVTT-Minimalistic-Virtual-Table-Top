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
_MIN_IMAGE_SCALE = 0.2
_MAX_IMAGE_SCALE = 3.0

_GRID_OPTIONS = [
    "off",
    '13,3" (33,8 cm)',
    '15,6" (39,6 cm)',
    '17,3" (43,9 cm)',
    '21,5" (54,6 cm)',
    '23,8" (60,5 cm)',
    '24" (61,0 cm)',
    '27" (68,6 cm)',
    '28" (71,1 cm)',
    '31,5" (80,0 cm)',
    '32" (81,3 cm)',
    '34" (86,4 cm)',
    '35" (88,9 cm)',
    '38" (96,5 cm)',
    '40" (101,6 cm)',
    '42" (106,7 cm)',
    '43" (109,2 cm)',
    '45" (114,3 cm)',
    '48" (121,9 cm)',
    '49" (124,5 cm)',
    '50" (127,0 cm)',
    '55" (139,7 cm)',
    '58" (147,3 cm)',
    '60" (152,4 cm)',
    '65" (165,1 cm)',
]

_GRID_INCHES: dict[str, float] = {
    "off": 0.0,
    '13,3" (33,8 cm)': 13.3,
    '15,6" (39,6 cm)': 15.6,
    '17,3" (43,9 cm)': 17.3,
    '21,5" (54,6 cm)': 21.5,
    '23,8" (60,5 cm)': 23.8,
    '24" (61,0 cm)': 24.0,
    '27" (68,6 cm)': 27.0,
    '28" (71,1 cm)': 28.0,
    '31,5" (80,0 cm)': 31.5,
    '32" (81,3 cm)': 32.0,
    '34" (86,4 cm)': 34.0,
    '35" (88,9 cm)': 35.0,
    '38" (96,5 cm)': 38.0,
    '40" (101,6 cm)': 40.0,
    '42" (106,7 cm)': 42.0,
    '43" (109,2 cm)': 43.0,
    '45" (114,3 cm)': 45.0,
    '48" (121,9 cm)': 48.0,
    '49" (124,5 cm)': 49.0,
    '50" (127,0 cm)': 50.0,
    '55" (139,7 cm)': 55.0,
    '58" (147,3 cm)': 58.0,
    '60" (152,4 cm)': 60.0,
    '65" (165,1 cm)': 65.0,
}


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
        self._grid_monitor_inches: float = 0.0
        self._grid_var: Optional[tk.StringVar] = None

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

        # Grid overlay dropdown — label and menu share one button-styled container
        self._grid_var = tk.StringVar(value="off")
        self._grid_var.trace_add("write", self._on_grid_change)

        grid_frame = tk.Frame(
            toolbar,
            bg=_BUTTON_BG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=_LINE,
            bd=0,
        )
        grid_frame.pack(side="left", padx=(6, 3), pady=4)

        tk.Label(
            grid_frame,
            text="Grid",
            bg=_BUTTON_BG,
            fg=_BUTTON_FG,
            font=("Segoe UI", 9, "bold"),
            padx=6,
            pady=3,
            cursor="hand2",
        ).pack(side="left")

        grid_menu = tk.OptionMenu(grid_frame, self._grid_var, *_GRID_OPTIONS)
        grid_menu.configure(
            bg=_BUTTON_BG,
            fg=_BUTTON_FG,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            activebackground=_BUTTON_HOVER,
            activeforeground=_BUTTON_FG,
            highlightthickness=0,
            cursor="hand2",
            padx=4,
            pady=3,
            bd=0,
        )
        grid_menu["menu"].configure(
            bg=_BUTTON_BG,
            fg=_BUTTON_FG,
            font=("Segoe UI", 9, "bold"),
            activebackground=_BUTTON_FG,
            activeforeground=_INK,
        )
        grid_menu.pack(side="left")

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
        self._state.image_scale = 1.0
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

        self._state.viewport = _rotate_rect_clockwise(
            self._state.viewport,
            old_w,
            old_h,
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

    def _on_grid_change(self, *_) -> None:
        if self._grid_var is None:
            return
        selected = self._grid_var.get()
        self._grid_monitor_inches = _GRID_INCHES.get(selected, 0.0)
        self._render_gm()

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

        push_history(self._history, self._state)

        if hit.startswith("image-"):
            image_frame = self._scaled_image_frame()
            if image_frame is None:
                return
            self._interaction = {
                "type": "image-scale",
                "handle": hit,
                "anchor": _anchor_for_handle(
                    Rect(image_frame[0], image_frame[1], image_frame[2], image_frame[3]),
                    hit,
                ),
            }
            self._canvas.configure(cursor=_cursor_for_hit(hit))
            return

        img_pt = self._to_image_coords(event.x, event.y)
        if img_pt is None:
            return

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
            self._state.viewport = new_vp

        elif self._interaction["type"] == "resize":
            self._state.viewport = _resize_viewport_fixed_aspect(
                self._interaction,
                img_pt,
                self._player_aspect,
            )

        elif self._interaction["type"] == "image-scale":
            self._state.image_scale = _compute_image_scale_from_pointer(
                self._interaction,
                (event.x, event.y),
                self._transform,
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

        image_handle = self._image_hit_type(canvas_x, canvas_y)
        if image_handle != "none":
            return image_handle

        frame = self._scaled_image_frame()
        if frame is None:
            return "none"

        tx, ty, tw, th = frame
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
        frame = self._scaled_image_frame()
        if frame is None:
            return None

        tx, ty, tw, th = frame

        nx = (canvas_x - tx) / tw
        ny = (canvas_y - ty) / th
        return nx * self._state.image_width, ny * self._state.image_height

    def _scaled_image_frame(self) -> Optional[tuple[int, int, int, int]]:
        if self._transform is None:
            return None
        tx, ty, tw, th = self._transform
        draw_w = max(1, int(tw * self._state.image_scale))
        draw_h = max(1, int(th * self._state.image_scale))
        draw_x = int(tx + (tw - draw_w) / 2)
        draw_y = int(ty + (th - draw_h) / 2)
        return draw_x, draw_y, draw_w, draw_h

    def _image_hit_type(self, canvas_x: int, canvas_y: int) -> str:
        frame = self._scaled_image_frame()
        if frame is None:
            return "none"

        fx, fy, fw, fh = frame
        corners = {
            "image-nw": (fx, fy),
            "image-ne": (fx + fw, fy),
            "image-se": (fx + fw, fy + fh),
            "image-sw": (fx, fy + fh),
        }
        for handle, (hx, hy) in corners.items():
            if abs(canvas_x - hx) <= HANDLE_SIZE and abs(canvas_y - hy) <= HANDLE_SIZE:
                return handle
        return "none"

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
            active_handle=(
                self._interaction.get("handle")
                if self._interaction and "handle" in self._interaction
                else self._hover_handle
            ),
            status_text=self._status_text,
            grid_monitor_inches=self._grid_monitor_inches,
            player_aspect=self._player_aspect,
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
        "image-nw": "top_left_corner",
        "image-se": "bottom_right_corner",
        "image-ne": "top_right_corner",
        "image-sw": "bottom_left_corner",
    }.get(hit, "arrow")


def _anchor_for_handle(viewport: Rect, handle: str) -> tuple[float, float]:
    return {
        "nw": (viewport.x + viewport.width, viewport.y + viewport.height),
        "ne": (viewport.x, viewport.y + viewport.height),
        "se": (viewport.x, viewport.y),
        "sw": (viewport.x + viewport.width, viewport.y),
        "image-nw": (viewport.x + viewport.width, viewport.y + viewport.height),
        "image-ne": (viewport.x, viewport.y + viewport.height),
        "image-se": (viewport.x, viewport.y),
        "image-sw": (viewport.x + viewport.width, viewport.y),
    }[handle]


def _resize_viewport_fixed_aspect(
    interaction: dict,
    pointer: tuple[float, float],
    ratio: float,
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

    return new_vp


def _compute_image_scale_from_pointer(
    interaction: dict,
    canvas_point: tuple[int, int],
    contain_transform: tuple[int, int, int, int],
) -> float:
    """Computes a clamped image scale from dragged image corner in canvas-space."""
    _, _, base_w, base_h = contain_transform
    aspect = base_w / base_h
    anchor_x, anchor_y = interaction["anchor"]
    pointer_x, pointer_y = canvas_point
    handle = interaction["handle"]

    width_delta = anchor_x - pointer_x if handle in ("image-nw", "image-sw") else pointer_x - anchor_x
    height_delta = anchor_y - pointer_y if handle in ("image-nw", "image-ne") else pointer_y - anchor_y

    proposed_w = max(abs(width_delta), abs(height_delta) * aspect)
    scale = proposed_w / max(1, base_w)
    return max(_MIN_IMAGE_SCALE, min(_MAX_IMAGE_SCALE, scale))


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
