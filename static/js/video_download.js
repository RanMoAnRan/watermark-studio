(function () {
  const qs = (sel) => document.querySelector(sel);
  const setText = (el, text) => {
    if (!el) return;
    el.textContent = text || "";
  };
  const showEl = (el) => {
    if (!el) return;
    el.style.display = "";
  };
  const hideEl = (el) => {
    if (!el) return;
    el.style.display = "none";
  };
  const escapeText = (text) => (text || "").replace(/\u0000/g, "");

  const form = qs("#videoDownloadForm");
  const clearBtn = qs("#videoClearBtn");
  const playBtn = qs("#videoPlayBtn");

  const taskCard = qs("#videoTaskCard");
  const taskMeta = qs("#videoTaskMeta");
  const statusEl = qs("#videoStatus");
  const statusHint = qs("#videoStatusHint");
  const logEl = qs("#videoLog");
  const autoScrollEl = qs("#videoAutoScroll");
  const zipBtn = qs("#videoZipBtn");
  const filesWrap = qs("#videoFilesWrap");
  const filesEl = qs("#videoFiles");

  const playerCard = qs("#videoPlayerCard");
  const player = qs("#videoPlayer");
  const playKindEl = qs("#videoPlayKind");
  const playHint = qs("#videoPlayHint");
  const playOpen = qs("#videoPlayOpen");

  let polling = false;
  let currentTaskId = "";
  let timer = null;

  function setError(msg) {
    const errBox = qs("#videoError");
    const errText = qs("#videoErrorText");
    if (msg) {
      showEl(errBox);
      setText(errText, msg);
    } else {
      hideEl(errBox);
      setText(errText, "");
    }
  }

  function updateUrl(taskId) {
    try {
      const u = new URL(window.location.href);
      if (taskId) u.searchParams.set("task", taskId);
      else u.searchParams.delete("task");
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (_) {}
  }

  function setLog(lines) {
    if (!logEl) return;
    const shouldScroll = !!(autoScrollEl && autoScrollEl.checked);
    const atBottom = (logEl.scrollTop + logEl.clientHeight + 12) >= logEl.scrollHeight;
    logEl.textContent = escapeText((lines || []).join("\n"));
    if (shouldScroll && (atBottom || !polling)) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  }

  function renderFiles(task) {
    if (!filesEl || !filesWrap) return;
    const results = task && task.results ? task.results : {};
    const files = Array.isArray(results.files) ? results.files : [];

    filesEl.innerHTML = "";
    if (!files.length) {
      hideEl(filesWrap);
      return;
    }
    showEl(filesWrap);

    const rank = (kind) => {
      if (kind === "video") return 0;
      if (kind === "subtitle") return 1;
      if (kind === "cover") return 2;
      return 9;
    };
    files.sort((a, b) => (rank(a.kind) - rank(b.kind)) || String(a.name).localeCompare(String(b.name)));

    for (const f of files) {
      const name = f.name || "";
      const kind = f.kind || "file";
      const downloadUrl = f.download_url || "";
      const previewUrl = f.preview_url || "";

      const col = document.createElement("div");
      col.className = "col-6";
      col.style.minWidth = "260px";

      const card = document.createElement("div");
      card.className = "card";
      card.style.margin = "0";

      const bd = document.createElement("div");
      bd.className = "bd";

      const title = document.createElement("div");
      title.style.fontWeight = "600";
      title.textContent = name;

      const meta = document.createElement("div");
      meta.className = "muted";
      meta.style.marginTop = "6px";
      meta.textContent = kind === "subtitle" ? "字幕" : (kind === "cover" ? "封面" : "视频/音频");

      const row = document.createElement("div");
      row.className = "row";
      row.style.marginTop = "10px";
      row.style.gap = "10px";

      const a = document.createElement("a");
      a.className = "btn primary";
      a.href = downloadUrl || "#";
      a.textContent = "下载";

      const b = document.createElement("a");
      b.className = "btn secondary";
      b.href = previewUrl || "#";
      b.target = "_blank";
      b.rel = "noopener";
      b.textContent = "打开";

      row.appendChild(a);
      row.appendChild(b);

      bd.appendChild(title);
      bd.appendChild(meta);
      bd.appendChild(row);
      card.appendChild(bd);
      col.appendChild(card);
      filesEl.appendChild(col);
    }
  }

  async function pollOnce() {
    if (!currentTaskId) return;
    try {
      const url = `/video/tasks/${encodeURIComponent(currentTaskId)}?_=${Date.now()}`;
      const resp = await fetch(url, { headers: { Accept: "application/json" } });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.ok === false) {
        throw new Error((data && data.error) ? data.error : `任务读取失败（HTTP ${resp.status}）`);
      }

      const task = data.task || {};
      setText(statusEl, task.status || "-");
      if (taskMeta) taskMeta.textContent = `#${currentTaskId.slice(-10)} · ${task.url || ""}`;

      setLog(data.log_tail || []);

      const zipUrl = data.zip_download_url || "";
      if (zipBtn) {
        if (zipUrl) {
          zipBtn.href = zipUrl;
          zipBtn.style.display = "";
        } else {
          zipBtn.style.display = "none";
        }
      }

      renderFiles(task);

      if (task.status === "failed") {
        statusHint.textContent = task.error ? `失败：${task.error}` : "失败";
        stopPolling();
      } else if (task.status === "done") {
        statusHint.textContent = "完成";
        stopPolling();
      } else {
        statusHint.textContent = "运行中…";
      }
    } catch (e) {
      statusHint.textContent = `轮询失败：${e && e.message ? e.message : e}`;
      stopPolling();
    }
  }

  function stopPolling() {
    polling = false;
    if (timer) clearInterval(timer);
    timer = null;
  }

  function startPolling(taskId) {
    currentTaskId = taskId || "";
    if (!currentTaskId) return;
    polling = true;
    if (taskCard) taskCard.style.display = "";
    updateUrl(currentTaskId);
    pollOnce();
    if (timer) clearInterval(timer);
    timer = setInterval(pollOnce, 1200);
  }

  function clearAll() {
    stopPolling();
    currentTaskId = "";
    updateUrl("");
    setError("");
    if (taskCard) taskCard.style.display = "none";
    if (logEl) logEl.textContent = "";
    if (zipBtn) zipBtn.style.display = "none";
    if (filesWrap) filesWrap.style.display = "none";
    if (filesEl) filesEl.innerHTML = "";
    setText(statusEl, "-");
    if (statusHint) statusHint.textContent = "";

    if (player) {
      try {
        player.pause();
      } catch (_) {}
      player.removeAttribute("src");
      player.load?.();
    }
    if (playerCard) playerCard.style.display = "none";
    if (playKindEl) playKindEl.textContent = "-";
    if (playHint) playHint.textContent = "";
    if (playOpen) playOpen.style.display = "none";
  }

  if (clearBtn) clearBtn.addEventListener("click", clearAll);

  if (form) {
    submitAjaxForm({
      form: "#videoDownloadForm",
      errorBox: "#videoError",
      errorText: "#videoErrorText",
      submitBtn: "button[type='submit']",
      submittingText: "启动中…",
      onStart: () => {
        setError("");
        if (statusHint) statusHint.textContent = "";
        if (taskCard) taskCard.style.display = "";
        if (logEl) logEl.textContent = "";
        hideEl(filesWrap);
        if (zipBtn) zipBtn.style.display = "none";
      },
      onSuccess: (data) => {
        const taskId = data.task_id || "";
        startPolling(taskId);
      },
    });
  }

  const initial = window.__WMS_VIDEO_INITIAL_TASK__ || "";
  if (initial) {
    startPolling(initial);
  }

  function loadHlsJs() {
    return new Promise((resolve, reject) => {
      if (window.Hls) return resolve(window.Hls);
      const sources = [
        "/static/vendor/hls/hls.min.js",
        "https://cdn.jsdelivr.net/npm/hls.js@1.5.15/dist/hls.min.js",
      ];

      let idx = 0;
      const tryNext = () => {
        if (idx >= sources.length) {
          reject(new Error("hls.js 加载失败（可能无网络/被拦截，或未放置本地文件）"));
          return;
        }
        const s = document.createElement("script");
        s.src = sources[idx++];
        s.async = true;
        s.onload = () => (window.Hls ? resolve(window.Hls) : tryNext());
        s.onerror = () => tryNext();
        document.head.appendChild(s);
      };
      tryNext();
    });
  }

  function setPlayUI({ kind, mediaUrl }) {
    if (playerCard) playerCard.style.display = "";
    if (playKindEl) playKindEl.textContent = kind || "-";
    if (playOpen) {
      if (mediaUrl) {
        playOpen.href = mediaUrl;
        playOpen.style.display = "";
      } else {
        playOpen.style.display = "none";
      }
    }
  }

  async function resolveAndPlay() {
    setError("");
    if (playHint) playHint.textContent = "";

    const urlInput = qs("#videoUrl");
    const url = (urlInput && urlInput.value) ? urlInput.value.trim() : "";
    if (!url) {
      setError("请输入视频链接。");
      return;
    }

    if (playBtn) playBtn.disabled = true;
    if (playHint) playHint.textContent = "解析中…";

    try {
      const fd = new FormData();
      fd.set("url", url);

      // Pass optional cookies settings to backend resolver (mainly for YouTube "not a bot").
      const cookiesFromBrowser = form && form.querySelector("input[name='cookies_from_browser']");
      const cookiesBrowser = form && form.querySelector("select[name='cookies_browser']");
      const cookiesProfile = form && form.querySelector("input[name='cookies_profile']");
      const cookiesFile = form && form.querySelector("input[name='cookies_file']");
      if (cookiesFromBrowser && cookiesFromBrowser.checked) {
        fd.set("cookies_from_browser", "on");
        if (cookiesBrowser && cookiesBrowser.value) fd.set("cookies_browser", cookiesBrowser.value);
        if (cookiesProfile && cookiesProfile.value) fd.set("cookies_profile", cookiesProfile.value);
      }
      if (cookiesFile && cookiesFile.files && cookiesFile.files.length > 0) {
        fd.set("cookies_file", cookiesFile.files[0]);
      }

      const resp = await fetch("/video/play/resolve", {
        method: "POST",
        body: fd,
        headers: { Accept: "application/json" },
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.ok === false) {
        throw new Error((data && data.error) ? data.error : `解析失败（HTTP ${resp.status}）`);
      }

      const kind = data.kind || "file";
      const mediaUrl = data.media_url || "";
      const playUrl = data.play_url || "";
      const hlsUrl = data.hls_url || "";

      setPlayUI({ kind, mediaUrl });

      if (!player) return;

      // Cleanup previous attachments.
      try {
        player.pause();
      } catch (_) {}
      player.removeAttribute("src");
      player.load?.();

      if (kind === "hls") {
        // Safari can play HLS natively, Chrome/Edge need hls.js.
        const canNative = !!player.canPlayType && player.canPlayType("application/vnd.apple.mpegurl");
        if (canNative) {
          player.src = hlsUrl;
          await player.play().catch(() => {});
          if (playHint) playHint.textContent = "";
          return;
        }

        const Hls = await loadHlsJs();
        if (!Hls || !Hls.isSupported()) {
          throw new Error("当前浏览器不支持 HLS 播放（建议改用下载）。");
        }
        const hls = new Hls({ enableWorker: true });
        hls.loadSource(hlsUrl);
        hls.attachMedia(player);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          player.play().catch(() => {});
        });
        if (playHint) playHint.textContent = "";
        return;
      }

      player.src = playUrl;
      await player.play().catch(() => {});
      if (playHint) playHint.textContent = "";
    } catch (e) {
      if (playHint) playHint.textContent = "";
      setError(e && e.message ? e.message : String(e));
    } finally {
      if (playBtn) playBtn.disabled = false;
    }
  }

  if (playBtn) playBtn.addEventListener("click", resolveAndPlay);
})();
