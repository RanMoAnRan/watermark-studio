function show(el) {
  if (!el) return;
  el.style.display = "";
}

function hide(el) {
  if (!el) return;
  el.style.display = "none";
}

function setText(el, text) {
  if (!el) return;
  el.textContent = text || "";
}

async function submitAjaxForm(cfg) {
  const form = document.querySelector(cfg.form);
  if (!form) return;

  form.addEventListener("submit", async (evt) => {
    evt.preventDefault();

    const errorBox = document.querySelector(cfg.errorBox);
    const errorText = document.querySelector(cfg.errorText);
    if (errorBox) hide(errorBox);
    if (errorText) setText(errorText, "");

    const submitBtn = form.querySelector(cfg.submitBtn) || form.querySelector("button[type='submit']");
    const originalBtnText = submitBtn ? submitBtn.textContent : null;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = cfg.submittingText || "处理中…";
    }

    try {
      const methodAttr = form.getAttribute("method") || "POST";
      const httpMethod = String(methodAttr).toUpperCase();
      const actionUrl = form.getAttribute("action") || form.action;
      const resp = await fetch(actionUrl, {
        method: httpMethod,
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.ok === false) {
        const msg = (data && data.error) ? data.error : `处理失败（HTTP ${resp.status}）。`;
        if (errorBox) show(errorBox);
        if (errorText) setText(errorText, msg);
        if (cfg.onError) cfg.onError(msg, data);
        return;
      }

      if (cfg.onSuccess) cfg.onSuccess(data);
    } catch (e) {
      const msg = `请求失败：${e && e.message ? e.message : e}`;
      if (errorBox) show(errorBox);
      if (errorText) setText(errorText, msg);
      if (cfg.onError) cfg.onError(msg, null);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        if (originalBtnText !== null) submitBtn.textContent = originalBtnText;
      }
    }
  });
}
