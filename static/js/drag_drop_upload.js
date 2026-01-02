(() => {
  function hasFiles(evt) {
    const dt = evt.dataTransfer;
    if (!dt) return false;
    if (dt.types && typeof dt.types.includes === "function") return dt.types.includes("Files");
    return !!(dt.files && dt.files.length);
  }

  function setFiles(input, fileList) {
    const files = Array.from(fileList || []).filter((f) => f && f.size >= 0);
    if (!files.length) return false;

    const limited = input.multiple ? files : [files[0]];

    // Some browsers allow direct assignment, but DataTransfer is more reliable.
    try {
      if (typeof DataTransfer !== "undefined") {
        const dt = new DataTransfer();
        for (const f of limited) dt.items.add(f);
        input.files = dt.files;
      } else {
        input.files = limited;
      }
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    } catch (e) {
      try {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (e2) {}
      return false;
    }
  }

  function enhance(input) {
    if (!input || input.dataset.dragDropReady === "1") return;
    input.dataset.dragDropReady = "1";

    const target = input.closest(".field") || input.parentElement || input;
    target.classList.add("file-drop");

    const hint = target.querySelector(".hint");
    if (hint && !hint.dataset.dragDropHint) {
      hint.dataset.dragDropHint = "1";
      const text = hint.textContent || "";
      if (!text.includes("拖拽")) hint.textContent = text ? `${text}（支持拖拽上传）` : "支持拖拽上传";
    }

    let dragDepth = 0;
    function enter(evt) {
      if (!hasFiles(evt)) return;
      evt.preventDefault();
      dragDepth += 1;
      target.classList.add("is-dragover");
    }
    function over(evt) {
      if (!hasFiles(evt)) return;
      evt.preventDefault();
      if (evt.dataTransfer) evt.dataTransfer.dropEffect = "copy";
      target.classList.add("is-dragover");
    }
    function leave(evt) {
      if (!hasFiles(evt)) return;
      evt.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) target.classList.remove("is-dragover");
    }
    function drop(evt) {
      if (!hasFiles(evt)) return;
      evt.preventDefault();
      dragDepth = 0;
      target.classList.remove("is-dragover");
      if (evt.dataTransfer && evt.dataTransfer.files) setFiles(input, evt.dataTransfer.files);
    }

    target.addEventListener("dragenter", enter);
    target.addEventListener("dragover", over);
    target.addEventListener("dragleave", leave);
    target.addEventListener("drop", drop);

    // Make the whole field clickable to open the file picker (nice UX for drop zones).
    target.addEventListener("click", (evt) => {
      const el = evt.target;
      if (!el) return;
      const tag = (el.tagName || "").toLowerCase();
      if (tag === "a" || tag === "button" || tag === "input" || tag === "select" || tag === "textarea") return;
      input.click();
    });

    target.tabIndex = target.tabIndex >= 0 ? target.tabIndex : 0;
    target.addEventListener("keydown", (evt) => {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        input.click();
      }
    });
  }

  function enhanceAll() {
    document.querySelectorAll('input[type="file"]').forEach(enhance);
  }

  // Prevent the browser from navigating to a file if dropped outside a drop zone.
  function preventWindowDrop(evt) {
    if (!hasFiles(evt)) return;
    const target = evt.target;
    if (target && target.closest && target.closest(".file-drop")) return;
    evt.preventDefault();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAll);
  } else {
    enhanceAll();
  }

  window.addEventListener("dragover", preventWindowDrop);
  window.addEventListener("drop", preventWindowDrop);
})();

