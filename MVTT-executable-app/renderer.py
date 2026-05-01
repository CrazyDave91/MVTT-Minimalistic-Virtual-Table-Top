# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
Pillow-based rendering for the GM and Player canvases.
All draw operations produce a PIL.Image that is then displayed via ImageTk.PhotoImage.
"""
from __future__ import annotations

import math
from typing import Optional

from PIL import Image, ImageDraw

from state import AppState, Rect

HANDLE_SIZE = 10
IMAGE_HANDLE_COLOR = (74, 170, 255)
IMAGE_HANDLE_ACTIVE_COLOR = (110, 193, 255)

_scaled_render_cache: dict[tuple[int, int, int], Image.Image] = {}

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


def _draw_grid_on_viewport(
    frame: Image.Image,
    vx: int,
    vy: int,
    vw: int,
    vh: int,
    monitor_inches: float,
    player_aspect: float,
) -> None:
    """Composites a 1-inch grid overlay onto the viewport area of the frame."""
    if monitor_inches <= 0 or vw <= 0 or vh <= 0 or player_aspect <= 0:
        return

    sqrt_term = math.sqrt(player_aspect ** 2 + 1)
    cell_w = vw * sqrt_term / (monitor_inches * player_aspect)
    cell_h = vh * sqrt_term / monitor_inches

    if cell_w < 2 or cell_h < 2:
        return

    overlay = Image.new("RGBA", (vw, vh), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(overlay)

    x = 0.0
    while x <= vw:
        xi = round(x)
        grid_draw.line([(xi, 0), (xi, vh)], fill=(255, 255, 255, 64), width=1)
        x += cell_w

    y = 0.0
    while y <= vh:
        yi = round(y)
        grid_draw.line([(0, yi), (vw, yi)], fill=(255, 255, 255, 64), width=1)
        y += cell_h

    crop = frame.crop((vx, vy, vx + vw, vy + vh)).convert("RGBA")
    composited = Image.alpha_composite(crop, overlay).convert("RGB")
    frame.paste(composited, (vx, vy))


def render_gm(
    canvas_w: int,
    canvas_h: int,
    state: AppState,
    image: Optional[Image.Image],
    interaction_preview: Optional[Rect] = None,
    active_handle: Optional[str] = None,
    status_text: str = "",
    grid_monitor_inches: float = 0.0,
    player_aspect: float = 16 / 9,
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

    fx, fy, fw, fh = compute_scaled_frame(tx, ty, tw, th, state.image_scale)
    scaled = get_scaled_render_image(image, fw, fh)
    frame.paste(scaled, (fx, fy))

    # Apply 65% opacity fog overlay to the full image area.
    fog = Image.new("RGBA", (fw, fh), (0, 0, 0, 166))
    base_crop = frame.crop((fx, fy, fx + fw, fy + fh)).convert("RGBA")
    fogged = Image.alpha_composite(base_crop, fog).convert("RGB")
    frame.paste(fogged, (fx, fy))

    # Restore revealed areas through the fog.
    scale_x = fw / state.image_width
    scale_y = fh / state.image_height

    for reveal in state.reveals:
        src_x = int(reveal.x * scale_x)
        src_y = int(reveal.y * scale_y)
        src_w = max(1, int(reveal.width * scale_x))
        src_h = max(1, int(reveal.height * scale_y))
        crop = scaled.crop((src_x, src_y, src_x + src_w, src_y + src_h))
        frame.paste(crop, (int(fx + reveal.x * scale_x), int(fy + reveal.y * scale_y)))

    # Draw viewport rectangle.
    vx = int(fx + state.viewport.x * scale_x)
    vy = int(fy + state.viewport.y * scale_y)
    vw = int(state.viewport.width * scale_x)
    vh = int(state.viewport.height * scale_y)

    draw = ImageDraw.Draw(frame)
    draw.rectangle([vx, vy, vx + vw, vy + vh], outline=(255, 47, 47), width=2)

    # Draw 1-inch grid overlay inside the viewport when a monitor size is selected.
    _draw_grid_on_viewport(frame, vx, vy, vw, vh, grid_monitor_inches, player_aspect)

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

    # Draw image corner handles (separate from viewport handles).
    image_corners = {
        "image-nw": (fx, fy),
        "image-ne": (fx + fw, fy),
        "image-se": (fx + fw, fy + fh),
        "image-sw": (fx, fy + fh),
    }
    for handle, (hx, hy) in image_corners.items():
        is_active = handle == active_handle
        size = HANDLE_SIZE * 2 if is_active else HANDLE_SIZE
        half = size // 2
        color = IMAGE_HANDLE_ACTIVE_COLOR if is_active else IMAGE_HANDLE_COLOR
        draw.rectangle([hx - half, hy - half, hx + half, hy + half], fill=color)

    # Draw reveal-in-progress dashed preview.
    if interaction_preview is not None:
        px = int(fx + interaction_preview.x * scale_x)
        py = int(fy + interaction_preview.y * scale_y)
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
    if vp.width <= 0 or vp.height <= 0:
        return frame

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


def compute_scaled_frame(
    tx: int, ty: int, tw: int, th: int, image_scale: float
) -> tuple[int, int, int, int]:
    """Returns centered scaled frame based on contain transform and image_scale."""
    draw_w = max(1, int(tw * image_scale))
    draw_h = max(1, int(th * image_scale))
    draw_x = int(tx + (tw - draw_w) / 2)
    draw_y = int(ty + (th - draw_h) / 2)
    return draw_x, draw_y, draw_w, draw_h


def get_scaled_render_image(image: Image.Image, width: int, height: int) -> Image.Image:
    """Returns a cached scaled image for the target render size."""
    key = (id(image), width, height)
    cached = _scaled_render_cache.get(key)
    if cached is not None:
        return cached

    resized = image.resize((width, height), Image.BILINEAR)
    _scaled_render_cache[key] = resized

    if len(_scaled_render_cache) > 12:
        _scaled_render_cache.pop(next(iter(_scaled_render_cache)))

    return resized


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
