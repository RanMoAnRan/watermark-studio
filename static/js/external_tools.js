function setupExternalToolModal(cfg) {
  const openBtn = document.querySelector(cfg.openBtn);
  const modal = document.querySelector(cfg.modal);
  const backdrop = document.querySelector(cfg.backdrop);
  const closeBtns = Array.from(document.querySelectorAll(cfg.closeBtns));
  const form = document.querySelector(cfg.form);
  const status = document.querySelector(cfg.status);
  const title = cfg.title ? document.querySelector(cfg.title) : null;

  if (!openBtn || !modal || !backdrop || !form) return;

  const state = {
    editingId: "",
  };

  function show() {
    backdrop.style.display = "";
    modal.style.display = "";
    try {
      (form.querySelector("input[name='name']") || form.querySelector("input,select,textarea"))?.focus();
    } catch (_) {}
  }

  function hide() {
    backdrop.style.display = "none";
    modal.style.display = "none";
    if (status) status.textContent = "";
    state.editingId = "";
  }

  function setStatus(msg, kind) {
    if (!status) return;
    status.textContent = msg || "";
    status.style.color = kind === "error" ? "var(--danger)" : "";
  }

  openBtn.addEventListener("click", (evt) => {
    evt.preventDefault();
    state.editingId = "";
    if (title) title.textContent = "添加外链工具";
    try {
      form.reset();
      const checked = form.querySelector("input[name='open_new_tab']");
      if (checked) checked.checked = true;
    } catch (_) {}
    show();
  });
  backdrop.addEventListener("click", hide);
  closeBtns.forEach((b) => b.addEventListener("click", (evt) => {
    evt.preventDefault();
    hide();
  }));

  window.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape") hide();
  });

  function deleteUrlFor(id) {
    const base = cfg.endpoints && cfg.endpoints.deleteBase ? String(cfg.endpoints.deleteBase) : "";
    if (!base) return "";
    return base.replace("__id__", encodeURIComponent(String(id || "")));
  }

  function updateUrlFor(id) {
    const base = cfg.endpoints && cfg.endpoints.updateBase ? String(cfg.endpoints.updateBase) : "";
    if (!base) return "";
    return base.replace("__id__", encodeURIComponent(String(id || "")));
  }

  async function deleteTool(id) {
    const url = deleteUrlFor(id);
    if (!url) throw new Error("删除接口未配置。");
    const resp = await fetch(url, { method: "POST", headers: { Accept: "application/json" } });
    const out = await resp.json().catch(() => null);
    if (!resp.ok || !out || out.ok === false) {
      const msg = out && out.error ? out.error : `删除失败（HTTP ${resp.status}）`;
      throw new Error(msg);
    }
    return true;
  }

  async function upsertTool(payload) {
    const isEdit = !!state.editingId;
    const url = isEdit ? updateUrlFor(state.editingId) : (cfg.endpoints && cfg.endpoints.add);
    if (!url) throw new Error("保存接口未配置。");

    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const out = await resp.json().catch(() => null);
    if (!resp.ok || !out || out.ok === false) {
      const msg = out && out.error ? out.error : `${isEdit ? "更新" : "添加"}失败（HTTP ${resp.status}）`;
      throw new Error(msg);
    }
    return out;
  }

  function fillFormFromDataset(el) {
    const ds = el && el.dataset ? el.dataset : {};
    const name = ds.toolName || "";
    const url = ds.toolUrl || "";
    const description = ds.toolDescription || "";
    const category = ds.toolCategory || "other";
    const icon = ds.toolIcon || "";
    const openNewTab = ds.toolOpenNewTab !== "false";

    const nameEl = form.querySelector("input[name='name']");
    const urlEl = form.querySelector("input[name='url']");
    const descEl = form.querySelector("textarea[name='description']");
    const catEl = form.querySelector("select[name='category']");
    const iconEl = form.querySelector("input[name='icon']");
    const openEl = form.querySelector("input[name='open_new_tab']");

    if (nameEl) nameEl.value = name;
    if (urlEl) urlEl.value = url;
    if (descEl) descEl.value = description;
    if (catEl) catEl.value = category;
    if (iconEl) iconEl.value = icon;
    if (openEl) openEl.checked = openNewTab;
  }

  form.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    setStatus(state.editingId ? "更新中…" : "保存中…");

    const data = {
      name: (form.querySelector("input[name='name']")?.value || "").trim(),
      url: (form.querySelector("input[name='url']")?.value || "").trim(),
      description: (form.querySelector("textarea[name='description']")?.value || "").trim(),
      category: (form.querySelector("select[name='category']")?.value || "other").trim(),
      icon: (form.querySelector("input[name='icon']")?.value || "").trim(),
      open_new_tab: form.querySelector("input[name='open_new_tab']")?.checked !== false,
    };

    try {
      await upsertTool(data);
      setStatus(state.editingId ? "已更新，正在刷新…" : "已添加，正在刷新…");
      window.location.href = cfg.redirectTo || window.location.href;
    } catch (e) {
      setStatus(`请求失败：${e && e.message ? e.message : e}`, "error");
    }
  });

  // Delete Modal
  const delBackdrop = document.querySelector("#deleteModalBackdrop");
  const delModal = document.querySelector("#deleteModal");
  const delMsg = document.querySelector("#deleteModalMessage");
  const delConfirm = document.querySelector("#deleteModalConfirm");
  const delCloseBtns = document.querySelectorAll("[data-delete-modal-close]");
  
  let pendingDeleteId = null;
  let pendingDeleteBtn = null;

  function hideDeleteModal() {
    if (delBackdrop) delBackdrop.style.display = "none";
    if (delModal) delModal.style.display = "none";
    pendingDeleteId = null;
    pendingDeleteBtn = null;
  }

  if (delBackdrop) {
    delBackdrop.addEventListener("click", hideDeleteModal);
  }
  // Prevent clicks inside modal from closing backdrop
  if (delModal) {
    delModal.addEventListener("click", (e) => e.stopPropagation());
  }

  window.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape") {
      if (delBackdrop && delBackdrop.style.display !== "none") hideDeleteModal();
    }
  });

  delCloseBtns.forEach(b => b.addEventListener("click", (e) => { e.preventDefault(); hideDeleteModal(); }));

  if (delConfirm) {
    delConfirm.addEventListener("click", async () => {
      if (!pendingDeleteId || !pendingDeleteBtn) return;
      
      const btn = pendingDeleteBtn;
      const id = pendingDeleteId;
      hideDeleteModal();

      try {
        btn.setAttribute("disabled", "disabled");
        btn.classList.add("is_busy");
        await deleteTool(id);
        window.location.href = cfg.redirectTo || window.location.href;
      } catch (e) {
        btn.removeAttribute("disabled");
        btn.classList.remove("is_busy");
        setStatus(String(e && e.message ? e.message : e), "error");
        setTimeout(() => setStatus(""), 2200);
      }
    });
  }

  document.addEventListener("click", async (evt) => {
    const btn = evt.target && evt.target.closest ? evt.target.closest("[data-tool-delete]") : null;
    if (!btn) return;
    evt.preventDefault();
    evt.stopPropagation();
    const id = btn.getAttribute("data-tool-delete") || "";
    if (!id) return;
    const name = btn.getAttribute("data-tool-name") || "";
    
    pendingDeleteId = id;
    pendingDeleteBtn = btn;
    if (delMsg) delMsg.textContent = name ? `确定删除外链工具「${name}」？此操作无法撤销。` : "确定删除该外链工具？此操作无法撤销。";
    if (delBackdrop) delBackdrop.style.display = "";
    if (delModal) delModal.style.display = "";
  });

  document.addEventListener("click", async (evt) => {
    const btn = evt.target && evt.target.closest ? evt.target.closest("[data-tool-edit]") : null;
    if (!btn) return;
    evt.preventDefault();
    evt.stopPropagation();
    const id = btn.getAttribute("data-tool-edit") || "";
    if (!id) return;
    state.editingId = id;
    if (title) title.textContent = "编辑外链工具";
    fillFormFromDataset(btn);
    setStatus("");
    show();
  });
}
