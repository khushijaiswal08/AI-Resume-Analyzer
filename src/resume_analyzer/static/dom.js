// Tiny DOM helpers. Every piece of server/user-derived text goes through textContent or
// createTextNode, never HTML strings, so a resume containing "<img onerror=...>" is just text.
(function () {
  const RA = (window.RA = window.RA || {});
  const SVG_NS = "http://www.w3.org/2000/svg";

  RA.$ = (id) => document.getElementById(id);

  function apply(node, opts) {
    if (!opts) return node;
    if (opts.cls) node.setAttribute("class", opts.cls);
    if (opts.text !== undefined && opts.text !== null) node.textContent = String(opts.text);
    if (opts.attrs) {
      Object.keys(opts.attrs).forEach((k) => {
        if (opts.attrs[k] !== null && opts.attrs[k] !== undefined) node.setAttribute(k, opts.attrs[k]);
      });
    }
    if (opts.on) Object.keys(opts.on).forEach((k) => node.addEventListener(k, opts.on[k]));
    return node;
  }
  function append(node, children) {
    children.forEach((c) => {
      if (c === null || c === undefined || c === false) return;
      if (Array.isArray(c)) append(node, c);
      else node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
    return node;
  }

  /** el("div", {cls, text, attrs, on}, ...children) */
  RA.el = (tag, opts, ...children) => append(apply(document.createElement(tag), opts), children);
  RA.svg = (tag, opts, ...children) => append(apply(document.createElementNS(SVG_NS, tag), opts), children);
  RA.clear = (node) => { node.replaceChildren(); return node; };

  /** A small status/score pill. kind: good | warn | bad | neutral. The text always carries the meaning. */
  RA.pill = (text, kind) => RA.el("span", { cls: "pill pill-" + (kind || "neutral"), text });

  RA.kindForScore = (n) => (n >= 75 ? "good" : n >= 50 ? "warn" : "bad");

  RA.card = (title, ...children) =>
    RA.el("section", { cls: "card" }, title ? RA.el("h3", { cls: "card-title", text: title }) : null, ...children);

  RA.hint = (text) => RA.el("p", { cls: "hint", text });

  RA.empty = (title, body) =>
    RA.el("div", { cls: "empty" }, RA.el("strong", { text: title }), body ? RA.el("p", { cls: "hint", text: body }) : null);

  RA.reducedMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  RA.cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  // Skill category ids from the taxonomy -> display names ("ml_ai" would otherwise read "Ml / ai").
  const CATEGORY_LABELS = {
    languages: "Languages", ml_ai: "ML / AI", data: "Data", web: "Web",
    cloud_devops: "Cloud / DevOps", databases: "Databases", tools: "Tools", soft: "Soft skills",
  };
  RA.catLabel = (c) => CATEGORY_LABELS[c] || RA.cap(String(c).replace(/_/g, " "));
  RA.plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
})();
