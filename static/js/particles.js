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

  const pointer = {
    x: 0,
    y: 0,
    active: false,
    lastMovedTs: 0,
  };

  const TAU = Math.PI * 2;

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function rgba({ r, g, b }, a) {
    return `rgba(${r},${g},${b},${clamp(a, 0, 1)})`;
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
    state.w = Math.max(1, Math.floor(window.innerWidth));
    state.h = Math.max(1, Math.floor(window.innerHeight));
    const maxDpr = 2.5;
    const maxPixels = 16_000_000; // cap GPU/CPU on very large screens
    const areaLimit = Math.sqrt(maxPixels / (state.w * state.h));
    state.dpr = clamp(Math.min(window.devicePixelRatio || 1, maxDpr, areaLimit), 1, maxDpr);
    canvas.width = Math.floor(state.w * state.dpr);
    canvas.height = Math.floor(state.h * state.dpr);
    canvas.style.width = state.w + "px";
    canvas.style.height = state.h + "px";
    ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);

    if (!pointer.lastMovedTs) {
      pointer.x = state.w * 0.5;
      pointer.y = state.h * 0.35;
    }
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function mixColor(t) {
    return {
      r: Math.round(state.colorA.r * (1 - t) + state.colorB.r * t),
      g: Math.round(state.colorA.g * (1 - t) + state.colorB.g * t),
      b: Math.round(state.colorA.b * (1 - t) + state.colorB.b * t),
    };
  }

  function initParticles() {
    const isMobile = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    const area = state.w * state.h;
    const base = isMobile ? 32 : 52;
    const count = clamp(Math.round((area / (1100 * 800)) * base), isMobile ? 22 : 36, isMobile ? 44 : 78);

    state.particles = Array.from({ length: count }).map(() => {
      const size = rand(0.9, isMobile ? 2.1 : 2.6);
      const speed = rand(10, isMobile ? 22 : 34);
      const angle = rand(-Math.PI, Math.PI);
      const depth = rand(0.2, 1);
      return {
        x: rand(0, state.w),
        y: rand(0, state.h),
        vx: Math.cos(angle) * speed * (0.45 + depth),
        vy: Math.sin(angle) * speed * (0.45 + depth),
        size: size * (0.7 + depth * 0.6),
        alpha: rand(0.16, 0.38) * (0.55 + depth * 0.55),
        hueMix: Math.random(),
        wobble: rand(0.35, 1.6),
        phase: rand(0, TAU),
        pulse: rand(0.6, 1.9),
        depth,
      };
    });
  }

  function drawBackground(ts) {
    ctx.clearRect(0, 0, state.w, state.h);

    // subtle fog + vignette
    ctx.globalCompositeOperation = "source-over";
    const fog = ctx.createRadialGradient(state.w * 0.22, state.h * 0.18, 0, state.w * 0.22, state.h * 0.18, Math.max(state.w, state.h));
    fog.addColorStop(0, "rgba(255,255,255,0.03)");
    fog.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = fog;
    ctx.fillRect(0, 0, state.w, state.h);

    // diagonal sweep for a "tech" feel (very subtle)
    const sweep = (ts / 1000) * 45;
    const x = (sweep % (state.w + 600)) - 300;
    const sweepGrad = ctx.createLinearGradient(x, 0, x + 280, state.h);
    sweepGrad.addColorStop(0, "rgba(255,255,255,0)");
    sweepGrad.addColorStop(0.5, rgba(state.colorA, 0.045));
    sweepGrad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = sweepGrad;
    ctx.fillRect(0, 0, state.w, state.h);
  }

  function drawConnections(ts) {
    const isMobile = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    const maxDist = isMobile ? 110 : 145;
    const maxDist2 = maxDist * maxDist;

    ctx.globalCompositeOperation = "lighter";
    ctx.lineWidth = 1;
    ctx.lineCap = "round";

    for (let i = 0; i < state.particles.length; i++) {
      const a = state.particles[i];
      for (let j = i + 1; j < state.particles.length; j++) {
        const b = state.particles[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > maxDist2) continue;

        const d = Math.sqrt(d2);
        const t = 1 - d / maxDist;
        const alpha = t * t * 0.22;
        const pulse = 0.72 + 0.28 * Math.sin((ts / 1000) * (a.pulse + b.pulse) * 0.55 + a.phase - b.phase);
        const aa = alpha * pulse * (0.6 + 0.4 * Math.min(a.depth, b.depth));

        const ca = mixColor(a.hueMix);
        const cb = mixColor(b.hueMix);
        const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
        grad.addColorStop(0, rgba(ca, aa));
        grad.addColorStop(1, rgba(cb, aa));
        ctx.strokeStyle = grad;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }
  }

  function drawPointerLinks(ts) {
    if (!pointer.active) return;

    // fade out if pointer hasn't moved recently (touch screens)
    const idle = (ts - pointer.lastMovedTs) / 1000;
    const idleFade = clamp(1 - idle / 2.2, 0, 1);
    if (idleFade <= 0) return;

    const isMobile = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    const maxDist = isMobile ? 120 : 170;
    const maxDist2 = maxDist * maxDist;

    ctx.globalCompositeOperation = "lighter";
    ctx.lineWidth = 1;
    ctx.lineCap = "round";

    for (const p of state.particles) {
      const dx = p.x - pointer.x;
      const dy = p.y - pointer.y;
      const d2 = dx * dx + dy * dy;
      if (d2 > maxDist2) continue;

      const d = Math.sqrt(d2);
      const t = 1 - d / maxDist;
      const alpha = t * t * 0.28 * idleFade;
      const c = mixColor(p.hueMix);
      ctx.strokeStyle = rgba(c, alpha);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(pointer.x, pointer.y);
      ctx.stroke();
    }
  }

  function drawParticles(ts) {
    ctx.globalCompositeOperation = "lighter";

    for (const p of state.particles) {
      const c = mixColor(p.hueMix);
      const pulse = 0.6 + 0.4 * Math.sin((ts / 1000) * p.pulse + p.phase);
      const a = p.alpha * pulse;

      // glow
      const glowR = p.size * (4.2 + p.depth * 2.2);
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowR);
      g.addColorStop(0, rgba(c, a * 0.55));
      g.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(p.x, p.y, glowR, 0, TAU);
      ctx.fill();

      // core (crisp)
      ctx.fillStyle = rgba(c, Math.min(1, a * 1.8));
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, TAU);
      ctx.fill();
    }
  }

  function draw(ts) {
    if (!state.running) return;
    if (!state.lastTs) state.lastTs = ts;
    const dt = clamp((ts - state.lastTs) / 1000, 0, 0.033);
    state.lastTs = ts;

    drawBackground(ts);

    for (const p of state.particles) {
      p.phase += dt * p.wobble;
      const ax = Math.cos(p.phase) * (2 + p.depth * 3);
      const ay = Math.sin(p.phase * 0.9) * (2 + p.depth * 3);

      p.x += (p.vx + ax) * dt;
      p.y += (p.vy + ay) * dt;

      const pad = 28;
      if (p.x < -pad) p.x = state.w + pad;
      if (p.x > state.w + pad) p.x = -pad;
      if (p.y < -pad) p.y = state.h + pad;
      if (p.y > state.h + pad) p.y = -pad;
    }

    drawConnections(ts);
    drawPointerLinks(ts);
    drawParticles(ts);

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

  window.addEventListener(
    "pointermove",
    (e) => {
      pointer.active = true;
      pointer.lastMovedTs = performance.now();
      pointer.x = clamp(e.clientX, 0, state.w);
      pointer.y = clamp(e.clientY, 0, state.h);
    },
    { passive: true }
  );
  window.addEventListener(
    "pointerdown",
    (e) => {
      pointer.active = true;
      pointer.lastMovedTs = performance.now();
      pointer.x = clamp(e.clientX, 0, state.w);
      pointer.y = clamp(e.clientY, 0, state.h);
    },
    { passive: true }
  );
  window.addEventListener(
    "pointerleave",
    () => {
      pointer.active = false;
    },
    { passive: true }
  );
})();
