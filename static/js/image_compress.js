function clamp01(v) {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

function parseAspectRatio(value, imgEl) {
  if (!value) return NaN;
  if (value === "free") return NaN;
  if (value === "original") {
    if (!imgEl || !imgEl.naturalWidth || !imgEl.naturalHeight) return NaN;
    return imgEl.naturalWidth / imgEl.naturalHeight;
  }
  if (value === "id_1inch") return 25 / 35;
  if (value === "id_2inch") return 35 / 49;
  if (value === "print_4r") return 4 / 6;
  if (value === "print_5r") return 5 / 7;
  if (value === "print_6r") return 6 / 8;
  if (value === "a4") return 1 / 1.41421356237;
  const parts = String(value).split(":");
  if (parts.length === 2) {
    const a = Number(parts[0]);
    const b = Number(parts[1]);
    if (a > 0 && b > 0) return a / b;
  }
  return NaN;
}

function fmtPx(n) {
  if (!isFinite(n)) return "-";
  return `${Math.max(0, Math.round(n))}px`;
}

function setupImageCompress(cfg) {
  const form = document.querySelector(cfg.form);
  const fileInput = document.querySelector(cfg.fileInput);
  const imageEl = document.querySelector(cfg.image);

  const ratioSelect = document.querySelector(cfg.ratioSelect);
  const formatSelect = document.querySelector(cfg.formatSelect);
  const preserveAlpha = document.querySelector(cfg.preserveAlpha);
  const background = document.querySelector(cfg.background);
  const alphaHint = document.querySelector(cfg.alphaHint);

  const cropInfo = document.querySelector(cfg.cropInfo);
  const originalSize = document.querySelector(cfg.originalSize);
  const outW = document.querySelector(cfg.outW);
  const outH = document.querySelector(cfg.outH);
  const outHint = document.querySelector(cfg.outHint);

  const cropPxW = document.querySelector(cfg.cropPxW);
  const cropPxH = document.querySelector(cfg.cropPxH);

  const cropX = document.querySelector(cfg.cropX);
  const cropY = document.querySelector(cfg.cropY);
  const cropW = document.querySelector(cfg.cropW);
  const cropH = document.querySelector(cfg.cropH);

  const resetBtn = document.querySelector(cfg.resetBtn);
  const centerBtn = document.querySelector(cfg.centerBtn);

  if (!form || !fileInput || !imageEl || !cropX || !cropY || !cropW || !cropH) return;

  let cropper = null;
  let objectUrl = null;

  function setCropInputs(nx, ny, nw, nh) {
    cropX.value = nx != null ? String(nx) : "";
    cropY.value = ny != null ? String(ny) : "";
    cropW.value = nw != null ? String(nw) : "";
    cropH.value = nh != null ? String(nh) : "";
  }

  function updateAlphaUI() {
    const fmt = formatSelect ? String(formatSelect.value || "auto") : "auto";
    const wantsAlpha = preserveAlpha ? Boolean(preserveAlpha.checked) : true;
    if (fmt === "jpeg") {
      if (preserveAlpha) {
        preserveAlpha.checked = false;
        preserveAlpha.disabled = true;
      }
      if (alphaHint) alphaHint.textContent = "JPEG 不支持透明：将使用背景色填充透明区域。";
    } else {
      if (preserveAlpha) preserveAlpha.disabled = false;
      if (alphaHint) {
        alphaHint.textContent = wantsAlpha
          ? "选择 JPEG 时将自动填充背景色（不支持透明）。"
          : "未勾选“保留透明”：将使用背景色填充透明区域后再输出。";
      }
    }
    if (background) background.disabled = !(fmt === "jpeg" || !wantsAlpha);
  }

  function updateOriginalSizeText() {
    if (!originalSize) return;
    const file = fileInput.files && fileInput.files[0];
    if (!file || typeof file.size !== "number") {
      originalSize.textContent = "";
      return;
    }
    const bytes = file.size;
    const mb = bytes / (1024 * 1024);
    if (mb >= 1) {
      originalSize.textContent = `原图：${mb >= 10 ? mb.toFixed(0) : mb.toFixed(1)} MB`;
      return;
    }
    originalSize.textContent = `原图：${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  function getCropData() {
    if (!cropper) return null;
    const data = cropper.getData();
    const iw = imageEl.naturalWidth || 0;
    const ih = imageEl.naturalHeight || 0;
    if (!iw || !ih) return null;
    const nx = clamp01(data.x / iw);
    const ny = clamp01(data.y / ih);
    const nw = clamp01(data.width / iw);
    const nh = clamp01(data.height / ih);
    return { nx, ny, nw, nh, iw, ih, pxW: data.width, pxH: data.height };
  }

  function updateCropPxInputs() {
    if (!cropPxW || !cropPxH) return;
    if (!cropper) {
      cropPxW.value = "";
      cropPxH.value = "";
      return;
    }
    const data = cropper.getData();
    cropPxW.value = String(Math.max(1, Math.round(data.width)));
    cropPxH.value = String(Math.max(1, Math.round(data.height)));
  }

  function applyCropSizeFromInputs(changed) {
    if (!cropper) return;
    if (!cropPxW || !cropPxH) return;

    const iw = imageEl.naturalWidth || 0;
    const ih = imageEl.naturalHeight || 0;
    if (!iw || !ih) return;

    const cur = cropper.getData();
    const readNum = (el) => {
      const raw = (el && el.value != null) ? String(el.value).trim() : "";
      if (!raw) return null;
      const v = Number(raw);
      if (!isFinite(v)) return null;
      return v;
    };

    let w = readNum(cropPxW);
    let h = readNum(cropPxH);

    const aspect = cropper.options && isFinite(cropper.options.aspectRatio) ? cropper.options.aspectRatio : NaN;

    if (w == null && h == null) return;

    if (isFinite(aspect) && aspect > 0) {
      if (w != null && h != null) {
        if (changed === "w") {
          h = w / aspect;
        } else if (changed === "h") {
          w = h * aspect;
        } else {
          h = w / aspect;
        }
      } else if (w != null && h == null) {
        h = w / aspect;
      } else if (h != null && w == null) {
        w = h * aspect;
      }
    }

    if (w == null) w = cur.width;
    if (h == null) h = cur.height;

    w = Math.max(1, Math.round(w));
    h = Math.max(1, Math.round(h));

    const cx = cur.x + cur.width / 2;
    const cy = cur.y + cur.height / 2;
    let x = Math.round(cx - w / 2);
    let y = Math.round(cy - h / 2);
    x = Math.max(0, Math.min(iw - 1, x));
    y = Math.max(0, Math.min(ih - 1, y));
    w = Math.min(w, iw - x);
    h = Math.min(h, ih - y);

    cropper.setData({ x, y, width: w, height: h });
    updateCropUI();
  }

  function updateOutHint() {
    if (!outHint) return;
    if (!cropper) {
      outHint.textContent = "留空：按裁剪区域原分辨率输出（更清晰，但可能更大）。";
      return;
    }
    const c = getCropData();
    if (!c || !c.pxW || !c.pxH) {
      outHint.textContent = "留空：按裁剪区域原分辨率输出（更清晰，但可能更大）。";
      return;
    }
    const aspect = c.pxW / c.pxH;
    const ow = outW && outW.value ? Number(outW.value) : null;
    const oh = outH && outH.value ? Number(outH.value) : null;
    if (ow && !oh) {
      outHint.textContent = `将按裁剪比例自动计算高度：约 ${fmtPx(ow / aspect)}。`;
      return;
    }
    if (oh && !ow) {
      outHint.textContent = `将按裁剪比例自动计算宽度：约 ${fmtPx(oh * aspect)}。`;
      return;
    }
    outHint.textContent = "留空：按裁剪区域原分辨率输出（更清晰，但可能更大）。";
  }

  function updateCropUI() {
    if (!cropInfo) return;
    if (!cropper || !imageEl.src) {
      cropInfo.textContent = "未选择图片。";
      updateCropPxInputs();
      updateOriginalSizeText();
      return;
    }
    const c = getCropData();
    if (!c) {
      cropInfo.textContent = "裁剪信息获取失败。";
      updateCropPxInputs();
      updateOriginalSizeText();
      return;
    }
    setCropInputs(c.nx.toFixed(6), c.ny.toFixed(6), c.nw.toFixed(6), c.nh.toFixed(6));
    const msg = `裁剪区域：${fmtPx(c.pxW)} × ${fmtPx(c.pxH)}（基于原图 ${c.iw}×${c.ih}）`;
    cropInfo.textContent = msg;
    updateCropPxInputs();
    updateOriginalSizeText();
    updateOutHint();
  }

  function applyAspectRatio() {
    if (!cropper || !ratioSelect) return;
    const r = parseAspectRatio(String(ratioSelect.value || "original"), imageEl);
    cropper.setAspectRatio(r);
    updateCropUI();
  }

  function centerCrop() {
    if (!cropper) return;
    const imageData = cropper.getImageData();
    const iw = imageData.naturalWidth || imageEl.naturalWidth || 0;
    const ih = imageData.naturalHeight || imageEl.naturalHeight || 0;
    if (!iw || !ih) return;

    let r = cropper.options.aspectRatio;
    if (!isFinite(r) || r <= 0) r = iw / ih;

    let w = iw;
    let h = w / r;
    if (h > ih) {
      h = ih;
      w = h * r;
    }
    w = Math.max(1, w * 0.92);
    h = Math.max(1, h * 0.92);
    const x = (iw - w) / 2;
    const y = (ih - h) / 2;
    cropper.setData({ x, y, width: w, height: h });
    updateCropUI();
  }

  function destroyCropper() {
    if (cropper) {
      cropper.destroy();
      cropper = null;
    }
  }

  function revokeObjectUrl() {
    if (!objectUrl) return;
    try {
      URL.revokeObjectURL(objectUrl);
    } catch (_) {
      // ignore
    }
    objectUrl = null;
  }

  function initCropper() {
    destroyCropper();
    if (!imageEl.src) return;

    cropper = new Cropper(imageEl, {
      viewMode: 1,
      background: false,
      autoCropArea: 0.92,
      responsive: true,
      dragMode: "move",
      crop: () => updateCropUI(),
    });
    applyAspectRatio();
    updateAlphaUI();
    updateCropUI();
  }

  function restoreIfNeeded() {
    if (cropper) return;
    if (!imageEl) return;

    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      revokeObjectUrl();
      destroyCropper();
      imageEl.removeAttribute("src");
      setCropInputs(null, null, null, null);
      updateCropUI();
      return;
    }

    if (imageEl.src && imageEl.complete && (imageEl.naturalWidth || 0) > 0) {
      initCropper();
      updateCropUI();
      return;
    }

    revokeObjectUrl();
    objectUrl = URL.createObjectURL(file);
    imageEl.onload = () => {
      initCropper();
      centerCrop();
    };
    imageEl.src = objectUrl;
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    setCropInputs(null, null, null, null);
    destroyCropper();
    revokeObjectUrl();
    if (!file) {
      imageEl.removeAttribute("src");
      updateCropUI();
      return;
    }

    objectUrl = URL.createObjectURL(file);
    imageEl.onload = () => {
      initCropper();
      centerCrop();
    };
    imageEl.src = objectUrl;
  });

  ratioSelect && ratioSelect.addEventListener("change", () => applyAspectRatio());
  formatSelect && formatSelect.addEventListener("change", () => updateAlphaUI());
  preserveAlpha && preserveAlpha.addEventListener("change", () => updateAlphaUI());
  outW && outW.addEventListener("input", () => updateOutHint());
  outH && outH.addEventListener("input", () => updateOutHint());
  cropPxW && cropPxW.addEventListener("change", () => applyCropSizeFromInputs("w"));
  cropPxH && cropPxH.addEventListener("change", () => applyCropSizeFromInputs("h"));

  resetBtn && resetBtn.addEventListener("click", (evt) => {
    evt.preventDefault();
    if (!cropper) return;
    cropper.reset();
    applyAspectRatio();
    centerCrop();
  });

  centerBtn && centerBtn.addEventListener("click", (evt) => {
    evt.preventDefault();
    centerCrop();
  });

  form.addEventListener(
    "submit",
    () => {
      updateAlphaUI();
      updateCropUI();
    },
    true,
  );

  window.addEventListener("pageshow", () => restoreIfNeeded());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) restoreIfNeeded();
  });
  window.addEventListener("pagehide", () => {
    destroyCropper();
    revokeObjectUrl();
    imageEl.removeAttribute("src");
    setCropInputs(null, null, null, null);
  });

  updateAlphaUI();
  updateCropUI();
  restoreIfNeeded();
}
