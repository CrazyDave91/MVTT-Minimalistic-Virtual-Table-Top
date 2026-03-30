# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
Generate anti-aliased mouse click icons for the legend.

The icons render a full mouse silhouette and highlight either the left or the
right button. They are drawn at high resolution and then downsampled for
crisper edges in tkinter.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ACCENT = (85, 184, 255, 255)
OUTLINE = (151, 199, 245, 230)
WHEEL = (151, 199, 245, 170)


def _resource_base_dir() -> Path:
  # PyInstaller onefile extracts bundled resources into _MEIPASS at runtime.
  if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    return Path(sys._MEIPASS)
  return Path(__file__).resolve().parent


ASSETS_DIR = _resource_base_dir() / "assets" / "icons"


def _tint_non_transparent_pixels(
  image: Image.Image, tint: tuple[int, int, int, int]
) -> Image.Image:
  tinted = image.convert("RGBA")
  pixels = tinted.load()
  width, height = tinted.size
  for y in range(height):
    for x in range(width):
      _, _, _, alpha = pixels[x, y]
      if alpha > 0:
        pixels[x, y] = (tint[0], tint[1], tint[2], alpha)
  return tinted


def _trim_transparent_bounds(image: Image.Image) -> Image.Image:
  alpha = image.split()[-1]
  bbox = alpha.getbbox()
  if bbox is None:
    return image
  return image.crop(bbox)


def _load_web_icon(filename: str, size: int) -> Image.Image | None:
    file_path = ASSETS_DIR / filename
    if not file_path.exists():
        return None

    image = Image.open(file_path).convert("RGBA")
    image = _trim_transparent_bounds(image)
    image = _tint_non_transparent_pixels(image, ACCENT)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _build_mouse_icon(button: str, size: int = 18) -> Image.Image:
    scale = 4
    w = size * scale
    h = size * scale

    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Mouse body with wider proportions for readability at 18px.
    body = (4 * scale, 2 * scale, 14 * scale, 16 * scale)
    draw.rounded_rectangle(body, radius=5 * scale, outline=OUTLINE, width=scale)

    # Button split and wheel line.
    draw.line(
        [(9 * scale, 2 * scale), (9 * scale, 8 * scale)],
        fill=WHEEL,
        width=scale,
    )
    draw.line(
        [(4 * scale, 8 * scale), (14 * scale, 8 * scale)],
        fill=WHEEL,
        width=scale,
    )

    # Highlight active mouse button.
    if button == "left":
        draw.rounded_rectangle(
            (4 * scale + 1, 2 * scale + 1, 9 * scale - 1, 8 * scale - 1),
            radius=2 * scale,
            fill=ACCENT,
        )
    else:
        draw.rounded_rectangle(
            (9 * scale + 1, 2 * scale + 1, 14 * scale - 1, 8 * scale - 1),
            radius=2 * scale,
            fill=ACCENT,
        )

    return image.resize((size, size), Image.Resampling.LANCZOS)


def left_mouse_icon(size: int = 18) -> Image.Image:
  return _load_web_icon("mouse-left-click-source.png", size=size) or _build_mouse_icon(
    "left", size=size
  )


def right_mouse_icon(size: int = 18) -> Image.Image:
  return _load_web_icon("mouse-right-click-source.png", size=size) or _build_mouse_icon(
    "right", size=size
  )
