// Inline-SVG charts: an animated gauge, a radar and a plain bar. No chart library.
(function () {
  const RA = window.RA;
  const TAU = Math.PI * 2;

  /** Circular gauge. The arc animates with a CSS transition; the number counts up. */
  RA.gauge = function (value, label, kind) {
    const r = 52, c = 2 * Math.PI * r;
    const k = kind || RA.kindForScore(value);
    const arc = RA.svg("circle", { cls: "gauge-arc gauge-" + k, attrs: { cx: 60, cy: 60, r, "stroke-dasharray": c.toFixed(2) } });
    arc.style.strokeDashoffset = c.toFixed(2); // start empty, then animate in
    const num = RA.svg("text", { cls: "gauge-num", attrs: { x: 60, y: 68, "text-anchor": "middle" }, text: RA.reducedMotion() ? String(value) : "0" });
    const svg = RA.svg("svg", { cls: "gauge", attrs: { viewBox: "0 0 120 120", role: "img", "aria-label": `${label}: ${value} out of 100` } },
      RA.svg("circle", { cls: "gauge-track", attrs: { cx: 60, cy: 60, r } }), arc, num);
    const target = (c * (1 - value / 100)).toFixed(2);
    if (RA.reducedMotion()) {
      arc.style.strokeDashoffset = target;
    } else {
      requestAnimationFrame(() => requestAnimationFrame(() => { arc.style.strokeDashoffset = target; }));
      const start = performance.now(), dur = 900;
      const tick = (now) => {
        const t = Math.min(1, (now - start) / dur);
        num.textContent = String(Math.round(value * (1 - Math.pow(1 - t, 3))));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
    return svg;
  };

  /** Radar chart. items: [{label, value 0-100, title}] (needs >= 3 axes). */
  RA.radar = function (items, ariaLabel) {
    const cx = 150, cy = 150, R = 88, n = items.length;
    const pt = (i, f) => {
      const a = (TAU * i) / n - Math.PI / 2;
      return [cx + R * f * Math.cos(a), cy + R * f * Math.sin(a)];
    };
    const fmt = (p) => p[0].toFixed(1) + "," + p[1].toFixed(1);
    const svg = RA.svg("svg", { cls: "radar", attrs: { viewBox: "-30 0 360 300", role: "img", "aria-label": ariaLabel } });
    [0.25, 0.5, 0.75, 1].forEach((f) =>
      svg.appendChild(RA.svg("polygon", { cls: "radar-ring", attrs: { points: items.map((_, i) => fmt(pt(i, f))).join(" ") } })));
    items.forEach((it, i) => {
      const [x, y] = pt(i, 1);
      svg.appendChild(RA.svg("line", { cls: "radar-axis", attrs: { x1: cx, y1: cy, x2: x.toFixed(1), y2: y.toFixed(1) } }));
      const [lx, ly] = pt(i, 1.2);
      const anchor = lx < cx - 8 ? "end" : lx > cx + 8 ? "start" : "middle";
      svg.appendChild(RA.svg("text", { cls: "radar-label", attrs: { x: lx.toFixed(1), y: (ly + 4).toFixed(1), "text-anchor": anchor }, text: it.label }));
    });
    svg.appendChild(RA.svg("polygon", { cls: "radar-shape", attrs: { points: items.map((it, i) => fmt(pt(i, Math.max(0.02, it.value / 100)))).join(" ") } }));
    items.forEach((it, i) => {
      const [x, y] = pt(i, Math.max(0.02, it.value / 100));
      svg.appendChild(RA.svg("circle", { cls: "radar-dot", attrs: { cx: x.toFixed(1), cy: y.toFixed(1), r: 3.5 } }, RA.svg("title", { text: it.title })));
    });
    return svg;
  };

  /** Horizontal bar, percent 0-100. */
  RA.bar = function (percent, kind) {
    const fill = RA.el("i", { cls: "bar-fill bar-" + (kind || RA.kindForScore(percent)) });
    fill.style.width = Math.max(0, Math.min(100, percent)) + "%";
    return RA.el("div", { cls: "bar", attrs: { role: "presentation" } }, fill);
  };
})();
