// App controller: upload / sample flow, API calls, tabs, theme toggle, export buttons.
// Everything that comes back from the server is rendered through the DOM helpers in dom.js
// (textContent), never HTML strings.
(function () {
  const RA = window.RA;
  const $ = RA.$;
  const TABS = [
    ["overview", "Overview"], ["bullets", "Bullets"], ["skills", "Skills"], ["job", "Job match"],
    ["ats", "ATS checks"], ["privacy", "Privacy view"], ["ai", "AI insights"],
  ];
  const state = { file: null, label: "", result: null, roles: [], busy: false };

  // ---------------------------------------------------------------- theme
  function currentTheme() { return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
  function syncThemeButton() {
    const dark = currentTheme() === "dark";
    const btn = $("theme-toggle");
    btn.setAttribute("aria-pressed", String(dark));
    btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    $("theme-label").textContent = dark ? "Light" : "Dark";
  }
  $("theme-toggle").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("ra-theme", next); } catch (e) { /* storage blocked: toggle still works for this visit */ }
    syncThemeButton();
  });
  syncThemeButton();

  // ---------------------------------------------------------------- messages
  function showError(message) {
    const box = $("error");
    box.textContent = message;
    box.hidden = !message;
  }
  function announce(message) { $("status").textContent = message; }

  // ---------------------------------------------------------------- file selection
  function setFile(file, label) {
    state.file = file;
    state.label = label || (file ? file.name : "");
    $("file-name").textContent = file ? state.label : "No file chosen yet";
    $("dropzone").classList.toggle("has-file", !!file);
    showError("");
  }
  function acceptFile(file) {
    if (!file) return;
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) {
      showError("That file type is not supported. Please choose a PDF, DOCX or TXT resume.");
      return;
    }
    setFile(file);
  }

  const dz = $("dropzone");
  $("resume").addEventListener("change", (e) => acceptFile(e.target.files[0]));
  ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => { acceptFile(e.dataTransfer && e.dataTransfer.files[0]); });
  // A file dropped outside the zone would otherwise navigate the tab away from the page.
  ["dragover", "drop"].forEach((t) => window.addEventListener(t, (e) => e.preventDefault()));

  // ---------------------------------------------------------------- roles
  function loadRoles() {
    fetch("/api/roles").then((r) => (r.ok ? r.json() : [])).then((roles) => {
      state.roles = roles;
      const sel = $("role");
      roles.forEach((r) => sel.appendChild(RA.el("option", { text: r.name, attrs: { value: r.id } })));
    }).catch(() => { /* the role selector is optional */ });
  }
  $("role").addEventListener("change", () => {
    const role = state.roles.find((r) => r.id === $("role").value);
    $("role-hint").textContent = role ? role.description : "Optional: see how well you fit a role without a job description.";
  });
  fetch("/api/health").then((r) => r.json()).then((h) => {
    $("ai-state").textContent = h.llm_configured
      ? "AI insights are on: only redacted text is ever sent (see the Privacy view)."
      : "AI insights are off on this server. Every score below is deterministic and works without AI.";
  }).catch(() => {});

  // ---------------------------------------------------------------- analyze
  // "597 seconds" is hard to read: show minutes once the wait is over 90 seconds.
  function waitText(seconds) {
    return seconds > 90 ? `${Math.ceil(seconds / 60)} minutes` : `${seconds} seconds`;
  }

  function friendlyError(status, detail, retryAfter) {
    if (status === 429) {
      const seconds = parseInt(retryAfter, 10);
      return seconds > 0
        ? `Too many analyses. Please try again in ${waitText(seconds)}.`
        : detail || "Too many analyses right now. Please wait a few minutes and try again.";
    }
    if (status === 413) return "That file is too large. Please upload a smaller resume.";
    if (status === 415) return "That file type is not supported. Please upload a PDF, DOCX or TXT resume.";
    if (status === 422) return detail || "We could not read text from that file. Try another file or a TXT version.";
    return detail || "Something went wrong on the server. Please try again.";
  }

  async function analyze() {
    if (state.busy) return;
    if (!state.file) { showError("Choose a resume file first, or try the sample resume."); $("resume").focus(); return; }
    state.busy = true;
    showError("");
    $("analyze").disabled = true;
    $("sample").disabled = true;
    $("loading").hidden = false;
    $("results").hidden = true;
    announce("Analyzing your resume...");

    const form = new FormData();
    form.append("resume", state.file, state.file.name);
    const jd = $("jd").value.trim();
    if (jd) form.append("job_description", jd);
    if ($("role").value) form.append("role", $("role").value);
    try {
      const res = await fetch("/api/analyze", { method: "POST", body: form });
      let body = null;
      try { body = await res.json(); } catch (e) { /* non-JSON error page */ }
      if (!res.ok) throw new Error(friendlyError(res.status, body && typeof body.detail === "string" ? body.detail : "", res.headers.get("Retry-After")));
      state.result = body;
      renderResults(body);
    } catch (err) {
      const offline = err instanceof TypeError; // fetch rejects with TypeError when the network fails
      showError(offline ? "Could not reach the server. Check your connection and try again." : err.message);
      announce("");
      $("intake").hidden = false;
    } finally {
      state.busy = false;
      $("analyze").disabled = false;
      $("sample").disabled = false;
      $("loading").hidden = true;
    }
  }
  $("form").addEventListener("submit", (e) => { e.preventDefault(); analyze(); });

  $("sample").addEventListener("click", async () => {
    if (state.busy) return;
    showError("");
    try {
      const res = await fetch("/api/sample");
      if (!res.ok) throw new Error("sample");
      const s = await res.json();
      setFile(new File([s.resume_text], s.filename || "sample-resume.txt", { type: "text/plain" }), s.name);
      $("jd").value = s.job_description || "";
      $("jd-details").open = !!s.job_description;
      if (s.role_id && state.roles.some((r) => r.id === s.role_id)) { $("role").value = s.role_id; $("role").dispatchEvent(new Event("change")); }
      analyze();
    } catch (e) {
      showError("Could not load the sample resume. Please try again.");
    }
  });

  // ---------------------------------------------------------------- results + tabs
  const ctx = { goTo: (id) => selectTab(id, true) };

  function selectTab(id, focus) {
    TABS.forEach(([tid]) => {
      const tab = $("tab-" + tid), panel = $("panel-" + tid);
      const on = tid === id;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
      panel.hidden = !on;
      if (on && focus) { tab.focus(); tab.scrollIntoView({ block: "nearest", inline: "nearest" }); }
    });
  }

  function buildTabs() {
    const list = $("tablist"), panels = $("panels");
    RA.clear(list); RA.clear(panels);
    TABS.forEach(([id, label], i) => {
      list.appendChild(RA.el("button", { cls: "tab", attrs: { role: "tab", id: "tab-" + id, "aria-controls": "panel-" + id, "aria-selected": "false", tabindex: "-1", type: "button" },
        text: label, on: { click: () => selectTab(id), keydown: (e) => {
          const keys = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 };
          if (!(e.key in keys)) return;
          e.preventDefault();
          selectTab(TABS[(keys[e.key] + TABS.length) % TABS.length][0], true);
        } } }));
      panels.appendChild(RA.el("div", { cls: "panel", attrs: { role: "tabpanel", id: "panel-" + id, "aria-labelledby": "tab-" + id, tabindex: "0", hidden: "" } }));
    });
  }

  function renderResults(r) {
    buildTabs();
    TABS.forEach(([id]) => {
      const panel = $("panel-" + id);
      try { panel.appendChild(RA.views[id](r, ctx)); }
      catch (e) { panel.appendChild(RA.card("Could not display this tab", RA.hint("Something unexpected happened while drawing this section. The other tabs still work."))); }
    });
    RA.viewer.setText(r.resume_text);
    $("results-title").textContent = state.label ? `Analysis: ${state.label}` : "Your analysis";
    const bits = [];
    if (r.role_fit) bits.push("Role: " + r.role_fit.role_name);
    bits.push(r.jd_analysis ? "Compared with your job description" : "No job description");
    bits.push(`${r.word_count} words`);
    $("results-sub").textContent = bits.join(" · ");
    $("intake").hidden = true;
    $("results").hidden = false;
    selectTab("overview");
    announce(`Analysis complete. ATS-style score ${r.ats_score.total} out of 100, readiness ${r.readiness.score}.`);
    window.scrollTo({ top: 0, behavior: "auto" });
    $("results-title").focus({ preventScroll: true });
  }

  RA.viewer.init($("viewer-box"), $("viewer-label"), $("viewer-text"), $("viewer-note"));
  $("viewer-clear").addEventListener("click", () => RA.viewer.clear());

  $("new-analysis").addEventListener("click", () => {
    $("results").hidden = true;
    $("intake").hidden = false;
    announce("");
    window.scrollTo({ top: 0, behavior: "auto" });
    $("resume").focus();
  });
  $("export-json").addEventListener("click", () => state.result && RA.exportJson(state.result));
  $("export-md").addEventListener("click", () => state.result && RA.exportMarkdown(state.result));
  $("export-print").addEventListener("click", () => RA.exportPrint());

  loadRoles();
})();
