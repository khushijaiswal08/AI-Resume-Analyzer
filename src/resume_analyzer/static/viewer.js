// Resume viewer: shows the extracted text and highlights character ranges.
// Server offsets are Python string indexes (code points); JS strings index UTF-16 units, so
// text with emoji or other astral characters needs a translation table.
(function () {
  const RA = window.RA;
  let text = "", toU16 = null, boxNode = null, labelNode = null, bodyNode = null, noteNode = null;

  function buildMap(s) {
    if (!/[\ud800-\udfff]/.test(s)) return null;
    const map = [];
    let u = 0;
    for (const ch of s) { map.push(u); u += ch.length; }
    map.push(u);
    return map;
  }
  const conv = (i) => (toU16 ? toU16[Math.min(Math.max(i, 0), toU16.length - 1)] : i);

  RA.viewer = {
    init(box, label, body, note) { boxNode = box; labelNode = label; bodyNode = body; noteNode = note; },

    setText(s) { text = s || ""; toU16 = buildMap(text); this.clear(); },

    clear() {
      if (!bodyNode) return;
      bodyNode.textContent = text || "(no text)";
      labelNode.textContent = "Click a criterion, bullet, skill or check to highlight its evidence here.";
      noteNode.textContent = "";
      boxNode.scrollTop = 0;
    },

    /** ranges: [{start, end, kind: earned|lost|focus, note}] in server (code point) offsets. */
    highlight(ranges, label, missing) {
      const rs = (ranges || [])
        .map((r) => ({ a: conv(r.start), b: conv(r.end), kind: r.kind || "focus", note: r.note || "" }))
        .filter((r) => r.b > r.a && r.a < text.length);
      const cuts = new Set([0, text.length]);
      rs.forEach((r) => { cuts.add(r.a); cuts.add(Math.min(r.b, text.length)); });
      const pts = Array.from(cuts).sort((x, y) => x - y);
      const frag = document.createDocumentFragment();
      let first = null;
      for (let i = 0; i < pts.length - 1; i++) {
        const a = pts[i], b = pts[i + 1];
        const piece = text.slice(a, b);
        const active = rs.filter((r) => r.a <= a && r.b >= b);
        if (!active.length) { frag.appendChild(document.createTextNode(piece)); continue; }
        // If ranges overlap, "lost" wins, then "focus", then "earned".
        const kind = ["lost", "focus", "earned"].find((k) => active.some((r) => r.kind === k)) || "focus";
        const note = active.map((r) => r.note).filter(Boolean).join("; ");
        const mark = RA.el("mark", { cls: "hl hl-" + kind, text: piece, attrs: note ? { title: note } : null });
        if (!first) first = mark;
        frag.appendChild(mark);
      }
      bodyNode.replaceChildren(frag);
      labelNode.textContent = label + (rs.length ? ` (${RA.plural(rs.length, "highlight")})` : " (nothing to highlight)");
      noteNode.textContent = missing && missing.length ? "Not in the resume: " + missing.join(", ") : "";
      if (first) {
        boxNode.scrollTop = Math.max(0, first.offsetTop - boxNode.clientHeight / 3);
        // On narrow screens the viewer sits below the tabs: bring it into view if it is off screen.
        const r = boxNode.getBoundingClientRect();
        if (r.bottom < 0 || r.top > window.innerHeight) boxNode.scrollIntoView({ block: "nearest", behavior: RA.reducedMotion() ? "auto" : "smooth" });
      }
    },
  };
})();
