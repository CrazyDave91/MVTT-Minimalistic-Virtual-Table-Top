# This code was created with GitHub Copilot.
# This codebase is released under the MIT License.
# Use at your own risk. Provided "as is", without warranties of any kind.

"""
Application state model and history management for MVTT Battlemap.
All coordinates are in image space (pixels of the loaded image).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

HISTORY_LIMIT = 120
MIN_VIEWPORT_SIZE = 40.0


@dataclass
class Rect:
    """Axis-aligned rectangle in image-space coordinates."""

    x: float
    y: float
    width: float
    height: float


@dataclass
class AppState:
    """Shared render state passed between GM and Player windows."""

    image_width: int = 0
    image_height: int = 0
    viewport: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))
    reveals: list[Rect] = field(default_factory=list)


def create_centered_viewport(
    image_width: int, image_height: int, player_aspect: float
) -> Rect:
    """Returns a viewport centered on the image, sized for the given aspect ratio."""
    max_w = image_width * 0.6
    max_h = image_height * 0.6

    width = max_w
    height = width / player_aspect

    if height > max_h:
        height = max_h
        width = height * player_aspect

    return Rect(
        x=(image_width - width) / 2,
        y=(image_height - height) / 2,
        width=width,
        height=height,
    )


def push_history(history: list[dict], state: AppState) -> None:
    """Saves a snapshot of viewport and reveals to history."""
    history.append(
        {
            "viewport": deepcopy(state.viewport),
            "reveals": deepcopy(state.reveals),
        }
    )
    if len(history) > HISTORY_LIMIT:
        history.pop(0)


def pop_history(history: list[dict], state: AppState) -> bool:
    """Restores the last history snapshot. Returns True if one was available."""
    if not history:
        return False
    snapshot = history.pop()
    state.viewport = snapshot["viewport"]
    state.reveals = snapshot["reveals"]
    return True


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def clamp_viewport(viewport: Rect, image_width: int, image_height: int) -> Rect:
    """Clamps viewport dimensions and position to stay within image boundaries."""
    width = clamp(viewport.width, MIN_VIEWPORT_SIZE, image_width)
    height = clamp(viewport.height, MIN_VIEWPORT_SIZE, image_height)
    x = clamp(viewport.x, 0, image_width - width)
    y = clamp(viewport.y, 0, image_height - height)
    return Rect(x, y, width, height)
