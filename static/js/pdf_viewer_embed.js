(() => {
  const fileUrl = window.__WMS_PDF_VIEWER_FILE__;
  const initialPage = Math.max(1, parseInt(window.__WMS_PDF_VIEWER_PAGE__ || "1", 10) || 1);
  const renderIntent = (window.__WMS_PDF_VIEWER_INTENT__ === "print") ? "print" : "display";

  const scroller = document.getElementById("pdfScroller");
  const statusEl = document.getElementById("pdfStatus");
  const fileInfoEl = document.getElementById("pdfFileInfo");
  const openLink = document.getElementById("pdfOpenLink");

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function setFileInfo(url) {
    if (!fileInfoEl) return;
    const raw = url || "";
    const m = raw.match(/\/files\/([a-f0-9]{8,})/i);
    fileInfoEl.textContent = m ? `#${m[1].slice(-10)}` : raw ? `#${raw}` : "";
  }

  function ensureScroller() {
    if (!scroller) {
      throw new Error("Missing scroller element.");
    }
    return scroller;
  }

  function clamp01(x) {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    return x;
  }

  function getScrollRatio() {
    const el = ensureScroller();
    const max = el.scrollHeight - el.clientHeight;
    if (max <= 0) return 0;
    return el.scrollTop / max;
  }

  function setScrollRatio(ratio) {
    const el = ensureScroller();
    const max = el.scrollHeight - el.clientHeight;
    if (max <= 0) return;
    el.scrollTop = clamp01(ratio) * max;
  }

  function getScrollPosition() {
    const el = ensureScroller();
    const top = el.scrollTop;
    const pages = el.querySelectorAll(".pdf-page");
    if (!pages || pages.length === 0) {
      return { page: 1, offset: 0 };
    }

    let current = pages[0];
    for (let i = 0; i < pages.length; i += 1) {
      const p = pages[i];
      if (p.offsetTop <= top + 1) current = p;
      else break;
    }

    const pageNum = Math.max(1, parseInt(current.dataset.pageNumber || "1", 10) || 1);
    const denom = Math.max(1, current.clientHeight);
    const offsetFrac = (top - current.offsetTop) / denom;
    return { page: pageNum, offset: clamp01(offsetFrac) };
  }

  function setScrollPosition(pos) {
    if (!pos) return;
    const el = ensureScroller();
    const pageNum = Math.max(1, parseInt(pos.page || "1", 10) || 1);
    const offset = clamp01(pos.offset || 0);
    const pageEl = el.querySelector(`.pdf-page[data-page-number='${pageNum}']`);
    if (!pageEl) {
      // Fallback: approximate by whole-document ratio if page isn't found.
      setScrollRatio(offset);
      return;
    }
    const y = pageEl.offsetTop + offset * Math.max(1, pageEl.clientHeight);
    el.scrollTop = Math.max(0, y);
  }

  function goToPage(page) {
    const p = Math.max(1, parseInt(page || "1", 10) || 1);
    const el = ensureScroller();
    const pageEl = el.querySelector(`.pdf-page[data-page-number='${p}']`);
    if (!pageEl) return;
    el.scrollTop = Math.max(0, pageEl.offsetTop - 8);
  }

  window.__WMS_PDF_VIEWER__ = {
    getScrollRatio,
    setScrollRatio,
    getScrollPosition,
    setScrollPosition,
    goToPage,
    getScrollElement: () => ensureScroller(),
  };

  window.addEventListener("message", (e) => {
    if (e.origin !== window.location.origin) return;
    const msg = e.data;
    if (!msg || msg.ns !== "wms-pdf-viewer") return;
    if (msg.type === "set-scroll-ratio") setScrollRatio(msg.ratio);
    if (msg.type === "go-page") goToPage(msg.page);
  });

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`Failed to load: ${src}`));
      document.head.appendChild(script);
    });
  }

  async function loadPdfJs() {
    const localLib = "/static/vendor/pdfjs/pdf.min.js";
    const localWorker = "/static/vendor/pdfjs/pdf.worker.min.js";
    try {
      await loadScript(localLib);
    } catch (_) {
      await loadScript("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js");
    }
    if (!window.pdfjsLib) {
      throw new Error("PDF.js 未加载。");
    }
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = localWorker;
    return window.pdfjsLib;
  }

  async function renderPdf(pdfjsLib) {
    if (!fileUrl) {
      setStatus("缺少 PDF 地址。");
      return;
    }
    if (openLink) openLink.href = fileUrl;
    setFileInfo(fileUrl);

    setStatus("正在加载 PDF…");
    const loadingTask = pdfjsLib.getDocument({ url: fileUrl });
    const pdf = await loadingTask.promise;

    const container = ensureScroller();
    container.innerHTML = "";

    const firstPage = await pdf.getPage(1);
    const baseViewport = firstPage.getViewport({ scale: 1 });
    const availableWidth = Math.max(240, container.clientWidth - 24);
    const scale = Math.max(0.5, Math.min(2.0, availableWidth / baseViewport.width));

    const pageSizes = new Map();
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum += 1) {
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale });
      pageSizes.set(pageNum, {
        width: Math.floor(viewport.width),
        height: Math.floor(viewport.height),
      });

      const pageEl = document.createElement("div");
      pageEl.className = "pdf-page";
      pageEl.dataset.pageNumber = String(pageNum);
      pageEl.style.width = `${Math.floor(viewport.width)}px`;
      pageEl.style.height = `${Math.floor(viewport.height)}px`;

      const placeholder = document.createElement("div");
      placeholder.className = "placeholder";
      placeholder.textContent = `第 ${pageNum} 页`;
      pageEl.appendChild(placeholder);
      container.appendChild(pageEl);
    }

    setStatus(`共 ${pdf.numPages} 页`);

    const rendered = new Set();
    const rendering = new Set();

    async function renderPage(pageNum) {
      if (rendered.has(pageNum) || rendering.has(pageNum)) return;
      rendering.add(pageNum);
      try {
        const pageEl = container.querySelector(`.pdf-page[data-page-number='${pageNum}']`);
        if (!pageEl) return;

        const size = pageSizes.get(pageNum);
        const cssWidth = size ? size.width : Math.max(240, container.clientWidth - 24);
        const cssHeight = size ? size.height : 360;

        const dpr = window.devicePixelRatio || 1;
        const page = await pdf.getPage(pageNum);
        const viewportCss = page.getViewport({ scale });
        const viewport = page.getViewport({ scale: scale * dpr });

        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${cssWidth}px`;
        canvas.style.height = `${cssHeight}px`;

        const ctx = canvas.getContext("2d", { alpha: false });
        const renderTask = page.render({
          canvasContext: ctx,
          viewport,
          intent: renderIntent,
          // Important for comparison: many PDF watermarks are annotations (Stamp/Watermark),
          // which won't show up in a plain canvas render unless we enable annotation rendering.
          annotationMode: pdfjsLib.AnnotationMode ? pdfjsLib.AnnotationMode.ENABLE : undefined,
        });
        await renderTask.promise;

        pageEl.innerHTML = "";
        pageEl.appendChild(canvas);

        // Optional layers: text/annotations (helps with annotation-based watermarks).
        try {
          const annotationLayer = document.createElement("div");
          annotationLayer.className = "annotationLayer";
          pageEl.appendChild(annotationLayer);

          const annotations = await page.getAnnotations({ intent: renderIntent });
          const linkService = {
            getDestinationHash: () => "#",
            getAnchorUrl: () => "#",
            goToDestination: () => {},
            addLinkAttributes: (link) => {
              if (!link) return;
              link.rel = "noopener noreferrer";
              link.target = "_blank";
            },
          };

          if (pdfjsLib.AnnotationLayer && typeof pdfjsLib.AnnotationLayer.render === "function") {
            await pdfjsLib.AnnotationLayer.render({
              annotations,
              div: annotationLayer,
              page,
              viewport: viewportCss,
              linkService,
              renderForms: false,
            });
          }
        } catch (_) {}

        try {
          const textLayer = document.createElement("div");
          textLayer.className = "textLayer";
          pageEl.appendChild(textLayer);
          const textContent = await page.getTextContent();
          if (typeof pdfjsLib.renderTextLayer === "function") {
            await pdfjsLib.renderTextLayer({
              textContent,
              container: textLayer,
              viewport: viewportCss,
              textDivs: [],
            });
          }
        } catch (_) {}

        rendered.add(pageNum);
      } finally {
        rendering.delete(pageNum);
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const pageNum = parseInt(entry.target.dataset.pageNumber || "0", 10);
          if (pageNum > 0) void renderPage(pageNum);
        }
      },
      { root: container, rootMargin: "800px 0px" },
    );

    container.querySelectorAll(".pdf-page").forEach((el) => observer.observe(el));

    // Render the initial viewport quickly.
    for (let p = initialPage; p <= Math.min(pdf.numPages, initialPage + 2); p += 1) {
      void renderPage(p);
    }
    goToPage(initialPage);
  }

  (async () => {
    try {
      const pdfjsLib = await loadPdfJs();
      await renderPdf(pdfjsLib);
    } catch (err) {
      setStatus(`预览失败：${err && err.message ? err.message : String(err)}`);
      const el = ensureScroller();
      el.innerHTML = "";
      const msg = document.createElement("div");
      msg.className = "muted";
      msg.style.padding = "12px";
      msg.textContent = "PDF 预览加载失败，请使用右上角“在新窗口打开”或直接下载查看。";
      el.appendChild(msg);
    }
  })();
})();
