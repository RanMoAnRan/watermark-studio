function clamp01(v) {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

function setupRegionSelector(cfg) {
  const fileInput = document.querySelector(cfg.fileInput);
  const canvas = document.querySelector(cfg.canvas);
  const previewBox = cfg.previewBox ? document.querySelector(cfg.previewBox) : null;
  const hint = document.querySelector(cfg.hint);

  const xInput = document.querySelector(cfg.xInput);
  const yInput = document.querySelector(cfg.yInput);
  const wInput = document.querySelector(cfg.wInput);
  const hInput = document.querySelector(cfg.hInput);
  const regionsInput = document.querySelector(cfg.regionsInput);

  if (!fileInput || !canvas || !xInput || !yInput || !wInput || !hInput) return;

  const ctx = canvas.getContext("2d");
  const img = new Image();
  let dragging = false;
  let startX = 0;
  let startY = 0;
  let activeRect = null;
  let regions = [];

  function showPreview() {
    if (!previewBox) return;
    previewBox.style.display = "";
  }

  function hidePreview() {
    if (!previewBox) return;
    previewBox.style.display = "none";
  }

  function clearRectInputs() {
    xInput.value = "";
    yInput.value = "";
    wInput.value = "";
    hInput.value = "";
    if (regionsInput) regionsInput.value = "";
  }

  function draw() {
    if (!img.src) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    function drawOne(r, stroke, fill) {
      ctx.save();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 6]);
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.fillStyle = fill;
      ctx.fillRect(r.x, r.y, r.w, r.h);
      ctx.restore();
    }
    regions.forEach((r) => drawOne(r, "rgba(124, 58, 237, 0.95)", "rgba(124, 58, 237, 0.14)"));
    if (activeRect) drawOne(activeRect, "rgba(34, 197, 94, 0.95)", "rgba(34, 197, 94, 0.14)");
  }

  function canvasPointFromEvent(evt) {
    const r = canvas.getBoundingClientRect();
    const x = (evt.clientX - r.left) * (canvas.width / r.width);
    const y = (evt.clientY - r.top) * (canvas.height / r.height);
    return { x, y };
  }

  function updateNormalizedInputs() {
    if (!regions.length) {
      clearRectInputs();
      if (hint) hint.textContent = "未选择区域：将尝试自动去水印。";
      return;
    }
    const first = regions[0];
    const nx = clamp01(first.x / canvas.width);
    const ny = clamp01(first.y / canvas.height);
    const nw = clamp01(first.w / canvas.width);
    const nh = clamp01(first.h / canvas.height);
    xInput.value = nx.toFixed(6);
    yInput.value = ny.toFixed(6);
    wInput.value = nw.toFixed(6);
    hInput.value = nh.toFixed(6);

    const payload = regions.map((rr) => ({
      x: clamp01(rr.x / canvas.width),
      y: clamp01(rr.y / canvas.height),
      w: clamp01(rr.w / canvas.width),
      h: clamp01(rr.h / canvas.height),
    }));
    if (regionsInput) regionsInput.value = JSON.stringify(payload);
    if (hint) hint.textContent = `已选择 ${regions.length} 个区域：仅对这些区域去水印（可重复框选，点“撤销/清除”修改）。`;
  }

  function normalizeRect(a, b) {
    const x1 = Math.min(a.x, b.x);
    const y1 = Math.min(a.y, b.y);
    const x2 = Math.max(a.x, b.x);
    const y2 = Math.max(a.y, b.y);
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    activeRect = null;
    regions = [];
    clearRectInputs();
    if (!file) {
      img.removeAttribute("src");
      hidePreview();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const url = URL.createObjectURL(file);
    img.onload = () => {
      const maxW = 1100;
      const scale = img.width > maxW ? (maxW / img.width) : 1;
      canvas.width = Math.floor(img.width * scale);
      canvas.height = Math.floor(img.height * scale);
      showPreview();
      draw();
      updateNormalizedInputs();
    };
    img.src = url;
  });

  canvas.addEventListener("mousedown", (evt) => {
    if (!img.src) return;
    dragging = true;
    const p = canvasPointFromEvent(evt);
    startX = p.x;
    startY = p.y;
    activeRect = { x: startX, y: startY, w: 0, h: 0 };
    draw();
  });

  canvas.addEventListener("mousemove", (evt) => {
    if (!dragging || !img.src) return;
    const p = canvasPointFromEvent(evt);
    activeRect = normalizeRect({ x: startX, y: startY }, p);
    draw();
  });

  function endDrag(evt) {
    if (!dragging) return;
    dragging = false;
    if (!activeRect) return;
    if (activeRect.w < 6 || activeRect.h < 6) {
      activeRect = null;
      updateNormalizedInputs();
      draw();
      return;
    }
    regions.push(activeRect);
    activeRect = null;
    updateNormalizedInputs();
    draw();
  }

  canvas.addEventListener("mouseup", endDrag);
  canvas.addEventListener("mouseleave", endDrag);

  document.querySelector(cfg.clearBtn)?.addEventListener("click", (evt) => {
    evt.preventDefault();
    activeRect = null;
    regions = [];
    updateNormalizedInputs();
    draw();
  });

  document.querySelector(cfg.undoBtn)?.addEventListener("click", (evt) => {
    evt.preventDefault();
    if (regions.length) regions.pop();
    activeRect = null;
    updateNormalizedInputs();
    draw();
  });
}
