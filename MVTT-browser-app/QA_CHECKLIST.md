<!--
This code was created with GitHub Copilot.
This codebase is released under the MIT License.
Use at your own risk. Provided "as is", without warranties of any kind.
-->

# Local Battlemap QA Checklist

Run this checklist before every live session.

## Environment

- Browser: Chrome, Edge, or Firefox current version.
- Open app from local file path.
- Popup blocker disabled for local file context.

## GM Window Checks

1. Initial load
- Page opens with visible controls and canvas.
- Status box shows ready message.

2. Image load
- Select an image file.
- Expected: map appears (slightly darkened), red viewport visible, no full-black canvas.
- Expected: status shows successful image dimensions.

3. Viewport interactions
- Drag center of red viewport with left mouse.
- Drag each corner with left mouse.
- Expected: movement and scaling work, ratio remains stable.

4. Fog actions
- Right-click drag reveals rectangular regions.
- Undo restores previous action.
- Reset Fog To Start clears all reveals.

## Player Window Checks

1. Open player window
- Click Open or Focus Player Window.
- Expected: second window opens with player view.
- If blocked: manual link opens player window.

2. Synchronization
- Move viewport and draw reveals in GM view.
- Expected: player view updates at least once per second.
- Click Sync Now and verify immediate update.

3. Fullscreen
- Click Enter Fullscreen in player window.
- Expected: player view enters fullscreen.

## Resilience Checks

- Load a larger image and confirm app stays responsive.
- Verify status warns on popup/storage failures instead of silent break.

## Sign-off

- QA Date:
- Browser/Version:
- Result: Pass or Fail
- Findings:
