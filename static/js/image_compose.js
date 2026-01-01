(() => {
  const filesInput = document.getElementById("imgComposeFiles");
  const layoutSelect = document.getElementById("imgComposeLayout");
  const widthInput = document.getElementById("imgComposeWidth");
  const formatSelect = document.getElementById("imgComposeFormat");
  const exportBtn = document.getElementById("imgComposeExport");
  const resetBtn = document.getElementById("imgComposeReset");
  const canvas = document.getElementById("imgComposeCanvas");
  const meta = document.getElementById("imgComposeMeta");

  if (!filesInput || !layoutSelect || !widthInput || !formatSelect || !exportBtn || !resetBtn || !canvas || !meta) {
    return;
  }

  const ctx = canvas.getContext("2d");

  function layoutToGrid(layout) {
    if (layout === "split_v2") return [1, 2];
    if (layout === "split_h2") return [2, 1];
    if (layout === "grid_2") return [2, 2];
    if (layout === "grid_2x3") return [2, 3];
    return [3, 3];
  }

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  let images = [];
  let imageDisposers = [];
  let slots = [];
  let dragging = null;

  function currentGrid() {
    return layoutToGrid(layoutSelect.value);
  }

  function outputSize() {
    const [rows, cols] = currentGrid();
    let outW = parseInt(widthInput.value || "2048", 10);
    if (!Number.isFinite(outW)) outW = 2048;
    outW = clamp(outW, 512, 8192);
    const cellW = Math.floor(outW / cols);
    const outH = cellW * rows;
    return { rows, cols, outW, outH, cellW, cellH: cellW };
  }

  function ensureSlots() {
    const { rows, cols } = currentGrid();
    const needed = rows * cols;
    while (slots.length < needed) {
      slots.push({ imgIndex: -1, offsetX: 0, offsetY: 0 });
    }
    slots = slots.slice(0, needed);
    for (let i = 0; i < needed; i++) {
      if (slots[i].imgIndex === -1 && images[i]) slots[i].imgIndex = i;
      if (slots[i].imgIndex >= images.length) slots[i].imgIndex = -1;
    }
  }

  function slotRect(i, out) {
    const r = Math.floor(i / out.cols);
    const c = i % out.cols;
    return { x: c * out.cellW, y: r * out.cellH, w: out.cellW, h: out.cellH };
  }

  function coverDrawParams(img, rect, slot) {
    const scale = Math.max(rect.w / img.width, rect.h / img.height);
    const drawW = img.width * scale;
    const drawH = img.height * scale;
    const minX = rect.w - drawW;
    const minY = rect.h - drawH;
    slot.offsetX = clamp(slot.offsetX, minX, 0);
    slot.offsetY = clamp(slot.offsetY, minY, 0);
    return { drawW, drawH };
  }

  function drawGridLines(out, scale, offsetX, offsetY) {
    const { rows, cols } = out;

    function line(x1, y1, x2, y2) {
      ctx.save();
      ctx.setLineDash([6 * scale, 4 * scale]);

      ctx.lineWidth = 3 * scale;
      ctx.strokeStyle = "rgba(0,0,0,0.75)";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();

      ctx.lineWidth = 1 * scale;
      ctx.strokeStyle = "rgba(255,255,255,0.95)";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();

      ctx.restore();
    }

    for (let c = 1; c < cols; c++) {
      const x = offsetX + (out.outW * c) / cols * scale;
      line(x, offsetY, x, offsetY + out.outH * scale);
    }
    for (let r = 1; r < rows; r++) {
      const y = offsetY + (out.outH * r) / rows * scale;
      line(offsetX, y, offsetX + out.outW * scale, y);
    }
  }

  function drawPreview() {
    ensureSlots();
    const out = outputSize();

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const cssW = Math.max(1, rect.width || 1);
    const cssH = 520;
    if (cssW < 10) {
      // Likely still hidden (tab not shown yet); retry next frame.
      requestAnimationFrame(() => drawPreview());
      return;
    }

    canvas.style.height = cssH + "px";
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, cssW, cssH);

    const scale = Math.min(cssW / out.outW, cssH / out.outH);
    const drawW = out.outW * scale;
    const drawH = out.outH * scale;
    const offX = Math.round((cssW - drawW) / 2);
    const offY = Math.round((cssH - drawH) / 2);

    ctx.save();
    ctx.translate(offX, offY);
    ctx.scale(scale, scale);

    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const r = slotRect(i, out);

      ctx.save();
      ctx.beginPath();
      ctx.rect(r.x, r.y, r.w, r.h);
      ctx.clip();

      if (slot.imgIndex >= 0 && images[slot.imgIndex]) {
        const img = images[slot.imgIndex];
        const p = coverDrawParams(img, r, slot);
        const x = r.x + (r.w - p.drawW) / 2 + slot.offsetX;
        const y = r.y + (r.h - p.drawH) / 2 + slot.offsetY;
        ctx.drawImage(img, x, y, p.drawW, p.drawH);
      } else {
        ctx.fillStyle = "rgba(148,163,184,0.10)";
        ctx.fillRect(r.x, r.y, r.w, r.h);
      }

      ctx.restore();
    }

    ctx.restore();
    drawGridLines(out, scale, offX, offY);

    if (!images.length) {
      meta.textContent = `${out.rows}×${out.cols} · ${out.outW}×${out.outH}px · 未加载到可预览的图片（建议使用 JPG/PNG/WEBP）`;
    } else {
      meta.textContent = `${out.rows}×${out.cols} · ${out.outW}×${out.outH}px · 已加载 ${images.length} 张`;
    }
  }

  function findSlotAt(clientX, clientY) {
    const out = outputSize();
    const rect = canvas.getBoundingClientRect();
    const cssW = Math.max(1, rect.width || 1);
    const cssH = 520;
    const scale = Math.min(cssW / out.outW, cssH / out.outH);
    const drawW = out.outW * scale;
    const drawH = out.outH * scale;
    const offX = Math.round((cssW - drawW) / 2);
    const offY = Math.round((cssH - drawH) / 2);

    const x = clientX - rect.left - offX;
    const y = clientY - rect.top - offY;
    if (x < 0 || y < 0 || x > drawW || y > drawH) return null;

    const ox = x / scale;
    const oy = y / scale;
    const col = Math.floor(ox / out.cellW);
    const row = Math.floor(oy / out.cellH);
    const idx = row * out.cols + col;
    if (idx < 0 || idx >= slots.length) return null;

    return { idx, out };
  }

  function resetOffsets() {
    ensureSlots();
    for (const s of slots) {
      s.offsetX = 0;
      s.offsetY = 0;
    }
    drawPreview();
  }

  async function loadFiles(fileList) {
    const files = Array.from(fileList || []).filter((f) => f && f.size > 0);
    if (!files.length) {
      for (const dispose of imageDisposers) {
        try { dispose(); } catch (e) {}
      }
      images = [];
      imageDisposers = [];
      slots = [];
      drawPreview();
      return;
    }

    meta.textContent = `加载中…（${files.length}）`;

    const supported = new Set(["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"]);
    const unsupported = files.filter((f) => f.type && !supported.has(f.type));

    const loaded = [];
    const disposers = [];

    for (const f of files) {
      // Prefer ImageBitmap when possible (more reliable decode, faster).
      if (window.createImageBitmap) {
        try {
          const bmp = await window.createImageBitmap(f);
          loaded.push(bmp);
          disposers.push(() => {
            try { bmp.close(); } catch (e) {}
          });
          continue;
        } catch (e) {
          // fall back to HTMLImageElement
        }
      }

      const url = URL.createObjectURL(f);
      const img = await new Promise((resolve) => {
        const el = new Image();
        el.decoding = "async";
        el.onload = () => resolve(el);
        el.onerror = () => resolve(null);
        el.src = url;
      });
      if (img) {
        loaded.push(img);
        disposers.push(() => URL.revokeObjectURL(url));
      } else {
        URL.revokeObjectURL(url);
      }
    }

    for (const dispose of imageDisposers) {
      try { dispose(); } catch (e) {}
    }

    images = loaded;
    imageDisposers = disposers;

    slots = [];
    resetOffsets();
    if (!images.length && unsupported.length) {
      meta.textContent = `图片格式可能不支持：${unsupported[0].type || "unknown"}`;
    }
  }

  async function exportImage() {
    ensureSlots();
    const out = outputSize();

    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = out.outW;
    exportCanvas.height = out.outH;
    const ex = exportCanvas.getContext("2d");
    ex.fillStyle = "#ffffff";
    ex.fillRect(0, 0, out.outW, out.outH);

    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const r = slotRect(i, out);
      ex.save();
      ex.beginPath();
      ex.rect(r.x, r.y, r.w, r.h);
      ex.clip();

      if (slot.imgIndex >= 0 && images[slot.imgIndex]) {
        const img = images[slot.imgIndex];
        const p = coverDrawParams(img, r, slot);
        const x = r.x + (r.w - p.drawW) / 2 + slot.offsetX;
        const y = r.y + (r.h - p.drawH) / 2 + slot.offsetY;
        ex.drawImage(img, x, y, p.drawW, p.drawH);
      } else {
        ex.fillStyle = "rgba(148,163,184,0.10)";
        ex.fillRect(r.x, r.y, r.w, r.h);
      }

      ex.restore();
    }

    const fmt = formatSelect.value || "png";
    let mime = "image/png";
    let ext = "png";
    let quality = undefined;
    if (fmt === "jpg") {
      mime = "image/jpeg";
      ext = "jpg";
      quality = 0.98;
    } else if (fmt === "webp") {
      mime = "image/webp";
      ext = "webp";
      quality = 1.0;
    }

    const blob = await new Promise((resolve) => exportCanvas.toBlob(resolve, mime, quality));
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const [rows, cols] = currentGrid();
    a.download = `compose_${rows}x${cols}_${out.outW}w.${ext}`;
    a.href = url;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function onPointerDown(evt) {
    const hit = findSlotAt(evt.clientX, evt.clientY);
    if (!hit) return;
    const slot = slots[hit.idx];
    if (slot.imgIndex < 0) return;
    dragging = {
      idx: hit.idx,
      startX: evt.clientX,
      startY: evt.clientY,
      baseX: slot.offsetX,
      baseY: slot.offsetY,
    };
    canvas.setPointerCapture(evt.pointerId);
  }

  function onPointerMove(evt) {
    if (!dragging) return;
    const out = outputSize();
    const r = slotRect(dragging.idx, out);
    const slot = slots[dragging.idx];
    const img = images[slot.imgIndex];
    if (!img) return;

    const rect = canvas.getBoundingClientRect();
    const cssW = Math.max(1, rect.width || 1);
    const cssH = 520;
    const scale = Math.min(cssW / out.outW, cssH / out.outH);

    slot.offsetX = dragging.baseX + (evt.clientX - dragging.startX) / scale;
    slot.offsetY = dragging.baseY + (evt.clientY - dragging.startY) / scale;
    coverDrawParams(img, r, slot);
    drawPreview();
  }

  function onPointerUp() {
    dragging = null;
  }

  filesInput.addEventListener("change", (e) => loadFiles(e.target.files));
  // Re-selecting the same files should also trigger change in some browsers.
  filesInput.addEventListener("click", () => {
    filesInput.value = "";
  });
  layoutSelect.addEventListener("change", () => {
    ensureSlots();
    resetOffsets();
  });
  widthInput.addEventListener("change", () => drawPreview());
  window.addEventListener("resize", () => drawPreview());
  exportBtn.addEventListener("click", () => exportImage());
  resetBtn.addEventListener("click", () => resetOffsets());

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);
  canvas.addEventListener("pointerleave", onPointerUp);

  if ("ResizeObserver" in window) {
    const ro = new ResizeObserver(() => drawPreview());
    ro.observe(canvas);
  }

  const wrap = document.getElementById("composeWrap");
  if (wrap && "MutationObserver" in window) {
    const mo = new MutationObserver(() => {
      const display = getComputedStyle(wrap).display;
      if (display !== "none") requestAnimationFrame(() => drawPreview());
    });
    mo.observe(wrap, { attributes: true, attributeFilter: ["style", "class"] });
  }

  drawPreview();
})();
