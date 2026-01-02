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
  if (!ctx) return;

  const UA = (typeof navigator !== "undefined" && navigator.userAgent) ? navigator.userAgent : "";
  const IS_EDGE = /Edg\//.test(UA) || /EdgiOS\//.test(UA) || /EdgA\//.test(UA);

  let previewRetryTimer = null;
  let previewRetryCount = 0;

  function previewCssBox() {
    const cssH = 520;
    const rect = canvas.getBoundingClientRect();
    let cssW = rect && rect.width ? rect.width : 0;
    if (!cssW || cssW < 10) cssW = canvas.clientWidth || 0;
    if (!cssW || cssW < 10) cssW = (canvas.parentElement && canvas.parentElement.clientWidth) || 0;
    if (!cssW || cssW < 10) {
      const preview = canvas.closest(".preview");
      cssW = (preview && preview.clientWidth) || 0;
    }
    if (!cssW || cssW < 10) {
      const main = canvas.closest(".main");
      cssW = (main && main.clientWidth) || 0;
    }
    if (!cssW || cssW < 10) {
      cssW = window.innerWidth ? Math.max(1, window.innerWidth - 40) : 640;
    }
    cssW = Math.max(1, Math.floor(cssW));
    return { cssW, cssH };
  }

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
  let lastLoadError = "";

  function intrinsicSize(img) {
    if (!img) return { w: 0, h: 0 };
    if ("naturalWidth" in img && "naturalHeight" in img) {
      const w = img.naturalWidth || img.width || 0;
      const h = img.naturalHeight || img.height || 0;
      return { w, h };
    }
    return { w: img.width || 0, h: img.height || 0 };
  }

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

  function coverCropParams(img, rect, slot) {
    const { w: imgW, h: imgH } = intrinsicSize(img);
    if (!imgW || !imgH) return null;

    const scale = Math.max(rect.w / imgW, rect.h / imgH);
    let srcW = rect.w / scale;
    let srcH = rect.h / scale;

    const maxOffsetX = (imgW * scale - rect.w) / 2;
    const maxOffsetY = (imgH * scale - rect.h) / 2;
    slot.offsetX = clamp(slot.offsetX, -maxOffsetX, maxOffsetX);
    slot.offsetY = clamp(slot.offsetY, -maxOffsetY, maxOffsetY);

    let sx = (imgW - srcW) / 2 - slot.offsetX / scale;
    let sy = (imgH - srcH) / 2 - slot.offsetY / scale;
    sx = clamp(sx, 0, Math.max(0, imgW - srcW));
    sy = clamp(sy, 0, Math.max(0, imgH - srcH));

    // Edge seems more reliable with integer crop params.
    srcW = Math.max(1, Math.round(srcW));
    srcH = Math.max(1, Math.round(srcH));
    sx = Math.floor(clamp(sx, 0, Math.max(0, imgW - srcW)));
    sy = Math.floor(clamp(sy, 0, Math.max(0, imgH - srcH)));

    return { sx, sy, sw: srcW, sh: srcH };
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
    const { cssW, cssH } = previewCssBox();
    const wrap = document.getElementById("composeWrap");
    const wrapHidden = wrap ? getComputedStyle(wrap).display === "none" : false;
    if (wrapHidden) {
      meta.textContent = `${out.rows}×${out.cols} · ${out.outW}×${out.outH}px · 请切换到“拼装”标签后选择图片`;
      return;
    }
    if (cssW < 10) {
      previewRetryCount += 1;
      if (previewRetryTimer) clearTimeout(previewRetryTimer);
      if (previewRetryCount <= 60) {
        previewRetryTimer = setTimeout(drawPreview, 50);
      } else {
        meta.textContent = `${out.rows}×${out.cols} · ${out.outW}×${out.outH}px · 预览区域宽度为 0（请刷新页面或缩放窗口后重试）`;
      }
      return;
    }
    previewRetryCount = 0;

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

    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const r = slotRect(i, out);
      const dx = offX + r.x * scale;
      const dy = offY + r.y * scale;
      const dw = r.w * scale;
      const dh = r.h * scale;

      if (slot.imgIndex >= 0 && images[slot.imgIndex]) {
        const img = images[slot.imgIndex];
        const p = coverCropParams(img, r, slot);
        if (!p) continue;
        try {
          ctx.imageSmoothingEnabled = true;
          ctx.drawImage(img, p.sx, p.sy, p.sw, p.sh, dx, dy, dw, dh);
        } catch (e) {
          lastLoadError = "绘制失败（浏览器不支持该图片解码结果，建议改用 JPG/PNG）";
        }
      } else {
        ctx.fillStyle = "rgba(148,163,184,0.10)";
        ctx.fillRect(dx, dy, dw, dh);
      }
    }

    drawGridLines(out, scale, offX, offY);

    if (!images.length) {
      const hint = lastLoadError ? ` · ${lastLoadError}` : " · 未加载到可预览的图片（建议使用 JPG/PNG/WEBP）";
      meta.textContent = `${out.rows}×${out.cols} · ${out.outW}×${out.outH}px${hint}`;
    } else {
      const parts = [];
      for (let i = 0; i < Math.min(images.length, 3); i++) {
        const img = images[i];
        const { w, h } = intrinsicSize(img);
        const t = img && img.constructor && img.constructor.name ? img.constructor.name : "Image";
        parts.push(`#${i + 1} ${w}×${h} ${t}`);
      }
      const hint = lastLoadError ? ` · ${lastLoadError}` : "";
      const debug = parts.length ? ` · ${parts.join(" · ")}` : "";
      meta.textContent = `${out.rows}×${out.cols} · ${out.outW}×${out.outH}px · 已加载 ${images.length} 张${debug}${hint}`;
    }
  }

  function findSlotAt(clientX, clientY) {
    const out = outputSize();
    const rect = canvas.getBoundingClientRect();
    const { cssW, cssH } = previewCssBox();
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

  function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("read failed"));
      reader.readAsDataURL(file);
    });
  }

  function loadImageFromSrc(src) {
    return new Promise((resolve, reject) => {
      const el = new Image();
      el.crossOrigin = "anonymous";
      el.decoding = "async";
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("decode failed"));
      el.src = src;
    });
  }

  function canDrawDrawable(drawable) {
    const t = document.createElement("canvas");
    t.width = 8;
    t.height = 8;
    const tc = t.getContext("2d", { willReadFrequently: true });
    if (!tc) return true;
    tc.imageSmoothingEnabled = true;
    tc.fillStyle = "rgb(1,2,3)";
    tc.fillRect(0, 0, 8, 8);
    try {
      tc.drawImage(drawable, 0, 0, 8, 8);
    } catch (e) {
      return false;
    }
    try {
      const data = tc.getImageData(0, 0, 8, 8).data;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        const a = data[i + 3];
        if (a !== 255 || r !== 1 || g !== 2 || b !== 3) return true;
      }
      return false;
    } catch (e) {
      // If we can't read pixels (shouldn't happen for local blobs), assume drawable is ok.
      return true;
    }
  }

  async function decodeFileToDrawable(file) {
    if (!file || file.size <= 0) return { img: null, dispose: null, error: "empty file" };

    if (IS_EDGE) {
      try {
        const dataUrl = await readFileAsDataURL(file);
        const el = await loadImageFromSrc(dataUrl);
        if (!canDrawDrawable(el)) return { img: null, dispose: null, error: "edge draw failed" };
        return { img: el, dispose: null, error: null };
      } catch (e) {
        // continue fallbacks
      }
    }

    // Edge has intermittent issues where ImageBitmap decodes fine but draws as blank on <canvas>.
    // Prefer HTMLImageElement on Edge for stability.
    if (!IS_EDGE && window.createImageBitmap) {
      try {
        let bmp = null;
        try {
          bmp = await window.createImageBitmap(file, { imageOrientation: "from-image" });
        } catch (e) {
          bmp = await window.createImageBitmap(file);
        }
        if (bmp && bmp.width > 0 && bmp.height > 0) {
          if (!canDrawDrawable(bmp)) {
            try { bmp.close(); } catch (e) {}
            throw new Error("bitmap draw failed");
          }
          return {
            img: bmp,
            dispose: () => {
              try { bmp.close(); } catch (e) {}
            },
            error: null,
          };
        }
      } catch (e) {
        // fall back to HTMLImageElement
      }
    }

    if (window.URL && URL.createObjectURL) {
      const url = URL.createObjectURL(file);
      try {
        const el = await loadImageFromSrc(url);
        if (!canDrawDrawable(el)) throw new Error("draw failed");
        return { img: el, dispose: () => URL.revokeObjectURL(url), error: null };
      } catch (e) {
        try { URL.revokeObjectURL(url); } catch (e2) {}
      }
    }

    try {
      const dataUrl = await readFileAsDataURL(file);
      const el = await loadImageFromSrc(dataUrl);
      return { img: el, dispose: null, error: null };
    } catch (e) {
      return { img: null, dispose: null, error: "decode failed" };
    }
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
      lastLoadError = "";
      drawPreview();
      return;
    }

    meta.textContent = `加载中…（${files.length}）`;

    const supported = new Set([
      "image/jpeg",
      "image/jpg",
      "image/png",
      "image/webp",
      "image/gif",
      "image/bmp",
      "image/heic",
      "image/heif",
    ]);
    const unsupported = files.filter((f) => f.type && !supported.has(f.type));

    const loaded = [];
    const disposers = [];
    let failed = 0;
    let zeroSized = 0;

    for (const f of files) {
      const decoded = await decodeFileToDrawable(f);
      if (decoded.img) {
        const { w, h } = intrinsicSize(decoded.img);
        if (!w || !h) zeroSized += 1;
        loaded.push(decoded.img);
        if (decoded.dispose) disposers.push(decoded.dispose);
      } else {
        failed += 1;
      }
    }

    for (const dispose of imageDisposers) {
      try { dispose(); } catch (e) {}
    }

    images = loaded;
    imageDisposers = disposers;

    slots = [];
    lastLoadError = "";
    if (!images.length) {
      if (failed) {
        lastLoadError = "图片解码失败（可能是 HEIC/HEIF 或浏览器不支持，请先转成 JPG/PNG）";
      } else {
        lastLoadError = "未加载到可预览的图片";
      }
    } else if (failed) {
      lastLoadError = `有 ${failed} 张图片解码失败`;
    } else if (zeroSized) {
      lastLoadError = `有 ${zeroSized} 张图片尺寸为 0（请更换图片或浏览器）`;
    }
    resetOffsets();
    if (!images.length && unsupported.length) {
      lastLoadError = `图片格式可能不支持：${unsupported[0].type || "unknown"}`;
      drawPreview();
    }
  }

  function canvasToBlob(canvasEl, mime, quality) {
    if (canvasEl.toBlob) {
      return new Promise((resolve) => canvasEl.toBlob(resolve, mime, quality));
    }
    try {
      const dataUrl = canvasEl.toDataURL(mime, quality);
      const parts = dataUrl.split(",");
      if (parts.length < 2) return Promise.resolve(null);
      const header = parts[0] || "";
      const base64 = parts[1] || "";
      const m = header.match(/data:([^;]+);base64/);
      const outMime = m ? m[1] : mime;
      const binary = atob(base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return Promise.resolve(new Blob([bytes], { type: outMime }));
    } catch (e) {
      return Promise.resolve(null);
    }
  }

  async function exportImage() {
    ensureSlots();
    const out = outputSize();
    if (!images.length) {
      lastLoadError = lastLoadError || "未加载到可导出的图片";
      drawPreview();
      return;
    }

    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = out.outW;
    exportCanvas.height = out.outH;
    const ex = exportCanvas.getContext("2d");
    if (!ex) return;
    ex.fillStyle = "#ffffff";
    ex.fillRect(0, 0, out.outW, out.outH);

    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const r = slotRect(i, out);

      if (slot.imgIndex >= 0 && images[slot.imgIndex]) {
        const img = images[slot.imgIndex];
        const p = coverCropParams(img, r, slot);
        if (!p) continue;
        try {
          ex.imageSmoothingEnabled = true;
          ex.drawImage(img, p.sx, p.sy, p.sw, p.sh, r.x, r.y, r.w, r.h);
        } catch (e) {
          lastLoadError = "导出绘制失败（建议改用 JPG/PNG 图片再试）";
          drawPreview();
          return;
        }
      } else {
        ex.fillStyle = "rgba(148,163,184,0.10)";
        ex.fillRect(r.x, r.y, r.w, r.h);
      }
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

    const blob = await canvasToBlob(exportCanvas, mime, quality);
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

    const { cssW, cssH } = previewCssBox();
    const scale = Math.min(cssW / out.outW, cssH / out.outH);

    slot.offsetX = dragging.baseX + (evt.clientX - dragging.startX) / scale;
    slot.offsetY = dragging.baseY + (evt.clientY - dragging.startY) / scale;
    coverCropParams(img, r, slot);
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
