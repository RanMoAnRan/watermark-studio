function applyTheme(theme) {
  const root = document.documentElement;
  if (!theme || theme === "default") {
    root.removeAttribute("data-theme");
    return;
  }
  root.setAttribute("data-theme", theme);
}

function loadTheme() {
  try {
    return localStorage.getItem("wm_theme") || "default";
  } catch (e) {
    return "default";
  }
}

function saveTheme(theme) {
  try {
    if (!theme || theme === "default") {
      localStorage.removeItem("wm_theme");
      return;
    }
    localStorage.setItem("wm_theme", theme);
  } catch (e) {}
}

(function initThemeSwitcher() {
  const select = document.querySelector("#themeSelect");
  const theme = loadTheme();
  applyTheme(theme);
  if (!select) return;
  select.value = theme;

  select.addEventListener("change", () => {
    const next = String(select.value || "default");
    applyTheme(next);
    saveTheme(next);
  });
})();

