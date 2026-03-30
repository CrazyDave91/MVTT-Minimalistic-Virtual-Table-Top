/*
 * This code was created with GitHub Copilot.
 * This codebase is released under the MIT License.
 * Use at your own risk. Provided "as is", without warranties of any kind.
 */

const CHANNEL_NAME = "mvtt_local_sync_v1";
const STORAGE_KEY = "mvtt_local_state_v1";
const SYNC_INTERVAL_MS = 1000;
const HANDLE_SIZE_PX = 10;
const MIN_VIEWPORT_SIZE_PX = 40;

const initialState = {
  imageSrc: null,
  imageWidth: 0,
  imageHeight: 0,
  imageRotation: 0,
  viewport: { x: 0, y: 0, width: 0, height: 0 },
  reveals: [],
};

const runtime = {
  role: new URLSearchParams(window.location.search).get("role") === "player" ? "player" : "gm",
  state: structuredClone(initialState),
  history: [],
  syncChannel: null,
  imageElement: null,
  playerWindowRef: null,
  gmCanvas: null,
  gmContext: null,
  playerCanvas: null,
  playerContext: null,
  gmTransform: null,
  interaction: null,
  statusMessage: "",
  statusLevel: "info",
  playerAspectRatio: 16 / 9,
  hoverHitType: "none",
};

initialize();

function initialize() {
  document.body.classList.toggle("player-mode", runtime.role === "player");

  runtime.syncChannel = createSyncChannel();
  setupWindowMessaging();

  if (runtime.role === "gm") {
    setupGmUi();
    startPeriodicSync();
    renderGm();
  } else {
    setupPlayerUi();
    renderPlayer();
    requestStateFromParent();
  }
}

function createSyncChannel() {
  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel(CHANNEL_NAME);
    channel.addEventListener("message", (event) => {
      const data = event.data;

      if (!data || typeof data !== "object") {
        return;
      }

      if (data.type === "state") {
        handleIncomingState(data.payload);
        return;
      }

      if (data.type === "player-metrics") {
        if (runtime.role === "gm") {
          handlePlayerMetrics(data.payload);
        }
        return;
      }

      handleIncomingState(data);
    });
    return channel;
  }

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY || !event.newValue) {
      return;
    }

    try {
      const parsed = JSON.parse(event.newValue);
      handleIncomingState(parsed);
    } catch {
      // Ignore malformed payloads from unrelated tooling.
    }
  });

  return null;
}

function setupWindowMessaging() {
  window.addEventListener("message", (event) => {
    if (!event.data || typeof event.data !== "object") {
      return;
    }

    if (event.data.type === "mvtt-state") {
      handleIncomingState(event.data.payload);
    }

    if (runtime.role === "gm" && event.data.type === "mvtt-request-state") {
      sendStateToPlayerWindow(event.source);
    }

    if (runtime.role === "gm" && event.data.type === "mvtt-player-metrics") {
      handlePlayerMetrics(event.data.payload);
    }

    if (runtime.role === "player" && event.data.type === "mvtt-request-fullscreen") {
      requestFullscreen(document.documentElement);
    }
  });
}

function setupGmUi() {
  runtime.gmCanvas = document.getElementById("gmCanvas");
  runtime.gmContext = runtime.gmCanvas.getContext("2d", { alpha: false });

  const imageInput = document.getElementById("imageInput");
  const openPlayerButton = document.getElementById("openPlayerButton");
  const rotateButton = document.getElementById("rotateButton");
  const undoButton = document.getElementById("undoButton");
  const resetFogButton = document.getElementById("resetFogButton");

  imageInput.addEventListener("change", onImageSelected);
  openPlayerButton.addEventListener("click", openOrFocusPlayerWindow);
  rotateButton.addEventListener("click", rotateImage);
  undoButton.addEventListener("click", undoLastAction);
  resetFogButton.addEventListener("click", resetFog);

  runtime.gmCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
  runtime.gmCanvas.addEventListener("mousedown", onGmPointerDown);
  runtime.gmCanvas.addEventListener("mousemove", onGmPointerMove);
  runtime.gmCanvas.addEventListener("mouseleave", () => {
    runtime.hoverHitType = "none";
    setCanvasCursor("default");
    renderGm();
  });
  window.addEventListener("mouseup", onGmPointerUp);
  window.addEventListener("resize", renderGm);

  const observer = new ResizeObserver(() => renderGm());
  observer.observe(runtime.gmCanvas.parentElement);
}

function setupPlayerUi() {
  runtime.playerCanvas = document.getElementById("playerCanvas");
  runtime.playerContext = runtime.playerCanvas.getContext("2d", { alpha: false });
  const hint = document.getElementById("playerHint");

  document.addEventListener("dblclick", () => requestFullscreen(document.documentElement));
  window.addEventListener("resize", () => {
    renderPlayer();
    sendPlayerMetrics();
  });
  window.addEventListener("fullscreenchange", () => {
    if (!hint) {
      return;
    }
    hint.style.display = document.fullscreenElement ? "none" : "block";
    sendPlayerMetrics();
  });

  const observer = new ResizeObserver(() => {
    renderPlayer();
    sendPlayerMetrics();
  });
  observer.observe(runtime.playerCanvas.parentElement);

  window.setInterval(sendPlayerMetrics, SYNC_INTERVAL_MS);
  sendPlayerMetrics();
}

function onImageSelected(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    const image = new Image();
    image.onload = () => {
      pushHistorySnapshot();
      runtime.imageElement = image;
      runtime.state.imageSrc = image.src;
      runtime.state.imageWidth = image.width;
      runtime.state.imageHeight = image.height;
      runtime.state.imageRotation = 0;
      runtime.state.reveals = [];

      const ratio = runtime.playerAspectRatio;
      runtime.state.viewport = createCenteredViewport(image.width, image.height, ratio);

      renderGm();
      broadcastState(true);
      updateStatusOverlay();
    };
    image.onerror = () => {
      setStatus("Image decoding failed. Try a different image file.", "error");
    };
    image.src = reader.result;
  };
  reader.onerror = () => {
    setStatus("Could not read selected file.", "error");
  };
  reader.readAsDataURL(file);
}

function createCenteredViewport(imageWidth, imageHeight, ratio) {
  const maxWidth = imageWidth * 0.6;
  const maxHeight = imageHeight * 0.6;

  let width = maxWidth;
  let height = width / ratio;

  if (height > maxHeight) {
    height = maxHeight;
    width = height * ratio;
  }

  return {
    x: (imageWidth - width) / 2,
    y: (imageHeight - height) / 2,
    width,
    height,
  };
}

function openOrFocusPlayerWindow() {
  const targetUrl = buildPlayerUrl();
  const features = "popup,width=1280,height=720,left=100,top=80";
  const handle = window.open(targetUrl, "MVTT_PlayerWindow", features);

  if (handle) {
    runtime.playerWindowRef = handle;
    handle.focus();
    broadcastState(true);
    handle.postMessage({ type: "mvtt-request-fullscreen" }, "*");
    updateStatusOverlay();
  } else {
    setStatus("Player window blocked by browser popup settings. Please allow popups and retry.", "warn");
  }
}

function onGmPointerDown(event) {
  if (!hasImageLoaded()) {
    setCanvasCursor("default");
    return;
  }

  const canvasPoint = getCanvasPointer(event, runtime.gmCanvas);
  const pointer = toImageCoordinates(canvasPoint.x, canvasPoint.y);
  if (!pointer) {
    return;
  }

  const viewportHit = getViewportHitType(canvasPoint.x, canvasPoint.y);
  runtime.hoverHitType = viewportHit.type;

  if (event.button === 2) {
    runtime.interaction = {
      type: "reveal",
      start: pointer,
      current: pointer,
    };
    setCanvasCursor("crosshair");
    return;
  }

  if (event.button !== 0) {
    return;
  }

  if (viewportHit.type === "none") {
    setCanvasCursor("default");
    return;
  }

  pushHistorySnapshot();

  if (viewportHit.type === "move") {
    runtime.interaction = {
      type: "move",
      pointerOffsetX: pointer.x - runtime.state.viewport.x,
      pointerOffsetY: pointer.y - runtime.state.viewport.y,
    };
    setCanvasCursor("grabbing");
    return;
  }

  runtime.interaction = {
    type: "resize",
    handle: viewportHit.type,
    anchor: getAnchorForHandle(runtime.state.viewport, viewportHit.type),
  };
  setCanvasCursor(getCursorForHitType(viewportHit.type));
}

function onGmPointerMove(event) {
  if (!hasImageLoaded()) {
    setCanvasCursor("default");
    return;
  }

  const canvasPoint = getCanvasPointer(event, runtime.gmCanvas);
  const hoverHit = getViewportHitType(canvasPoint.x, canvasPoint.y);
  const hoverChanged = runtime.hoverHitType !== hoverHit.type;
  runtime.hoverHitType = hoverHit.type;

  if (!runtime.interaction) {
    setCanvasCursor(getCursorForHitType(hoverHit.type));
    if (hoverChanged) {
      renderGm();
    }
    return;
  }

  const pointer = toImageCoordinates(canvasPoint.x, canvasPoint.y);
  if (!pointer) {
    setCanvasCursor("default");
    return;
  }

  if (runtime.interaction.type === "move") {
    const nextViewport = {
      ...runtime.state.viewport,
      x: pointer.x - runtime.interaction.pointerOffsetX,
      y: pointer.y - runtime.interaction.pointerOffsetY,
    };

    runtime.state.viewport = clampViewportToImage(nextViewport);
    setCanvasCursor("grabbing");
    renderGm();
    return;
  }

  if (runtime.interaction.type === "resize") {
    runtime.state.viewport = resizeViewportWithFixedAspect(runtime.interaction, pointer, runtime.playerAspectRatio);
    setCanvasCursor(getCursorForHitType(runtime.interaction.handle));
    renderGm();
    return;
  }

  if (runtime.interaction.type === "reveal") {
    runtime.interaction.current = pointer;
    setCanvasCursor("crosshair");
    renderGm();
  }
}

function onGmPointerUp() {
  if (!hasImageLoaded()) {
    setCanvasCursor("default");
    return;
  }

  if (!runtime.interaction) {
    setCanvasCursor("default");
    return;
  }

  if (runtime.interaction.type === "reveal") {
    const preview = buildRectangle(runtime.interaction.start, runtime.interaction.current);
    if (preview.width >= 2 && preview.height >= 2) {
      pushHistorySnapshot();
      runtime.state.reveals.push(preview);
    }
  }

  runtime.interaction = null;
  setCanvasCursor("default");
  renderGm();
  broadcastState(true);
}

function setCanvasCursor(cursor) {
  if (!runtime.gmCanvas) {
    return;
  }

  runtime.gmCanvas.style.cursor = cursor;
}

function getCursorForHitType(hitType) {
  if (hitType === "move") {
    return "move";
  }

  if (hitType === "nw" || hitType === "se") {
    return "nwse-resize";
  }

  if (hitType === "ne" || hitType === "sw") {
    return "nesw-resize";
  }

  return "default";
}

function getViewportHitType(canvasX, canvasY) {
  const viewportScreenRect = imageRectToCanvasRect(runtime.state.viewport);
  if (!viewportScreenRect) {
    return { type: "none" };
  }

  const corners = {
    nw: { x: viewportScreenRect.x, y: viewportScreenRect.y },
    ne: { x: viewportScreenRect.x + viewportScreenRect.width, y: viewportScreenRect.y },
    se: { x: viewportScreenRect.x + viewportScreenRect.width, y: viewportScreenRect.y + viewportScreenRect.height },
    sw: { x: viewportScreenRect.x, y: viewportScreenRect.y + viewportScreenRect.height },
  };

  for (const [handle, point] of Object.entries(corners)) {
    if (Math.abs(canvasX - point.x) <= HANDLE_SIZE_PX && Math.abs(canvasY - point.y) <= HANDLE_SIZE_PX) {
      return { type: handle };
    }
  }

  const withinRect =
    canvasX >= viewportScreenRect.x &&
    canvasX <= viewportScreenRect.x + viewportScreenRect.width &&
    canvasY >= viewportScreenRect.y &&
    canvasY <= viewportScreenRect.y + viewportScreenRect.height;

  return withinRect ? { type: "move" } : { type: "none" };
}

function getAnchorForHandle(viewport, handle) {
  if (handle === "nw") {
    return { x: viewport.x + viewport.width, y: viewport.y + viewport.height };
  }

  if (handle === "ne") {
    return { x: viewport.x, y: viewport.y + viewport.height };
  }

  if (handle === "se") {
    return { x: viewport.x, y: viewport.y };
  }

  return { x: viewport.x + viewport.width, y: viewport.y };
}

function resizeViewportWithFixedAspect(interaction, pointer, ratio) {
  const anchor = interaction.anchor;
  const minWidth = MIN_VIEWPORT_SIZE_PX;
  let widthFromPointer;

  if (interaction.handle === "nw" || interaction.handle === "sw") {
    widthFromPointer = anchor.x - pointer.x;
  } else {
    widthFromPointer = pointer.x - anchor.x;
  }

  let heightFromPointer;
  if (interaction.handle === "nw" || interaction.handle === "ne") {
    heightFromPointer = anchor.y - pointer.y;
  } else {
    heightFromPointer = pointer.y - anchor.y;
  }

  const proposedWidth = Math.max(minWidth, Math.max(Math.abs(widthFromPointer), Math.abs(heightFromPointer) * ratio));
  const proposedHeight = proposedWidth / ratio;

  let nextViewport;

  if (interaction.handle === "nw") {
    nextViewport = { x: anchor.x - proposedWidth, y: anchor.y - proposedHeight, width: proposedWidth, height: proposedHeight };
  } else if (interaction.handle === "ne") {
    nextViewport = { x: anchor.x, y: anchor.y - proposedHeight, width: proposedWidth, height: proposedHeight };
  } else if (interaction.handle === "se") {
    nextViewport = { x: anchor.x, y: anchor.y, width: proposedWidth, height: proposedHeight };
  } else {
    nextViewport = { x: anchor.x - proposedWidth, y: anchor.y, width: proposedWidth, height: proposedHeight };
  }

  return clampViewportToImage(nextViewport);
}

function clampViewportToImage(viewport) {
  const maxWidth = runtime.state.imageWidth;
  const maxHeight = runtime.state.imageHeight;

  const width = clamp(viewport.width, MIN_VIEWPORT_SIZE_PX, maxWidth);
  const height = clamp(viewport.height, MIN_VIEWPORT_SIZE_PX, maxHeight);
  const x = clamp(viewport.x, 0, maxWidth - width);
  const y = clamp(viewport.y, 0, maxHeight - height);

  return { x, y, width, height };
}

function renderGm() {
  if (!runtime.gmCanvas || !runtime.gmContext) {
    return;
  }

  fitCanvasToContainer(runtime.gmCanvas);

  const ctx = runtime.gmContext;
  ctx.fillStyle = "#121212";
  ctx.fillRect(0, 0, runtime.gmCanvas.width, runtime.gmCanvas.height);

  if (!hasImageLoaded()) {
    drawPlaceholder(ctx, runtime.gmCanvas, "Load an image to begin");
    return;
  }

  runtime.gmTransform = computeContainTransform(
    runtime.gmCanvas.width,
    runtime.gmCanvas.height,
    runtime.state.imageWidth,
    runtime.state.imageHeight,
  );

  try {
    drawImageWithFog(ctx);
    drawViewportOverlay(ctx);
    drawRevealPreview(ctx);
    drawStatusOverlay(ctx, runtime.gmCanvas);
  } catch {
    setStatus("Rendering error detected. Reload and retry with a smaller image.", "error");
  }
}

function drawImageWithFog(ctx) {
  const transform = runtime.gmTransform;
  ctx.drawImage(
    runtime.imageElement,
    0,
    0,
    runtime.state.imageWidth,
    runtime.state.imageHeight,
    transform.x,
    transform.y,
    transform.width,
    transform.height,
  );

  ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
  ctx.fillRect(transform.x, transform.y, transform.width, transform.height);

  for (const reveal of runtime.state.reveals) {
    const screenRect = imageRectToCanvasRect(reveal);

    ctx.drawImage(
      runtime.imageElement,
      reveal.x,
      reveal.y,
      reveal.width,
      reveal.height,
      screenRect.x,
      screenRect.y,
      screenRect.width,
      screenRect.height,
    );
  }
}

function drawViewportOverlay(ctx) {
  const viewport = imageRectToCanvasRect(runtime.state.viewport);
  if (!viewport) {
    return;
  }

  ctx.strokeStyle = "#ff2f2f";
  ctx.lineWidth = 2;
  ctx.strokeRect(viewport.x, viewport.y, viewport.width, viewport.height);

  const corners = {
    nw: [viewport.x, viewport.y],
    ne: [viewport.x + viewport.width, viewport.y],
    se: [viewport.x + viewport.width, viewport.y + viewport.height],
    sw: [viewport.x, viewport.y + viewport.height],
  };

  const activeHandle = runtime.interaction?.type === "resize" ? runtime.interaction.handle : runtime.hoverHitType;

  ctx.fillStyle = "#ff2f2f";
  for (const [handle, [x, y]] of Object.entries(corners)) {
    const size = activeHandle === handle ? HANDLE_SIZE_PX * 1.9 : HANDLE_SIZE_PX;
    ctx.fillRect(x - size / 2, y - size / 2, size, size);
  }
}

function drawRevealPreview(ctx) {
  if (!runtime.interaction || runtime.interaction.type !== "reveal") {
    return;
  }

  const previewRect = buildRectangle(runtime.interaction.start, runtime.interaction.current);
  const screenRect = imageRectToCanvasRect(previewRect);

  ctx.strokeStyle = "#ffffff";
  ctx.setLineDash([6, 4]);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(screenRect.x, screenRect.y, screenRect.width, screenRect.height);
  ctx.setLineDash([]);
}

function renderPlayer() {
  if (!runtime.playerCanvas || !runtime.playerContext) {
    return;
  }

  fitCanvasToContainer(runtime.playerCanvas);

  const ctx = runtime.playerContext;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, runtime.playerCanvas.width, runtime.playerCanvas.height);

  if (!hasImageLoaded()) {
    drawPlaceholder(ctx, runtime.playerCanvas, "Waiting for GM state...");
    return;
  }

  const viewport = runtime.state.viewport;

  for (const reveal of runtime.state.reveals) {
    const intersect = intersectRectangles(reveal, viewport);
    if (!intersect) {
      continue;
    }

    const dx = ((intersect.x - viewport.x) / viewport.width) * runtime.playerCanvas.width;
    const dy = ((intersect.y - viewport.y) / viewport.height) * runtime.playerCanvas.height;
    const dw = (intersect.width / viewport.width) * runtime.playerCanvas.width;
    const dh = (intersect.height / viewport.height) * runtime.playerCanvas.height;

    ctx.drawImage(
      runtime.imageElement,
      intersect.x,
      intersect.y,
      intersect.width,
      intersect.height,
      dx,
      dy,
      dw,
      dh,
    );
  }
}

function drawPlaceholder(ctx, canvas, text) {
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawCenteredMessage(ctx, canvas, text, "#e7e7e7", "600 20px Segoe UI");
}

function drawStatusOverlay(ctx, canvas) {
  if (!runtime.statusMessage) {
    return;
  }
  drawCenteredMessage(ctx, canvas, runtime.statusMessage, runtime.statusLevel === "error" ? "#ff8686" : "#e7e7e7", "400 16px Segoe UI");
}

function drawCenteredMessage(ctx, canvas, text, textColor, font) {
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  const lineHeight = 24;
  const lines = text.split("\n");
  const padding = 16;
  
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  
  let maxWidth = 0;
  for (const line of lines) {
    const metric = ctx.measureText(line);
    maxWidth = Math.max(maxWidth, metric.width);
  }
  
  const boxWidth = maxWidth + padding * 2;
  const boxHeight = lineHeight * lines.length + padding * 2;
  const boxX = centerX - boxWidth / 2;
  const boxY = centerY - boxHeight / 2;
  
  ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
  ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
  
  ctx.fillStyle = textColor;
  for (let i = 0; i < lines.length; i++) {
    ctx.fillText(lines[i], centerX, centerY - ((lines.length - 1) * lineHeight) / 2 + i * lineHeight);
  }
}

function fitCanvasToContainer(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

function getCanvasPointer(event, canvas) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;

  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
  };
}

function computeContainTransform(canvasWidth, canvasHeight, imageWidth, imageHeight) {
  const imageAspect = imageWidth / imageHeight;

  let drawWidth = canvasWidth;
  let drawHeight = drawWidth / imageAspect;

  if (drawHeight > canvasHeight) {
    drawHeight = canvasHeight;
    drawWidth = drawHeight * imageAspect;
  }

  return {
    x: (canvasWidth - drawWidth) / 2,
    y: (canvasHeight - drawHeight) / 2,
    width: drawWidth,
    height: drawHeight,
  };
}

function imageRectToCanvasRect(rect) {
  if (!runtime.gmTransform) {
    return null;
  }

  const scaleX = runtime.gmTransform.width / runtime.state.imageWidth;
  const scaleY = runtime.gmTransform.height / runtime.state.imageHeight;

  return {
    x: runtime.gmTransform.x + rect.x * scaleX,
    y: runtime.gmTransform.y + rect.y * scaleY,
    width: rect.width * scaleX,
    height: rect.height * scaleY,
  };
}

function toImageCoordinates(canvasX, canvasY) {
  if (!runtime.gmTransform) {
    return null;
  }

  const withinX = canvasX >= runtime.gmTransform.x && canvasX <= runtime.gmTransform.x + runtime.gmTransform.width;
  const withinY = canvasY >= runtime.gmTransform.y && canvasY <= runtime.gmTransform.y + runtime.gmTransform.height;

  if (!withinX || !withinY) {
    return null;
  }

  const normalizedX = (canvasX - runtime.gmTransform.x) / runtime.gmTransform.width;
  const normalizedY = (canvasY - runtime.gmTransform.y) / runtime.gmTransform.height;

  return {
    x: normalizedX * runtime.state.imageWidth,
    y: normalizedY * runtime.state.imageHeight,
  };
}

function buildRectangle(a, b) {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  };
}

function intersectRectangles(a, b) {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);

  if (right <= x || bottom <= y) {
    return null;
  }

  return { x, y, width: right - x, height: bottom - y };
}

function undoLastAction() {
  const previous = runtime.history.pop();
  if (!previous) {
    return;
  }

  if (previous.imageSrc && previous.imageSrc !== runtime.state.imageSrc) {
    const image = new Image();
    image.onload = () => {
      runtime.imageElement = image;
      runtime.state.imageSrc = previous.imageSrc;
      runtime.state.imageWidth = previous.imageWidth || image.width;
      runtime.state.imageHeight = previous.imageHeight || image.height;
      runtime.state.viewport = previous.viewport;
      runtime.state.reveals = previous.reveals;
      runtime.state.imageRotation = 0;
      renderGm();
      broadcastState(true);
    };
    image.onerror = () => {
      setStatus("Could not restore previous image state from history.", "error");
    };
    image.src = previous.imageSrc;
    return;
  }

  runtime.state.viewport = previous.viewport;
  runtime.state.reveals = previous.reveals;
  runtime.state.imageRotation = 0;

  renderGm();
  broadcastState(true);
}

function rotateImage() {
  if (!hasImageLoaded()) {
    return;
  }

  pushRotationSnapshot();

  const sourceWidth = runtime.state.imageWidth;
  const sourceHeight = runtime.state.imageHeight;
  const rotatedCanvas = document.createElement("canvas");
  rotatedCanvas.width = sourceHeight;
  rotatedCanvas.height = sourceWidth;

  const rotatedContext = rotatedCanvas.getContext("2d", { alpha: false });
  if (!rotatedContext) {
    setStatus("Rotation failed because the browser could not allocate canvas context.", "error");
    return;
  }

  rotatedContext.translate(rotatedCanvas.width / 2, rotatedCanvas.height / 2);
  rotatedContext.rotate(Math.PI / 2);
  rotatedContext.drawImage(runtime.imageElement, -sourceWidth / 2, -sourceHeight / 2, sourceWidth, sourceHeight);

  const rotatedSrc = rotatedCanvas.toDataURL("image/png");
  const rotatedImage = new Image();
  rotatedImage.onload = () => {
    runtime.imageElement = rotatedImage;
    runtime.state.imageSrc = rotatedSrc;
    runtime.state.imageWidth = rotatedImage.width;
    runtime.state.imageHeight = rotatedImage.height;
    runtime.state.imageRotation = 0;
    runtime.state.viewport = rotateRectClockwise(runtime.state.viewport, sourceWidth, sourceHeight);
    runtime.state.reveals = runtime.state.reveals.map((reveal) => rotateRectClockwise(reveal, sourceWidth, sourceHeight));

    renderGm();
    broadcastState(true);
  };
  rotatedImage.onerror = () => {
    setStatus("Rotated image could not be loaded. Try again with a smaller image.", "error");
  };
  rotatedImage.src = rotatedSrc;
}

function rotateRectClockwise(rect, sourceWidth, sourceHeight) {
  return {
    x: sourceHeight - (rect.y + rect.height),
    y: rect.x,
    width: rect.height,
    height: rect.width,
  };
}

function resetFog() {
  if (!hasImageLoaded() || runtime.state.reveals.length === 0) {
    return;
  }

  pushHistorySnapshot();
  runtime.state.reveals = [];
  renderGm();
  broadcastState(true);
}

function pushHistorySnapshot() {
  if (!hasImageLoaded()) {
    return;
  }

  runtime.history.push({
    viewport: structuredClone(runtime.state.viewport),
    reveals: structuredClone(runtime.state.reveals),
    imageRotation: runtime.state.imageRotation,
  });

  if (runtime.history.length > 120) {
    runtime.history.shift();
  }
}

function pushRotationSnapshot() {
  if (!hasImageLoaded()) {
    return;
  }

  runtime.history.push({
    viewport: structuredClone(runtime.state.viewport),
    reveals: structuredClone(runtime.state.reveals),
    imageSrc: runtime.state.imageSrc,
    imageWidth: runtime.state.imageWidth,
    imageHeight: runtime.state.imageHeight,
    imageRotation: 0,
  });

  if (runtime.history.length > 120) {
    runtime.history.shift();
  }
}

function startPeriodicSync() {
  window.setInterval(() => {
    broadcastState(false);
    refreshAspectIndicator();
  }, SYNC_INTERVAL_MS);
}

function broadcastState(forceRender) {
  if (runtime.role !== "gm") {
    return;
  }

  const payload = {
    imageSrc: runtime.state.imageSrc,
    imageWidth: runtime.state.imageWidth,
    imageHeight: runtime.state.imageHeight,
    imageRotation: 0,
    viewport: runtime.state.viewport,
    reveals: runtime.state.reveals,
    timestamp: Date.now(),
  };

  let realtimeSyncOk = false;

  if (runtime.syncChannel) {
    try {
      runtime.syncChannel.postMessage({ type: "state", payload });
      realtimeSyncOk = true;
    } catch {
      setStatus("Broadcast channel sync failed. Falling back to local storage sync.", "warn");
    }
  }

  // localStorage is a fallback channel and frequently hits quota with base64 images.
  // Persist only when real-time sync is not available.
  if (!realtimeSyncOk) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      setStatus("Local storage sync failed (possibly large image). Player sync may be limited.", "warn");
    }
  }

  if (runtime.playerWindowRef && !runtime.playerWindowRef.closed) {
    try {
      runtime.playerWindowRef.postMessage({ type: "mvtt-state", payload }, "*");
    } catch {
      setStatus("Direct player sync message failed. Reopen the player window.", "warn");
    }
  }

  if (forceRender && runtime.role === "gm") {
    renderGm();
  }
}

function requestStateFromParent() {
  if (window.opener) {
    window.opener.postMessage({ type: "mvtt-request-state" }, "*");
  }

  const cached = localStorage.getItem(STORAGE_KEY);
  if (cached) {
    try {
      handleIncomingState(JSON.parse(cached));
    } catch {
      // Ignore malformed cache entries.
    }
  }
}

function sendStateToPlayerWindow(windowRef) {
  if (!windowRef || typeof windowRef.postMessage !== "function") {
    return;
  }

  const payload = {
    imageSrc: runtime.state.imageSrc,
    imageWidth: runtime.state.imageWidth,
    imageHeight: runtime.state.imageHeight,
    viewport: runtime.state.viewport,
    reveals: runtime.state.reveals,
    timestamp: Date.now(),
  };

  windowRef.postMessage({ type: "mvtt-state", payload }, "*");
}

function handleIncomingState(payload) {
  if (!payload || runtime.role !== "player") {
    return;
  }

  runtime.state.imageWidth = payload.imageWidth || 0;
  runtime.state.imageHeight = payload.imageHeight || 0;
  runtime.state.viewport = payload.viewport || { x: 0, y: 0, width: 0, height: 0 };
  runtime.state.reveals = Array.isArray(payload.reveals) ? payload.reveals : [];
  runtime.state.imageRotation = 0;

  if (!payload.imageSrc) {
    runtime.state.imageSrc = null;
    runtime.imageElement = null;
    renderPlayer();
    return;
  }

  if (runtime.state.imageSrc === payload.imageSrc && runtime.imageElement) {
    renderPlayer();
    return;
  }

  runtime.state.imageSrc = payload.imageSrc;
  const image = new Image();
  image.onload = () => {
    runtime.imageElement = image;
    renderPlayer();
  };
  image.src = payload.imageSrc;
}

function requestFullscreen(element) {
  if (element.requestFullscreen) {
    element.requestFullscreen().catch(() => {
      // Browser refused because of gesture policy.
    });
  }
}

function sendPlayerMetrics() {
  if (runtime.role !== "player") {
    return;
  }

  const width = window.innerWidth;
  const height = window.innerHeight;
  if (!width || !height) {
    return;
  }

  const payload = {
    width,
    height,
    ratio: width / height,
    timestamp: Date.now(),
  };

  if (window.opener && !window.opener.closed) {
    window.opener.postMessage({ type: "mvtt-player-metrics", payload }, "*");
  }

  if (runtime.syncChannel) {
    try {
      runtime.syncChannel.postMessage({ type: "player-metrics", payload });
    } catch {
      // Metrics sync best-effort only.
    }
  }
}

function handlePlayerMetrics(payload) {
  if (!payload || typeof payload.ratio !== "number" || payload.ratio <= 0) {
    return;
  }

  const nextRatio = payload.ratio;
  const changed = Math.abs(nextRatio - runtime.playerAspectRatio) > 0.001;
  runtime.playerAspectRatio = nextRatio;
  refreshAspectIndicator();

  if (changed && hasImageLoaded()) {
    runtime.state.viewport = fitViewportToAspect(runtime.state.viewport, runtime.playerAspectRatio);
    renderGm();
    broadcastState(true);
  }
}

function fitViewportToAspect(viewport, ratio) {
  const centerX = viewport.x + viewport.width / 2;
  const centerY = viewport.y + viewport.height / 2;

  let width = viewport.width;
  let height = width / ratio;

  if (height > runtime.state.imageHeight) {
    height = runtime.state.imageHeight;
    width = height * ratio;
  }

  if (width > runtime.state.imageWidth) {
    width = runtime.state.imageWidth;
    height = width / ratio;
  }

  return clampViewportToImage({
    x: centerX - width / 2,
    y: centerY - height / 2,
    width,
    height,
  });
}

function refreshAspectIndicator() {
  // Aspect ratio indicator element has been removed.
}

function buildPlayerUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("role", "player");
  return url.toString();
}

function setStatus(message, level) {
  if (level === "error" || level === "warn") {
    runtime.statusMessage = message;
    runtime.statusLevel = level;
    return;
  }
  runtime.statusMessage = "";
  runtime.statusLevel = "info";
}

function updateStatusOverlay() {
  const playerOpen = runtime.playerWindowRef && !runtime.playerWindowRef.closed;
  
  if (!hasImageLoaded()) {
    runtime.statusMessage = "";
    return;
  }
  
  if (playerOpen) {
    runtime.statusMessage = "";
  } else {
    runtime.statusMessage = "Open player window to show the image to your player.";
    runtime.statusLevel = "info";
  }
}

function hasImageLoaded() {
  return Boolean(runtime.imageElement && runtime.state.imageWidth > 0 && runtime.state.imageHeight > 0);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
