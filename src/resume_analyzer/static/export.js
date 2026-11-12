// Client-side export: the analysis is built into a file in the browser and never sent anywhere.
(function () {
  const RA = window.RA;

  function download(name, mime, content) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Markdown table cells must not contain pipes or newlines.
  const cell = (s) => String(s === null || s === undefined ? "" : s).replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ");

  RA.toMarkdown = function (r) {
    const L = [];
    L.push("# Resume analysis", "");
    L.push(`- **ATS-style score:** ${r.ats_score.total}/100 (explainable heuristic, not a real ATS vendor's algorithm)`);
    L.push(`- **Composite readiness:** ${r.readiness.score}/100 (${r.readiness.label})`);
    L.push(`- **Words:** ${r.word_count} | **Sections:** ${r.sections.join(", ") || "none"}`, "");
    L.push("## Score breakdown", "", "| Criterion | Points | Why |", "| --- | --- | --- |");
    r.ats_score.breakdown.forEach((b) => L.push(`| ${cell(b.criterion)} | ${b.score}/${b.max} | ${cell(b.reason)} |`));
    L.push("", "## Readiness components", "");
    r.readiness.components.forEach((c) => L.push(`- ${c.label}: ${c.score} (weight ${c.weight}%) - ${c.note}`));
    L.push("", "## ATS parse-ability checks", "", `Score ${r.ats_checks.score}/100: ${r.ats_checks.passed} passed, ${r.ats_checks.warned} warnings, ${r.ats_checks.failed} failed.`, "");
    r.ats_checks.items.forEach((c) => {
      L.push(`- **${c.status.toUpperCase()}** ${c.title}: ${c.detail}` + (c.fix ? ` Fix: ${c.fix}` : ""));
    });
    L.push("", "## Bullets", "");
    if (r.bullets.count) {
      L.push(`Average ${r.bullets.average_score}/100: ${r.bullets.strong} strong, ${r.bullets.ok} ok, ${r.bullets.weak} weak.`, "");
      r.bullets.items.filter((b) => b.rating !== "strong").forEach((b) =>
        L.push(`- (${b.score}, ${b.rating}) ${b.text}` + (b.hint ? `\n  - Hint: ${b.hint}` : "")));
    } else L.push("No bullets found.");
    L.push("", "## Skills", "");
    L.push(`${r.skill_evidence.demonstrated} demonstrated, ${r.skill_evidence.listed_only} listed only, ${r.skill_evidence.mentioned} mentioned.`);
    if (r.skill_evidence.listed_only_skills.length) L.push("", "Listed but never shown: " + r.skill_evidence.listed_only_skills.join(", "));
    Object.keys(r.skills).forEach((cat) => L.push(`- ${RA.catLabel(cat)}: ${r.skills[cat].join(", ")}`));
    if (r.jd_analysis) {
      const j = r.jd_analysis;
      L.push("", "## Job description match", "", `Weighted ${j.weighted_percent === null ? "n/a" : j.weighted_percent + "%"} | required ${j.required_percent === null ? "n/a" : j.required_percent + "%"} | preferred ${j.preferred_percent === null ? "n/a" : j.preferred_percent + "%"}`, "");
      j.requirements.forEach((q) => L.push(`- [${q.status}] ${q.skill} (${q.priority})` + (q.hint ? ` - ${q.hint}` : "")));
    }
    if (r.role_fit) {
      const f = r.role_fit;
      L.push("", `## Role fit: ${f.role_name}`, "", `Fit ${f.fit_percent}%. Missing core: ${f.core_missing.join(", ") || "none"}.`, "");
      f.learn_next.forEach((l) => L.push(`- Learn next (${l.priority}): ${l.skill} - ${l.hint}`));
    }
    if (r.llm.used) {
      L.push("", "## AI insights (do not affect any score)", "");
      if (r.llm.first_impression) L.push(r.llm.first_impression, "");
      r.llm.suggestions.forEach((s) => L.push(`- ${s}`));
      r.llm.bullet_rewrites.forEach((w) => L.push(`- Rewrite: "${w.original}" -> "${w.rewrite}"`));
    }
    L.push("", "---", "Generated locally in your browser by AI Resume Analyzer. Nothing was stored.");
    return L.join("\n") + "\n";
  };

  RA.exportJson = (r) => download("resume-analysis.json", "application/json", JSON.stringify(r, null, 2));
  RA.exportMarkdown = (r) => download("resume-analysis.md", "text/markdown", RA.toMarkdown(r));
  RA.exportPrint = () => window.print();
})();
