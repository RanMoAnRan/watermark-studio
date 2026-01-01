(() => {
  const canvas = document.getElementById("bgParticles");
  if (!canvas) return;

  const prefersReduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  if (prefersReduced && prefersReduced.matches) return;

  const ctx = canvas.getContext("2d", { alpha: true, desynchronized: true });
  if (!ctx) return;

  const state = {
    dpr: 1,
    w: 0,
    h: 0,
    particles: [],
    running: true,
    lastTs: 0,
    colorA: { r: 124, g: 58, b: 237 }, // --accent default
    colorB: { r: 34, g: 197, b: 94 }, // --accent2 default
  };

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function parseColorToRgb(raw) {
    const s = String(raw || "").trim();
    if (!s) return null;

    // #RRGGBB
    if (s[0] === "#" && s.length === 7) {
      const r = parseInt(s.slice(1, 3), 16);
      const g = parseInt(s.slice(3, 5), 16);
      const b = parseInt(s.slice(5, 7), 16);
      if ([r, g, b].some((x) => Number.isNaN(x))) return null;
      return { r, g, b };
    }

    // rgb(...) / rgba(...)
    const m = s.match(/rgba?\(([^)]+)\)/i);
    if (m) {
      const parts = m[1].split(",").map((p) => p.trim());
      if (parts.length < 3) return null;
      const r = parseFloat(parts[0]);
      const g = parseFloat(parts[1]);
      const b = parseFloat(parts[2]);
      if ([r, g, b].some((x) => Number.isNaN(x))) return null;
      return { r: clamp(Math.round(r), 0, 255), g: clamp(Math.round(g), 0, 255), b: clamp(Math.round(b), 0, 255) };
    }

    return null;
  }

  function readThemeColors() {
    const styles = getComputedStyle(document.documentElement);
    const a = parseColorToRgb(styles.getPropertyValue("--accent"));
    const b = parseColorToRgb(styles.getPropertyValue("--accent2"));
    if (a) state.colorA = a;
    if (b) state.colorB = b;
  }

  function resize() {
    state.dpr = clamp(window.devicePixelRatio || 1, 1, 2);
    state.w = Math.max(1, Math.floor(window.innerWidth));
    state.h = Math.max(1, Math.floor(window.innerHeight));
    canvas.width = Math.floor(state.w * state.dpr);
    canvas.height = Math.floor(state.h * state.dpr);
    canvas.style.width = state.w + "px";
    canvas.style.height = state.h + "px";
    ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function initParticles() {
    const isMobile = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    const area = state.w * state.h;
    const base = isMobile ? 34 : 56;
    const count = clamp(Math.round((area / (1100 * 800)) * base), isMobile ? 22 : 38, isMobile ? 46 : 86);

    state.particles = Array.from({ length: count }).map(() => {
      const size = rand(1.2, isMobile ? 2.6 : 3.2);
      const speed = rand(6, isMobile ? 18 : 26);
      const angle = rand(-Math.PI, Math.PI);
      return {
        x: rand(0, state.w),
        y: rand(0, state.h),
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        size,
        alpha: rand(0.08, 0.22),
        hueMix: Math.random(),
        wobble: rand(0.4, 1.8),
        phase: rand(0, Math.PI * 2),
      };
    });
  }

  function draw(ts) {
    if (!state.running) return;
    if (!state.lastTs) state.lastTs = ts;
    const dt = clamp((ts - state.lastTs) / 1000, 0, 0.033);
    state.lastTs = ts;

    ctx.clearRect(0, 0, state.w, state.h);

    // subtle fog
    const grad = ctx.createRadialGradient(state.w * 0.25, state.h * 0.2, 0, state.w * 0.25, state.h * 0.2, Math.max(state.w, state.h));
    grad.addColorStop(0, "rgba(255,255,255,0.03)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, state.w, state.h);

    for (const p of state.particles) {
      p.phase += dt * p.wobble;
      const ax = Math.cos(p.phase) * 4;
      const ay = Math.sin(p.phase * 0.9) * 4;

      p.x += (p.vx + ax) * dt;
      p.y += (p.vy + ay) * dt;

      if (p.x < -20) p.x = state.w + 20;
      if (p.x > state.w + 20) p.x = -20;
      if (p.y < -20) p.y = state.h + 20;
      if (p.y > state.h + 20) p.y = -20;

      const r = Math.round(state.colorA.r * (1 - p.hueMix) + state.colorB.r * p.hueMix);
      const g = Math.round(state.colorA.g * (1 - p.hueMix) + state.colorB.g * p.hueMix);
      const b = Math.round(state.colorA.b * (1 - p.hueMix) + state.colorB.b * p.hueMix);

      ctx.beginPath();
      ctx.fillStyle = `rgba(${r},${g},${b},${p.alpha})`;
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }

  function onVisibility() {
    state.running = !document.hidden;
    if (state.running) {
      state.lastTs = 0;
      requestAnimationFrame(draw);
    }
  }

  const mo = new MutationObserver(() => readThemeColors());
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "style"] });

  readThemeColors();
  resize();
  initParticles();
  requestAnimationFrame(draw);

  window.addEventListener("resize", () => {
    resize();
    initParticles();
  });
  document.addEventListener("visibilitychange", onVisibility);
})();

