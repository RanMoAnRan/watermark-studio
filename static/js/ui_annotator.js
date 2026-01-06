function setupUiAnnotator(cfg) {
  const fileInput = document.querySelector(cfg.fileInput);
  const viewport = document.querySelector(cfg.viewport);
  const world = document.querySelector(cfg.world);
  const imgEl = document.querySelector(cfg.image);
  const svg = document.querySelector(cfg.overlay);
  const hud = document.querySelector(cfg.hud);

  const blocksEl = document.querySelector(cfg.blocks);
  const jsonTextEl = document.querySelector(cfg.jsonText);
  const selectedIdEl = document.querySelector(cfg.selectedId);
  const componentCountEl = document.querySelector(cfg.componentCount);

  const nameInput = document.querySelector(cfg.nameInput);
  const typeSelect = document.querySelector(cfg.typeSelect);
  const textInput = document.querySelector(cfg.textInput);
  const bgColorInput = document.querySelector(cfg.bgColorInput);
  const textColorInput = document.querySelector(cfg.textColorInput);
  const fontSizeInput = document.querySelector(cfg.fontSizeInput);
  const radiusInput = document.querySelector(cfg.radiusInput);
  const statusEl = document.querySelector(cfg.status);

  const resetViewBtn = document.querySelector(cfg.resetViewBtn);
  const clearAllBtn = document.querySelector(cfg.clearAllBtn);
  const downloadJsonBtn = document.querySelector(cfg.downloadJsonBtn);
  const copyJsonBtn = document.querySelector(cfg.copyJsonBtn);
  const saveJsonBtn = document.querySelector(cfg.saveJsonBtn);
  const saveImageBtn = document.querySelector(cfg.saveImageBtn);

  if (!fileInput || !viewport || !world || !imgEl || !svg || !blocksEl || !jsonTextEl) return;

  const state = {
    schema: "watermark-studio.ui-annot-v1",
    image: {
      name: "",
      source: "",
      width: 0,
      height: 0,
    },
    components: [],
    view: {
      scale: 1,
      tx: 0,
      ty: 0,
      minScale: 0.05,
      maxScale: 24,
    },
    selectedId: null,
    keys: {
      space: false,
    },
  };

  const analysisCanvas = document.createElement("canvas");
  const analysisCtx = analysisCanvas.getContext("2d", { willReadFrequently: true });

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.style.color = kind === "error" ? "var(--danger)" : "";
  }

  function hex2(v) {
    const s = Math.max(0, Math.min(255, v | 0)).toString(16);
    return s.length === 1 ? "0" + s : s;
  }

  function rgbToHex(r, g, b) {
    return "#" + hex2(r) + hex2(g) + hex2(b);
  }

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function normalizeRect(a, b) {
    const x1 = Math.min(a.x, b.x);
    const y1 = Math.min(a.y, b.y);
    const x2 = Math.max(a.x, b.x);
    const y2 = Math.max(a.y, b.y);
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  }

  function ensureId(prefix) {
    const s = Math.random().toString(16).slice(2);
    return (prefix || "c") + "_" + s;
  }

  function getViewportPoint(evt) {
    const r = viewport.getBoundingClientRect();
    return {
      x: evt.clientX - r.left,
      y: evt.clientY - r.top,
      w: r.width,
      h: r.height,
    };
  }

  function screenToWorld(p) {
    return {
      x: (p.x - state.view.tx) / state.view.scale,
      y: (p.y - state.view.ty) / state.view.scale,
    };
  }

  function applyTransform() {
    world.style.transformOrigin = "0 0";
    world.style.transform = `translate(${state.view.tx}px, ${state.view.ty}px) scale(${state.view.scale})`;
    updateHud();
  }

  function fitToViewport() {
    if (!state.image.width || !state.image.height) return;
    const r = viewport.getBoundingClientRect();
    const pad = 10;
    const scale = Math.min((r.width - pad * 2) / state.image.width, (r.height - pad * 2) / state.image.height);
    state.view.scale = clamp(scale > 0 ? scale : 1, state.view.minScale, state.view.maxScale);
    state.view.tx = (r.width - state.image.width * state.view.scale) / 2;
    state.view.ty = (r.height - state.image.height * state.view.scale) / 2;
    applyTransform();
  }

  function updateHud() {
    if (!hud) return;
    if (!state.image.width) {
      hud.style.display = "none";
      return;
    }
    hud.style.display = "";
    hud.textContent = `${Math.round(state.view.scale * 100)}% · ${state.image.width}×${state.image.height}`;
  }

  function setImage(src, meta) {
    state.image.name = (meta && meta.name) || state.image.name || "";
    state.image.source = (meta && meta.source) || state.image.source || "";
    setStatus("");

    if (!src) {
      imgEl.style.display = "none";
      imgEl.removeAttribute("src");
      return;
    }

    imgEl.onload = () => {
      state.image.width = imgEl.naturalWidth || 0;
      state.image.height = imgEl.naturalHeight || 0;

      svg.setAttribute("width", String(state.image.width));
      svg.setAttribute("height", String(state.image.height));
      svg.setAttribute("viewBox", `0 0 ${state.image.width} ${state.image.height}`);

      analysisCanvas.width = state.image.width;
      analysisCanvas.height = state.image.height;
      if (analysisCtx) {
        analysisCtx.clearRect(0, 0, analysisCanvas.width, analysisCanvas.height);
        analysisCtx.drawImage(imgEl, 0, 0);
      }

      imgEl.style.display = "block";
      fitToViewport();
      renderAll();
    };
    imgEl.src = src;
  }

  function quantizeColor(r, g, b) {
    const qr = (r >> 4) & 0x0f;
    const qg = (g >> 4) & 0x0f;
    const qb = (b >> 4) & 0x0f;
    return (qr << 8) | (qg << 4) | qb;
  }

  function dequantizeColor(key) {
    const qr = (key >> 8) & 0x0f;
    const qg = (key >> 4) & 0x0f;
    const qb = key & 0x0f;
    const r = qr * 16 + 8;
    const g = qg * 16 + 8;
    const b = qb * 16 + 8;
    return { r, g, b };
  }

  function analyzeBox(bbox) {
    if (!analysisCtx || !state.image.width || !state.image.height) return null;
    const x0 = clamp(Math.floor(bbox.x), 0, state.image.width - 1);
    const y0 = clamp(Math.floor(bbox.y), 0, state.image.height - 1);
    const x1 = clamp(Math.ceil(bbox.x + bbox.w), 0, state.image.width);
    const y1 = clamp(Math.ceil(bbox.y + bbox.h), 0, state.image.height);
    const w = Math.max(1, x1 - x0);
    const h = Math.max(1, y1 - y0);

    const step = w * h > 260_000 ? 4 : (w * h > 120_000 ? 3 : 2);
    let count = 0;
    let sumR = 0, sumG = 0, sumB = 0;
    let sumLuma = 0;
    let edgeCount = 0;
    const buckets = new Map();

    const data = analysisCtx.getImageData(x0, y0, w, h).data;
    const rowStride = w * 4;
    for (let yy = 0; yy < h; yy += step) {
      const row = yy * rowStride;
      let prev = null;
      for (let xx = 0; xx < w; xx += step) {
        const i = row + xx * 4;
        const r = data[i] | 0;
        const g = data[i + 1] | 0;
        const b = data[i + 2] | 0;
        sumR += r;
        sumG += g;
        sumB += b;
        sumLuma += (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
        count += 1;
        const key = quantizeColor(r, g, b);
        buckets.set(key, (buckets.get(key) || 0) + 1);

        if (prev) {
          const dist = Math.abs(r - prev.r) + Math.abs(g - prev.g) + Math.abs(b - prev.b);
          if (dist > 120) edgeCount += 1;
        }
        prev = { r, g, b };
      }
    }

    const avg = count ? { r: Math.round(sumR / count), g: Math.round(sumG / count), b: Math.round(sumB / count) } : { r: 0, g: 0, b: 0 };
    const avgLuma = count ? (sumLuma / count) : 0;
    const sorted = Array.from(buckets.entries()).sort((a, b) => b[1] - a[1]);
    const dominant = sorted.slice(0, 8).map(([k]) => {
      const c = dequantizeColor(k);
      return rgbToHex(c.r, c.g, c.b);
    });

    const bgKey = sorted.length ? sorted[0][0] : quantizeColor(avg.r, avg.g, avg.b);
    const bg = dequantizeColor(bgKey);
    const bgHex = rgbToHex(bg.r, bg.g, bg.b);

    // Heuristic: choose the most frequent color far from bg as "content/text" color.
    let fgKey = null;
    for (const [k] of sorted) {
      if (k === bgKey) continue;
      const c = dequantizeColor(k);
      const dist = Math.abs(c.r - bg.r) + Math.abs(c.g - bg.g) + Math.abs(c.b - bg.b);
      if (dist > 140) {
        fgKey = k;
        break;
      }
    }
    const fg = fgKey != null ? dequantizeColor(fgKey) : { r: 255 - bg.r, g: 255 - bg.g, b: 255 - bg.b };
    const fgHex = rgbToHex(fg.r, fg.g, fg.b);

    function srgbToLinear(u) {
      const v = u / 255;
      return v <= 0.04045 ? (v / 12.92) : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    function relLum(c) {
      return 0.2126 * srgbToLinear(c.r) + 0.7152 * srgbToLinear(c.g) + 0.0722 * srgbToLinear(c.b);
    }
    const Lbg = relLum(bg);
    const Lfg = relLum(fg);
    const contrastRatio = (Math.max(Lbg, Lfg) + 0.05) / (Math.min(Lbg, Lfg) + 0.05);

    return {
      average_color: rgbToHex(avg.r, avg.g, avg.b),
      dominant_colors: dominant,
      suggested_bg_color: bgHex,
      suggested_fg_color: fgHex,
      avg_luma: +avgLuma.toFixed(6),
      contrast_ratio: +contrastRatio.toFixed(4),
      edge_density: count ? +(edgeCount / count).toFixed(6) : 0,
      sample_step: step,
    };
  }

  function componentToJson(c, index) {
    const bbox = {
      x: Math.round(c.bbox.x),
      y: Math.round(c.bbox.y),
      w: Math.round(c.bbox.w),
      h: Math.round(c.bbox.h),
    };
    const nx = state.image.width ? bbox.x / state.image.width : 0;
    const ny = state.image.height ? bbox.y / state.image.height : 0;
    const nw = state.image.width ? bbox.w / state.image.width : 0;
    const nh = state.image.height ? bbox.h / state.image.height : 0;

    const style = c.style || {};
    const typography = style.typography || {};
    const background = style.background || {};
    const border = style.border || {};

    return {
      id: c.id,
      name: c.name || "",
      type: c.type || "unknown",
      bbox,
      bbox_norm: { x: +nx.toFixed(6), y: +ny.toFixed(6), w: +nw.toFixed(6), h: +nh.toFixed(6) },
      z_index: typeof c.z_index === "number" ? c.z_index : index,
      style: {
        position: "absolute",
        width: bbox.w,
        height: bbox.h,
        opacity: typeof style.opacity === "number" ? style.opacity : 1,
        background: {
          color: background.color || (c.analysis ? c.analysis.suggested_bg_color : ""),
          gradient: background.gradient || "",
          image: background.image || "",
        },
        border: {
          color: border.color || "",
          width: typeof border.width === "number" ? border.width : 0,
          radius: typeof border.radius === "number" ? border.radius : (typeof style.radius === "number" ? style.radius : 0),
        },
        shadow: style.shadow || { x: 0, y: 0, blur: 0, spread: 0, color: "" },
        typography: {
          text: typography.text || "",
          color: typography.color || (c.analysis ? c.analysis.suggested_fg_color : ""),
          font_family: typography.font_family || "",
          font_size: typeof typography.font_size === "number" ? typography.font_size : null,
          font_weight: typography.font_weight || null,
          line_height: typeof typography.line_height === "number" ? typography.line_height : null,
          letter_spacing: typeof typography.letter_spacing === "number" ? typography.letter_spacing : null,
          align: typography.align || "",
        },
        layout: style.layout || {
          display: "",
          flex_direction: "",
          justify_content: "",
          align_items: "",
          gap: null,
          padding: { top: 0, right: 0, bottom: 0, left: 0 },
          margin: { top: 0, right: 0, bottom: 0, left: 0 },
        },
        image: style.image || { src: "", fit: "" },
      },
      analysis: c.analysis || {},
      children: Array.isArray(c.children) ? c.children : [],
    };
  }

  function getDoc() {
    return {
      schema: state.schema,
      image: {
        name: state.image.name || "",
        source: state.image.source || "",
        width: state.image.width || 0,
        height: state.image.height || 0,
      },
      components: state.components.map((c, idx) => componentToJson(c, idx)),
    };
  }

  function renderOverlay() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (!state.image.width) return;

    const ns = "http://www.w3.org/2000/svg";
    const styleEl = document.createElementNS(ns, "style");
    styleEl.textContent = `
      .anno-rect { fill: rgba(239, 68, 68, 0.08); stroke: rgba(239, 68, 68, 0.92); stroke-width: 2; }
      .anno-rect.selected { stroke: rgba(34, 197, 94, 0.96); fill: rgba(34, 197, 94, 0.10); }
      .anno-label-bg { fill: rgba(11, 18, 32, 0.70); }
      .anno-label { fill: rgba(239, 68, 68, 1); font: 12px ui-sans-serif, system-ui; dominant-baseline: hanging; }
      .anno-label.selected { fill: rgba(34, 197, 94, 1); }
    `;
    svg.appendChild(styleEl);

    for (const c of state.components) {
      const g = document.createElementNS(ns, "g");
      g.dataset.id = c.id;

      const r = document.createElementNS(ns, "rect");
      r.classList.add("anno-rect");
      r.dataset.id = c.id;
      r.setAttribute("x", String(c.bbox.x));
      r.setAttribute("y", String(c.bbox.y));
      r.setAttribute("width", String(c.bbox.w));
      r.setAttribute("height", String(c.bbox.h));
      r.setAttribute("rx", String((c.style && typeof c.style.radius === "number") ? c.style.radius : 0));
      r.setAttribute("ry", String((c.style && typeof c.style.radius === "number") ? c.style.radius : 0));
      r.style.pointerEvents = "all";

      const label = (c.name || c.type || "component").slice(0, 48);
      const x = c.bbox.x;
      const y = Math.max(0, c.bbox.y - 18);
      const bg = document.createElementNS(ns, "rect");
      bg.classList.add("anno-label-bg");
      bg.dataset.id = c.id;
      bg.setAttribute("x", String(x));
      bg.setAttribute("y", String(y));
      bg.setAttribute("width", String(Math.max(40, label.length * 7 + 10)));
      bg.setAttribute("height", "18");
      bg.setAttribute("rx", "8");
      bg.setAttribute("ry", "8");
      bg.style.pointerEvents = "none";

      const t = document.createElementNS(ns, "text");
      t.classList.add("anno-label");
      t.dataset.id = c.id;
      t.setAttribute("x", String(x + 6));
      t.setAttribute("y", String(y + 3));
      t.textContent = label;
      t.style.pointerEvents = "none";

      if (c.id === state.selectedId) {
        r.classList.add("selected");
        t.classList.add("selected");
      }

      g.appendChild(r);
      g.appendChild(bg);
      g.appendChild(t);
      svg.appendChild(g);
    }
  }

  function renderBlocks() {
    blocksEl.innerHTML = "";
    const doc = getDoc();
    const components = doc.components || [];
    if (componentCountEl) componentCountEl.textContent = components.length ? `${components.length} 个` : "0 个";

    for (const c of components) {
      const item = document.createElement("div");
      item.className = "annot_block" + (c.id === state.selectedId ? " selected" : "");
      item.dataset.id = c.id;

      const head = document.createElement("div");
      head.className = "annot_block_head";
      head.textContent = `${c.name || "(未命名)"} · ${c.type}`;

      const pre = document.createElement("pre");
      pre.className = "annot_block_code";
      pre.textContent = JSON.stringify(c, null, 2);

      item.appendChild(head);
      item.appendChild(pre);
      item.addEventListener("click", () => selectComponent(c.id, { scrollBlocks: false, focusCanvas: true }));
      blocksEl.appendChild(item);
    }
  }

  function renderJson() {
    jsonTextEl.value = JSON.stringify(getDoc(), null, 2);
  }

  function renderSelectedEditor() {
    const c = state.components.find((x) => x.id === state.selectedId) || null;
    if (selectedIdEl) selectedIdEl.textContent = c ? c.id : "";
    if (!nameInput || !typeSelect || !textInput || !bgColorInput || !textColorInput || !fontSizeInput || !radiusInput) return;

    if (!c) {
      nameInput.value = "";
      typeSelect.value = "unknown";
      textInput.value = "";
      bgColorInput.value = "#000000";
      textColorInput.value = "#ffffff";
      fontSizeInput.value = "";
      radiusInput.value = "";
      return;
    }

    nameInput.value = c.name || "";
    typeSelect.value = c.type || "unknown";
    textInput.value = (c.style && c.style.typography && c.style.typography.text) ? c.style.typography.text : "";

    const bg = (c.style && c.style.background && c.style.background.color) || (c.analysis && c.analysis.suggested_bg_color) || "#000000";
    const fg = (c.style && c.style.typography && c.style.typography.color) || (c.analysis && c.analysis.suggested_fg_color) || "#ffffff";
    bgColorInput.value = bg;
    textColorInput.value = fg;

    const fs = c.style && c.style.typography && c.style.typography.font_size;
    fontSizeInput.value = typeof fs === "number" ? String(fs) : "";

    const r = c.style && typeof c.style.radius === "number" ? c.style.radius : "";
    radiusInput.value = r === "" ? "" : String(r);
  }

  function renderAll() {
    renderOverlay();
    renderBlocks();
    renderJson();
    renderSelectedEditor();
  }

  function selectComponent(id, opts) {
    const options = opts || {};
    state.selectedId = id || null;
    renderAll();
    if (options.scrollBlocks !== false && id) {
      const el = blocksEl.querySelector(`[data-id="${CSS.escape(id)}"]`);
      if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    if (options.focusCanvas) viewport.focus();
  }

  function updateSelectedFromInputs() {
    const c = state.components.find((x) => x.id === state.selectedId) || null;
    if (!c) return;

    if (nameInput) c.name = (nameInput.value || "").trim();
    if (typeSelect) c.type = String(typeSelect.value || "unknown");

    c.style = c.style || {};
    c.style.background = c.style.background || {};
    c.style.border = c.style.border || {};
    c.style.typography = c.style.typography || {};

    if (textInput) c.style.typography.text = (textInput.value || "").trim();
    if (bgColorInput) c.style.background.color = bgColorInput.value || "";
    if (textColorInput) c.style.typography.color = textColorInput.value || "";

    if (fontSizeInput) {
      const v = (fontSizeInput.value || "").trim();
      c.style.typography.font_size = v ? parseFloat(v) : null;
    }
    if (radiusInput) {
      const v = (radiusInput.value || "").trim();
      c.style.radius = v ? parseFloat(v) : 0;
      c.style.border.radius = c.style.radius;
    }
    renderAll();
  }

  if (nameInput) nameInput.addEventListener("input", updateSelectedFromInputs);
  if (typeSelect) typeSelect.addEventListener("change", updateSelectedFromInputs);
  if (textInput) textInput.addEventListener("input", updateSelectedFromInputs);
  if (bgColorInput) bgColorInput.addEventListener("input", updateSelectedFromInputs);
  if (textColorInput) textColorInput.addEventListener("input", updateSelectedFromInputs);
  if (fontSizeInput) fontSizeInput.addEventListener("input", updateSelectedFromInputs);
  if (radiusInput) radiusInput.addEventListener("input", updateSelectedFromInputs);

  function downloadText(filename, text, mime) {
    const blob = new Blob([text], { type: mime || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      return false;
    }
  }

  if (downloadJsonBtn) {
    downloadJsonBtn.addEventListener("click", () => {
      const nameBase = (state.image.name || "ui") || "ui";
      const filename = nameBase.replace(/\.[a-z0-9]+$/i, "") + "_annotations.json";
      downloadText(filename, JSON.stringify(getDoc(), null, 2) + "\n", "application/json");
      setStatus("已下载 JSON。");
      setTimeout(() => setStatus(""), 1200);
    });
  }

  if (copyJsonBtn) {
    copyJsonBtn.addEventListener("click", async () => {
      const ok = await copyToClipboard(JSON.stringify(getDoc(), null, 2));
      setStatus(ok ? "已复制到剪贴板。" : "复制失败：请手动全选右侧 JSON。", ok ? "ok" : "error");
      setTimeout(() => setStatus(""), 1600);
    });
  }

  async function postJson(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok || !data || data.ok === false) {
      const msg = data && data.error ? data.error : `请求失败（HTTP ${resp.status}）`;
      throw new Error(msg);
    }
    return data;
  }

  async function postForm(url, formData) {
    const resp = await fetch(url, { method: "POST", body: formData, headers: { Accept: "application/json" } });
    const data = await resp.json().catch(() => null);
    if (!resp.ok || !data || data.ok === false) {
      const msg = data && data.error ? data.error : `请求失败（HTTP ${resp.status}）`;
      throw new Error(msg);
    }
    return data;
  }

  if (saveJsonBtn) {
    saveJsonBtn.addEventListener("click", async () => {
      try {
        setStatus("保存中…");
        const doc = getDoc();
        const data = await postJson(cfg.endpoints.saveJson, doc);
        const url = (data && (data.preview_url || data.download_url)) || "";
        setStatus(url ? `已生成 JSON 链接：${url}` : "已生成 JSON 链接。");
        if (data && data.download_url) {
          window.open(data.download_url, "_blank");
        }
        setTimeout(() => setStatus(""), 1600);
      } catch (e) {
        setStatus(String(e && e.message ? e.message : e), "error");
      }
    });
  }

  if (saveImageBtn) {
    saveImageBtn.addEventListener("click", async () => {
      try {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          setStatus("请先选择图片。", "error");
          return;
        }
        setStatus("上传中…");
        const fd = new FormData();
        fd.append("file", file);
        const data = await postForm(cfg.endpoints.uploadImage, fd);
        if (data && data.image_url) {
          state.image.source = data.image_url;
          state.image.name = data.filename || state.image.name;
          setImage(data.image_url, { name: state.image.name, source: data.image_url });
        }
        setStatus(data && data.image_url ? `已保存图片链接：${data.image_url}` : "已保存图片链接。");
        setTimeout(() => setStatus(""), 1600);
      } catch (e) {
        setStatus(String(e && e.message ? e.message : e), "error");
      }
    });
  }

  if (resetViewBtn) resetViewBtn.addEventListener("click", () => fitToViewport());
  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", () => {
      state.components = [];
      selectComponent(null, { scrollBlocks: false });
      renderAll();
      setStatus("已清空。");
      setTimeout(() => setStatus(""), 900);
    });
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    state.image.name = file.name || "ui.png";
    state.image.source = "";
    const url = URL.createObjectURL(file);
    setImage(url, { name: state.image.name, source: "" });
    setStatus("已加载图片（本地）。");
    setTimeout(() => setStatus(""), 900);
  });

  const interaction = {
    mode: "idle", // idle | pan | draw | move
    pointerId: null,
    start: { x: 0, y: 0 },
    startTx: 0,
    startTy: 0,
    startRect: null,
    activeId: null,
    tempRectEl: null,
  };

  function removeTempRect() {
    if (interaction.tempRectEl && interaction.tempRectEl.parentNode) {
      interaction.tempRectEl.parentNode.removeChild(interaction.tempRectEl);
    }
    interaction.tempRectEl = null;
  }

  function addTempRect() {
    const ns = "http://www.w3.org/2000/svg";
    const r = document.createElementNS(ns, "rect");
    r.setAttribute("fill", "rgba(239, 68, 68, 0.10)");
    r.setAttribute("stroke", "rgba(239, 68, 68, 0.92)");
    r.setAttribute("stroke-width", "2");
    r.style.pointerEvents = "none";
    svg.appendChild(r);
    interaction.tempRectEl = r;
  }

  function setTempRect(b) {
    if (!interaction.tempRectEl) addTempRect();
    interaction.tempRectEl.setAttribute("x", String(b.x));
    interaction.tempRectEl.setAttribute("y", String(b.y));
    interaction.tempRectEl.setAttribute("width", String(b.w));
    interaction.tempRectEl.setAttribute("height", String(b.h));
  }

  function findComponentById(id) {
    return state.components.find((c) => c.id === id) || null;
  }

  function elementComponentId(el) {
    if (!el) return null;
    const id = el.dataset && el.dataset.id;
    return id || null;
  }

  function onPointerDown(evt) {
    if (!state.image.width) return;
    const vp = getViewportPoint(evt);
    const w = screenToWorld(vp);

    const targetId = elementComponentId(evt.target);
    interaction.pointerId = evt.pointerId;
    interaction.start = { x: vp.x, y: vp.y };
    interaction.startTx = state.view.tx;
    interaction.startTy = state.view.ty;

    if (state.keys.space) {
      interaction.mode = "pan";
      viewport.setPointerCapture(evt.pointerId);
      return;
    }

    if (targetId) {
      selectComponent(targetId, { scrollBlocks: true, focusCanvas: true });
      const c = findComponentById(targetId);
      if (c) {
        interaction.mode = "move";
        interaction.activeId = targetId;
        interaction.startRect = { x: c.bbox.x, y: c.bbox.y, w: c.bbox.w, h: c.bbox.h };
        interaction.startWorld = w;
        viewport.setPointerCapture(evt.pointerId);
      }
      return;
    }

    interaction.mode = "draw";
    interaction.startWorld = w;
    interaction.startRect = { x: w.x, y: w.y, w: 0, h: 0 };
    removeTempRect();
    addTempRect();
    setTempRect(interaction.startRect);
    viewport.setPointerCapture(evt.pointerId);
  }

  function onPointerMove(evt) {
    if (!state.image.width) return;
    if (interaction.pointerId !== evt.pointerId) return;

    const vp = getViewportPoint(evt);
    const w = screenToWorld(vp);

    if (interaction.mode === "pan") {
      const dx = vp.x - interaction.start.x;
      const dy = vp.y - interaction.start.y;
      state.view.tx = interaction.startTx + dx;
      state.view.ty = interaction.startTy + dy;
      applyTransform();
      return;
    }

    if (interaction.mode === "draw") {
      const rect = normalizeRect(interaction.startWorld, w);
      rect.x = clamp(rect.x, 0, state.image.width);
      rect.y = clamp(rect.y, 0, state.image.height);
      rect.w = clamp(rect.w, 0, state.image.width - rect.x);
      rect.h = clamp(rect.h, 0, state.image.height - rect.y);
      interaction.startRect = rect;
      setTempRect(rect);
      return;
    }

    if (interaction.mode === "move") {
      const c = findComponentById(interaction.activeId);
      if (!c || !interaction.startRect) return;
      const dx = w.x - interaction.startWorld.x;
      const dy = w.y - interaction.startWorld.y;
      const next = {
        x: clamp(interaction.startRect.x + dx, 0, state.image.width - interaction.startRect.w),
        y: clamp(interaction.startRect.y + dy, 0, state.image.height - interaction.startRect.h),
        w: interaction.startRect.w,
        h: interaction.startRect.h,
      };
      c.bbox = next;
      c.analysis = analyzeBox(next) || c.analysis;
      renderOverlay();
      renderJson();
    }
  }

  function onPointerUp(evt) {
    if (interaction.pointerId !== evt.pointerId) return;
    try {
      viewport.releasePointerCapture(evt.pointerId);
    } catch (_) {}

    const prevMode = interaction.mode;
    if (interaction.mode === "draw") {
      const rect = interaction.startRect;
      removeTempRect();
      if (rect && rect.w >= 8 && rect.h >= 8) {
        const id = ensureId("cmp");
        const analysis = analyzeBox(rect);
        const name = `Component ${state.components.length + 1}`;
        state.components.push({
          id,
          name,
          type: "unknown",
          bbox: rect,
          analysis: analysis || {},
          style: {
            radius: 0,
            background: { color: analysis ? analysis.suggested_bg_color : "" },
            border: { color: "", width: 0, radius: 0 },
            typography: { text: "", color: analysis ? analysis.suggested_fg_color : "", font_size: null },
          },
          children: [],
        });
        selectComponent(id, { scrollBlocks: true, focusCanvas: true });
        setStatus("已新增组件。");
        setTimeout(() => setStatus(""), 800);
      }
    }

    interaction.mode = "idle";
    interaction.pointerId = null;
    interaction.activeId = null;
    interaction.startRect = null;
    // Ensure blocks reflect latest bbox after move.
    if (prevMode === "move") renderAll();
  }

  svg.addEventListener("pointerdown", onPointerDown);
  viewport.addEventListener("pointermove", onPointerMove);
  viewport.addEventListener("pointerup", onPointerUp);
  viewport.addEventListener("pointercancel", onPointerUp);

  viewport.addEventListener("wheel", (evt) => {
    if (!state.image.width) return;
    evt.preventDefault();
    const vp = getViewportPoint(evt);
    const mx = vp.x;
    const my = vp.y;
    const wx = (mx - state.view.tx) / state.view.scale;
    const wy = (my - state.view.ty) / state.view.scale;

    const delta = evt.deltaY;
    const factor = delta > 0 ? 0.92 : 1.08;
    const nextScale = clamp(state.view.scale * factor, state.view.minScale, state.view.maxScale);
    state.view.scale = nextScale;
    state.view.tx = mx - wx * nextScale;
    state.view.ty = my - wy * nextScale;
    applyTransform();
  }, { passive: false });

  window.addEventListener("resize", () => fitToViewport());

  function keyHandler(evt, down) {
    if (evt.code === "Space") {
      state.keys.space = down;
      if (down) {
        viewport.classList.add("pan_mode");
      } else {
        viewport.classList.remove("pan_mode");
      }
      evt.preventDefault();
    }
    if (!down && (evt.code === "Delete" || evt.code === "Backspace")) {
      if (!state.selectedId) return;
      const idx = state.components.findIndex((c) => c.id === state.selectedId);
      if (idx >= 0) {
        state.components.splice(idx, 1);
        selectComponent(null, { scrollBlocks: false, focusCanvas: true });
        renderAll();
        setStatus("已删除。");
        setTimeout(() => setStatus(""), 800);
      }
      evt.preventDefault();
    }
  }

  viewport.addEventListener("keydown", (evt) => keyHandler(evt, true));
  viewport.addEventListener("keyup", (evt) => keyHandler(evt, false));

  // Initial render: empty.
  renderAll();
  applyTransform();
}
