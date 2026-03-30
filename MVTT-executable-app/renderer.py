# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
Pillow-based rendering for the GM and Player canvases.
All draw operations produce a PIL.Image that is then displayed via ImageTk.PhotoImage.
"""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from state import AppState, Rect

HANDLE_SIZE = 10

# Attempt to load a system font for canvas placeholder text.
_FONT_PATHS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont

    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def compute_contain_transform(
    canvas_w: int, canvas_h: int, image_w: int, image_h: int
) -> tuple[int, int, int, int]:
    """
    Returns (x, y, draw_w, draw_h) that contain-fits the image inside the canvas,
    preserving aspect ratio with letterboxing.
    """
    image_aspect = image_w / image_h
    draw_w = canvas_w
    draw_h = int(draw_w / image_aspect)

    if draw_h > canvas_h:
        draw_h = canvas_h
        draw_w = int(draw_h * image_aspect)

    x = (canvas_w - draw_w) // 2
    y = (canvas_h - draw_h) // 2
    return x, y, draw_w, draw_h


def intersect_rects(a: Rect, b: Rect) -> Optional[Rect]:
    """Returns the intersection of two rects, or None if they do not overlap."""
    x = max(a.x, b.x)
    y = max(a.y, b.y)
    right = min(a.x + a.width, b.x + b.width)
    bottom = min(a.y + a.height, b.y + b.height)

    if right <= x or bottom <= y:
        return None

    return Rect(x, y, right - x, bottom - y)


def render_gm(
    canvas_w: int,
    canvas_h: int,
    state: AppState,
    image: Optional[Image.Image],
    interaction_preview: Optional[Rect] = None,
    active_handle: Optional[str] = None,
    status_text: str = "",
) -> Image.Image:
    """
    Renders the full GM canvas:
    - Dark background
    - Loaded image with fog overlay
    - Revealed areas shown through fog
    - Viewport rectangle and corner handles
    - Optional reveal-in-progress preview rectangle
    """
    frame = Image.new("RGB", (canvas_w, canvas_h), (18, 18, 18))

    if image is None or state.image_width == 0:
        _draw_centered_text(frame, canvas_w, canvas_h, "Load an image to begin", "#e7e7e7")
        return frame

    tx, ty, tw, th = compute_contain_transform(
        canvas_w, canvas_h, state.image_width, state.image_height
    )
    scaled = image.resize((tw, th), Image.BILINEAR)
    frame.paste(scaled, (tx, ty))

    # Apply 35% opacity fog overlay to the full image area.
    fog = Image.new("RGBA", (tw, th), (0, 0, 0, 89))
    base_crop = frame.crop((tx, ty, tx + tw, ty + th)).convert("RGBA")
    fogged = Image.alpha_composite(base_crop, fog).convert("RGB")
    frame.paste(fogged, (tx, ty))

    # Restore revealed areas through the fog.
    scale_x = tw / state.image_width
    scale_y = th / state.image_height

    for reveal in state.reveals:
        src_x = int(reveal.x * scale_x)
        src_y = int(reveal.y * scale_y)
        src_w = max(1, int(reveal.width * scale_x))
        src_h = max(1, int(reveal.height * scale_y))
        crop = scaled.crop((src_x, src_y, src_x + src_w, src_y + src_h))
        frame.paste(crop, (int(tx + reveal.x * scale_x), int(ty + reveal.y * scale_y)))

    # Draw viewport rectangle.
    vx = int(tx + state.viewport.x * scale_x)
    vy = int(ty + state.viewport.y * scale_y)
    vw = int(state.viewport.width * scale_x)
    vh = int(state.viewport.height * scale_y)

    draw = ImageDraw.Draw(frame)
    draw.rectangle([vx, vy, vx + vw, vy + vh], outline=(255, 47, 47), width=2)

    # Draw corner handles.
    corners = {
        "nw": (vx, vy),
        "ne": (vx + vw, vy),
        "se": (vx + vw, vy + vh),
        "sw": (vx, vy + vh),
    }
    for handle, (hx, hy) in corners.items():
        size = HANDLE_SIZE * 2 if handle == active_handle else HANDLE_SIZE
        half = size // 2
        draw.rectangle([hx - half, hy - half, hx + half, hy + half], fill=(255, 47, 47))

    # Draw reveal-in-progress dashed preview.
    if interaction_preview is not None:
        px = int(tx + interaction_preview.x * scale_x)
        py = int(ty + interaction_preview.y * scale_y)
        pw = int(interaction_preview.width * scale_x)
        ph = int(interaction_preview.height * scale_y)
        draw.rectangle([px, py, px + pw, py + ph], outline=(255, 255, 255), width=1)

    if status_text:
        _draw_centered_text(frame, canvas_w, canvas_h, status_text, "#ff8686")

    return frame


def render_player(
    canvas_w: int,
    canvas_h: int,
    state: AppState,
    image: Optional[Image.Image],
) -> Image.Image:
    """
    Renders the Player canvas:
    - Black background
    - Only revealed portions of the viewport are drawn
    """
    frame = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))

    if image is None or state.image_width == 0 or state.viewport.width == 0:
        _draw_centered_text(frame, canvas_w, canvas_h, "Waiting for GM...", "#e7e7e7")
        return frame

    vp = state.viewport

    for reveal in state.reveals:
        intersect = intersect_rects(reveal, vp)
        if intersect is None:
            continue

        dw = max(1, int(intersect.width / vp.width * canvas_w))
        dh = max(1, int(intersect.height / vp.height * canvas_h))
        dx = int((intersect.x - vp.x) / vp.width * canvas_w)
        dy = int((intersect.y - vp.y) / vp.height * canvas_h)

        crop = image.crop(
            (
                int(intersect.x),
                int(intersect.y),
                int(intersect.x + intersect.width),
                int(intersect.y + intersect.height),
            )
        )
        crop = crop.resize((dw, dh), Image.BILINEAR)
        frame.paste(crop, (dx, dy))

    return frame


def _draw_centered_text(
    frame: Image.Image, w: int, h: int, text: str, color: str
) -> None:
    """Draws centered text with a semi-transparent dark background box."""
    draw = ImageDraw.Draw(frame)
    font = _load_font(18)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    padding = 16

    bx = (w - tw) // 2 - padding
    by = (h - th) // 2 - padding
    draw.rectangle(
        [bx, by, bx + tw + padding * 2, by + th + padding * 2],
        fill=(0, 0, 0),
    )
    draw.text(((w - tw) // 2, (h - th) // 2), text, fill=color, font=font)
