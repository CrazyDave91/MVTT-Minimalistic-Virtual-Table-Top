<!--
This code was created with GitHub Copilot.
This codebase is released under the MIT License.
Use at your own risk. Provided "as is", without warranties of any kind.
-->

# MVTT Local Battlemap App

A local, no-install browser application for dual-screen tabletop sessions.

## Goal

- GM runs the control view on a laptop.
- Player view runs on a TV screen (second display).
- Everything works with browser-only resources.

## Setup

1. Open `battlemap-local-app/index.html` in a modern browser.
2. In GM view, click **Open or Focus Player Window**.
3. Move the player window to the TV and double click inside the player window to enter fullscreen.

Note:
- The app is configured to run directly via `file://` (double-click or open file in browser) without module tooling.
- All menu and legend icons are bundled locally in `battlemap-local-app/icons/` for offline standalone use.

## GM Controls

- **Load image**: load map image from local disk.
- **Left drag center of red box**: move viewport.
- **Left drag corners of red box**: resize viewport, ratio preserved.
- **Right drag**: create reveal rectangle in fog.
- **Undo Last Action**: reverts last viewport/fog action.
- **Reset Fog To Start**: keeps image and viewport, removes all reveals.

Aspect ratio behavior:
- The red viewport ratio is synchronized automatically from the player window size.
- Manual ratio input is not required.

## Synchronization

- State is synchronized through `BroadcastChannel` where available.
- Fallback uses `localStorage` and periodic sync.
- GM sends updates at least once per second.

## Browser Notes

- Popup blocking can prevent opening the player window.
- Fullscreen activation can require a direct click inside the player window.
- Recommended browsers: latest Chrome, Edge, or Firefox.

## Troubleshooting

- GM canvas stays black after image load:
	- Check status box message in GM window.
	- Retry with a smaller image.
	- Verify file is a valid image format.
- Player window does not open:
	- Allow popups for this page.
	- Use the manual player link shown under the status box.
- Player does not update:
	- Reopen player window and enter fullscreen again.

## Limitations

- This MVP stores state in memory and browser local storage only.
- No network multi-user session is included.
- No advanced shape fog tools yet (rectangles only).
