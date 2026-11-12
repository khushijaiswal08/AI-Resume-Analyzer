// One render function per tab. Each takes the /api/analyze response `r` and returns a DOM node.
// `ctx.goTo(tabId)` switches tab; RA.viewer.highlight() paints evidence in the resume viewer.
(function () {
  const { el, card, pill, hint, empty, bar, plural, cap } = window.RA;
  const RA = window.RA;

  const SHORT = {
    sections: "Sections", skills: "Skills", quantified_achievements: "Metrics",
    action_verbs: "Verbs", length: "Length", contact_info: "Contact", jd_coverage: "JD fit",
  };
  const STATUS = {
    pass: { icon: "✓", label: "Pass", kind: "good" },
    warn: { icon: "!", label: "Warning", kind: "warn" },
    fail: { icon: "✕", label: "Fail", kind: "bad" },
  };

  /** A button that paints ranges in the viewer. Looks like a link/row; keyboard accessible. */
  function hlButton(cls, ranges, label, missing, ...children) {
    return el("button", { cls: "hl-btn " + cls, attrs: { type: "button", title: "Show in resume" },
      on: { click: () => RA.viewer.highlight(ranges, label, missing) } }, ...children);
  }

  function stat(value, label) {
    return el("div", { cls: "stat" }, el("div", { cls: "stat-v", text: value }), el("div", { cls: "stat-l", text: label }));
  }

  function chipList(items, kind) {
    return el("div", { cls: "chips" }, items.map((t) => el("span", { cls: "chip chip-" + (kind || "plain"), text: t })));
  }

  // ---------------------------------------------------------------- Overview
  function quickWins(r, ctx) {
    const wins = [];
    r.ats_checks.items.filter((c) => c.status === "fail").forEach((c) =>
      wins.push({ tab: "ats", kind: "bad", head: "Fix: " + c.title, body: c.fix || c.detail }));
    r.ats_checks.items.filter((c) => c.status === "warn").forEach((c) =>
      wins.push({ tab: "ats", kind: "warn", head: "Check: " + c.title, body: c.fix || c.detail }));
    if (r.bullets.weak > 0)
      wins.push({ tab: "bullets", kind: "bad", head: `${plural(r.bullets.weak, "weak bullet")}`, body: "Rewrite these first: lead with a strong verb and add a measurable result." });
    if (r.skill_evidence.listed_only > 0)
      wins.push({ tab: "skills", kind: "warn", head: `${plural(r.skill_evidence.listed_only, "skill")} listed but never shown`, body: r.skill_evidence.listed_only_skills.slice(0, 6).join(", ") + ". Add a bullet showing where you used each." });
    if (r.jd_analysis) {
      const miss = r.jd_analysis.requirements.filter((q) => q.status === "missing" && q.priority === "required");
      if (miss.length)
        wins.push({ tab: "job", kind: "warn", head: `${plural(miss.length, "required skill")} missing for this job`, body: miss.slice(0, 6).map((q) => q.skill).join(", ") });
    }
    r.readability.notes.forEach((n) => wins.push({ tab: "bullets", kind: "neutral", head: "Tone", body: n }));
    if (!wins.length) return el("p", { cls: "hint", text: "Nothing urgent. Every check passed and no weak bullets were found." });
    return el("ul", { cls: "wins" }, wins.slice(0, 7).map((w) =>
      el("li", null, el("button", { cls: "win", attrs: { type: "button" }, on: { click: () => ctx.goTo(w.tab) } },
        pill(w.kind === "bad" ? "Fix" : w.kind === "warn" ? "Improve" : "Note", w.kind),
        el("span", { cls: "win-text" }, el("strong", { text: w.head }), el("span", { text: w.body || "" }))))));
  }

  function overview(r, ctx) {
    const root = el("div", { cls: "stack" });
    const ats = r.ats_score;
    const rd = r.readiness;

    const gauges = el("div", { cls: "grid-2" });
    gauges.appendChild(card(null,
      el("div", { cls: "gauge-card" },
        RA.gauge(ats.total, "ATS-style score"),
        el("div", null,
          el("h3", { cls: "card-title", text: "ATS-style score" }),
          hint("An explainable heuristic built for this project, not a real vendor's algorithm. The AI never changes it."))),
      el("div", { cls: "stats", attrs: { style: "margin:14px 0 0" } },
        stat(r.bullets.average_score === null ? "-" : r.bullets.average_score, "Bullet quality"),
        stat(r.ats_checks.score, "Parse-ability"),
        stat(`${r.skill_evidence.demonstrated}/${r.skill_evidence.skills.length}`, "Skills shown in use"))));
    const comp = el("ul", { cls: "components" }, rd.components.map((c) =>
      el("li", null,
        el("div", { cls: "comp-head" }, el("span", { text: c.label }), el("span", { cls: "num", text: `${c.score}  · weight ${c.weight}%` })),
        bar(c.score))));
    gauges.appendChild(card(null,
      el("div", { cls: "gauge-card" },
        RA.gauge(rd.score, "Composite readiness"),
        el("div", null,
          el("h3", { cls: "card-title" }, "Composite readiness ", pill(rd.label, RA.kindForScore(rd.score))),
          hint(rd.explanation))),
      comp));
    root.appendChild(gauges);

    // Criteria radar + clickable rows that highlight evidence.
    const criteria = ats.breakdown.map((b, i) => ({ b, ev: r.evidence[i] }));
    const radar = RA.radar(criteria.map(({ b, ev }) => ({
      label: SHORT[ev && ev.id] || b.criterion, value: b.max ? (100 * b.score) / b.max : 0, title: `${b.criterion}: ${b.score}/${b.max}` })),
      "Radar chart of score criteria, each as a percent of its maximum");
    const rows = el("ul", { cls: "criteria" }, criteria.map(({ b, ev }) => {
      const pct = b.max ? Math.round((100 * b.score) / b.max) : 0;
      const n = ev ? ev.snippets.length : 0;
      const missing = ev ? ev.missing : [];
      const kids = [
        el("span", { cls: "crit-head" }, el("strong", { text: b.criterion }), el("span", { cls: "num", text: `${b.score} / ${b.max}` })),
        bar(pct),
        el("span", { cls: "crit-reason", text: b.reason }),
        el("span", { cls: "crit-ev", text: n ? `Show ${plural(n, "highlight")} in resume` : (missing.length ? "Nothing to highlight (see viewer)" : "No evidence lines") }),
      ];
      const li = el("li");
      li.appendChild(ev && (n || missing.length)
        ? hlButton("crit", ev.snippets, b.criterion, missing, ...kids)
        : el("div", { cls: "crit" }, ...kids));
      return li;
    }));
    root.appendChild(card("Where the points came from",
      el("div", { cls: "split" }, el("div", { cls: "radar-wrap" }, radar), rows),
      hint("Green highlights are text that earned points; red marks what cost points.")));

    root.appendChild(card("What to fix first", quickWins(r, ctx)));
    if (r.warnings.length)
      root.appendChild(card("Notes", el("ul", { cls: "plain-list" }, r.warnings.map((w) => el("li", { text: w })))));
    return root;
  }

  // ---------------------------------------------------------------- Bullets
  function bullets(r) {
    const b = r.bullets;
    const root = el("div", { cls: "stack" });
    if (!b.count) {
      root.appendChild(card("Bullets", empty("No bullets found", "Add bullet points under Experience or Projects so achievements can be scored.")));
    } else {
      const list = el("ul", { cls: "bullets" });
      const draw = (filter) => {
        RA.clear(list);
        b.items.filter((x) => filter === "all" || x.rating === filter).forEach((x) => {
          const issues = x.issues.length
            ? el("div", { cls: "chips" }, x.issues.map((i) => el("span", { cls: "chip chip-issue", text: i.message, attrs: { title: i.code } })))
            : null;
          list.appendChild(el("li", null,
            hlButton("bullet", [{ start: x.start, end: x.end, kind: x.rating === "weak" ? "lost" : x.rating === "ok" ? "focus" : "earned", note: `Score ${x.score}` }],
              "Bullet", null,
              el("span", { cls: "score-pill score-" + RA.kindForScore(x.score) }, el("b", { text: x.score }), el("small", { text: x.rating })),
              el("span", { cls: "bullet-body" },
                el("span", { cls: "bullet-text", text: x.text }),
                el("span", { cls: "tag", text: `${cap(x.section)} · ${x.word_count} words` }),
                issues,
                x.hint ? el("span", { cls: "bullet-hint", text: x.hint }) : null))));
        });
        if (!list.children.length) list.appendChild(el("li", { cls: "hint", text: "No bullets with this rating." }));
      };
      const select = el("select", { attrs: { id: "bullet-filter", "aria-label": "Filter bullets by rating" }, on: { change: (e) => draw(e.target.value) } },
        ...[["all", "All bullets"], ["weak", "Weak only"], ["ok", "OK only"], ["strong", "Strong only"]].map(([v, t]) => el("option", { text: t, attrs: { value: v } })));
      draw("all");
      root.appendChild(card("Bullet quality",
        el("div", { cls: "stats" }, stat(b.average_score === null ? "-" : b.average_score, "Average score"), stat(b.strong, "Strong"), stat(b.ok, "OK"), stat(b.weak, "Weak")),
        el("div", { cls: "toolbar" }, select),
        list));
    }

    const rd = r.readability;
    const blocks = [
      el("div", { cls: "stats" },
        stat(rd.avg_bullet_words === null ? "-" : rd.avg_bullet_words, "Avg words / bullet"),
        stat(rd.passive_rate_percent === null ? "-" : rd.passive_rate_percent + "%", "Passive voice"),
        stat(rd.buzzword_density, "Buzzwords / 100 words"),
        stat(rd.repeated_verbs.length, "Repeated verbs")),
    ];
    rd.notes.forEach((n) => blocks.push(el("p", { cls: "note", text: n })));
    if (rd.repeated_verbs.length) {
      blocks.push(el("h4", { text: "Repeated opening verbs" }));
      blocks.push(el("ul", { cls: "plain-list" }, rd.repeated_verbs.map((v) =>
        el("li", null, el("strong", { text: `${v.verb} × ${v.count}` }), "  Try: " + v.alternatives.join(", ")))));
    }
    if (rd.buzzwords.length) {
      blocks.push(el("h4", { text: "Buzzwords" }));
      blocks.push(chipList(rd.buzzwords.map((w) => `${w.term} × ${w.count}`), "issue"));
    }
    if (rd.passive_examples.length) {
      blocks.push(el("h4", { text: "Passive-voice lines" }));
      blocks.push(el("ul", { cls: "plain-list" }, rd.passive_examples.map((p) =>
        el("li", null, hlButton("inline", [{ start: p.start, end: p.end, kind: "focus" }], "Passive voice", null, p.text)))));
    }
    root.appendChild(card("Tone and readability", ...blocks));
    return root;
  }

  // ---------------------------------------------------------------- Skills
  const EVI = {
    demonstrated: { mark: "✓", label: "Demonstrated", help: "appears in Experience or Projects" },
    listed_only: { mark: "◐", label: "Listed only", help: "only in the Skills list, never shown in use" },
    mentioned: { mark: "○", label: "Mentioned", help: "only in the summary, education or elsewhere" },
  };

  function skills(r) {
    const se = r.skill_evidence;
    const root = el("div", { cls: "stack" });
    if (!se.skills.length) return card("Skills", empty("No recognised skills", "None of the skills in the taxonomy were found in this resume."));
    const legend = el("ul", { cls: "legend" }, Object.keys(EVI).map((k) =>
      el("li", null, el("span", { cls: "mark mark-" + k, text: EVI[k].mark, attrs: { "aria-hidden": "true" } }), el("strong", { text: EVI[k].label }), " " + EVI[k].help)));
    root.appendChild(card("Skill evidence",
      el("div", { cls: "stats" }, stat(se.demonstrated, "Demonstrated"), stat(se.listed_only, "Listed only"), stat(se.mentioned, "Mentioned")),
      legend,
      se.listed_only_skills.length ? el("p", { cls: "note", text: "Listed but never shown: " + se.listed_only_skills.join(", ") + ". Recruiters trust skills that appear inside a real bullet." }) : null));
    const groups = {};
    se.skills.forEach((s) => (groups[s.category] = groups[s.category] || []).push(s));
    Object.keys(groups).forEach((cat) => {
      root.appendChild(card(RA.catLabel(cat),
        el("div", { cls: "chips" }, groups[cat].map((s) => {
          const e = EVI[s.status];
          const ranges = s.locations.map((l) => ({ start: l.start, end: l.end, kind: "focus", note: s.skill }));
          return el("button", { cls: "chip chip-skill chip-" + s.status, attrs: { type: "button", title: `${e.label}: ${e.help}. ${plural(s.mentions, "mention")}.` },
            on: { click: () => RA.viewer.highlight(ranges, s.skill) } },
            el("span", { cls: "mark", text: e.mark, attrs: { "aria-hidden": "true" } }), s.skill, el("span", { cls: "sr-only", text: ` (${e.label})` }));
        }))));
    });
    return root;
  }

  // ---------------------------------------------------------------- Job match
  const REQ = {
    matched: { label: "Matched", kind: "good" },
    missing: { label: "Missing", kind: "bad" },
    covered_by_alternative: { label: "Covered by alternative", kind: "good" },
  };

  function requirementRow(q) {
    const st = REQ[q.status];
    const extra = [];
    if (q.status === "matched" && q.demonstrated === false) extra.push(pill("Listed only", "warn"));
    if (q.status === "matched" && q.demonstrated) extra.push(pill("Demonstrated", "good"));
    return el("li", { cls: "req" },
      el("div", { cls: "req-head" }, el("strong", { text: q.skill }), pill(st.label, st.kind), extra, el("span", { cls: "tag", text: q.weight === 2 ? "weight 2x" : "weight 1x" })),
      q.alternatives.length ? el("p", { cls: "hint", text: "Alternatives accepted: " + q.alternatives.join(", ") }) : null,
      q.hint ? el("p", { cls: "bullet-hint", text: q.hint }) : null,
      q.where_to_add.length ? el("p", { cls: "tag", text: "Add it in: " + q.where_to_add.join(" or ") }) : null);
  }

  function percentTile(label, value, sub) {
    return el("div", { cls: "pct" },
      el("div", { cls: "comp-head" }, el("span", { text: label }), el("span", { cls: "num", text: value === null ? "n/a" : value + "%" })),
      value === null ? null : bar(value), sub ? el("span", { cls: "tag", text: sub }) : null);
  }

  function jobMatch(r) {
    const root = el("div", { cls: "stack" });
    const jd = r.jd_analysis;
    if (jd) {
      const meta = [];
      if (jd.seniority) meta.push("Seniority cue: " + jd.seniority);
      if (jd.years_required !== null) meta.push(`Asks for ${jd.years_required}+ years` + (jd.resume_years_estimate !== null ? `; your resume shows about ${jd.resume_years_estimate}` : ""));
      else if (jd.resume_years_estimate !== null) meta.push(`Your resume shows about ${jd.resume_years_estimate} years of experience`);
      root.appendChild(card("Job description match",
        el("div", { cls: "pcts" },
          percentTile("Weighted match", jd.weighted_percent, "required skills count double"),
          percentTile("Required", jd.required_percent, plural(jd.required_count, "skill")),
          percentTile("Preferred", jd.preferred_percent, plural(jd.preferred_count, "skill"))),
        meta.length ? el("ul", { cls: "plain-list" }, meta.map((m) => el("li", { text: m }))) : null,
        jd.notes.map((n) => el("p", { cls: "note", text: n })),
        r.jd_match ? hint(`Simple count: ${r.jd_match.match_percent}% of the job's skills appear in the resume (every skill weighted equally).`) : null));
      ["required", "preferred"].forEach((lane) => {
        const items = jd.requirements.filter((q) => q.priority === lane);
        root.appendChild(card(cap(lane) + " skills",
          items.length ? el("ul", { cls: "reqs" }, items.map(requirementRow)) : hint(`No ${lane} skills recognised in the job description.`)));
      });
    }
    const rf = r.role_fit;
    if (rf) {
      root.appendChild(card("Role fit: " + rf.role_name,
        percentTile("Fit (70% core + 30% bonus)", rf.fit_percent),
        el("h4", { text: "Core skills" }), chipList(rf.core_matched, "good"), rf.core_missing.length ? chipList(rf.core_missing, "bad") : null,
        el("h4", { text: "Bonus skills" }), chipList(rf.bonus_matched, "good"), rf.bonus_missing.length ? chipList(rf.bonus_missing, "bad") : null,
        hint("Green = on your resume, red outlined = missing.")));
      if (rf.learn_next.length)
        root.appendChild(card("Skills to learn next",
          el("ol", { cls: "learn" }, rf.learn_next.map((l) =>
            el("li", null, el("strong", { text: l.skill }), " ", pill(l.priority, l.priority === "core" ? "bad" : "neutral"), el("p", { cls: "hint", text: l.hint }))))));
    }
    if (!jd && !rf)
      root.appendChild(card("Job match", empty("No job description or role selected",
        "Paste a job description or pick a target role, then analyze again to see required vs preferred skills, weighted match and where to add what is missing.")));
    return root;
  }

  // ---------------------------------------------------------------- ATS checks
  function atsChecks(r) {
    const a = r.ats_checks;
    const list = el("ul", { cls: "checks" }, a.items.map((c) => {
      const s = STATUS[c.status];
      const body = [
        el("span", { cls: "check-icon check-" + c.status, text: s.icon, attrs: { "aria-hidden": "true" } }),
        el("span", { cls: "check-body" },
          el("span", { cls: "check-title" }, el("strong", { text: c.title }), pill(s.label, s.kind)),
          el("span", { cls: "check-detail", text: c.detail }),
          c.fix ? el("span", { cls: "bullet-hint", text: "How to fix: " + c.fix }) : null,
          c.evidence.length ? el("span", { cls: "tag", text: `Click to highlight ${plural(c.evidence.length, "line")} in the resume` }) : null),
      ];
      const li = el("li", null);
      li.appendChild(c.evidence.length
        ? hlButton("check", c.evidence.map((e) => ({ start: e.start, end: e.end, kind: c.status === "pass" ? "earned" : "lost", note: c.title })), c.title, null, ...body)
        : el("div", { cls: "check" }, ...body));
      return li;
    }));
    return card("Parse-ability checklist",
      el("div", { cls: "stats" }, stat(a.score, "Parse-ability score"), stat(a.passed, "Passed"), stat(a.warned, "Warnings"), stat(a.failed, "Failed")),
      hint("Heuristics on the extracted text: can an automated parser read this resume cleanly?"), list);
  }

  // ---------------------------------------------------------------- Privacy view
  function withPlaceholders(text) {
    // Make [EMAIL] / [PHONE] / [URL] visible as tokens; everything else stays plain text nodes.
    const frag = document.createDocumentFragment();
    text.split(/(\[(?:EMAIL|PHONE|URL)\])/).forEach((part) => {
      if (/^\[(?:EMAIL|PHONE|URL)\]$/.test(part)) frag.appendChild(el("span", { cls: "token", text: part }));
      else if (part) frag.appendChild(document.createTextNode(part));
    });
    return frag;
  }

  function privacy(r) {
    const p = r.redacted_preview;
    const root = el("div", { cls: "stack" });
    const pre = el("pre", { cls: "plain-text" });
    pre.appendChild(withPlaceholders(p.text));
    root.appendChild(card("Exactly what an AI model would see",
      el("p", { cls: "lead", text: p.note }),
      el("div", { cls: "stats" }, stat(p.emails, "Emails removed"), stat(p.phones, "Phones removed"), stat(p.urls, "Links removed")),
      el("p", { cls: "note" }, pill(p.llm_configured ? "AI configured on this server" : "No AI key configured: nothing is sent anywhere", p.llm_configured ? "neutral" : "good")),
      pre));
    if (p.jd_text) {
      const jpre = el("pre", { cls: "plain-text" });
      jpre.appendChild(withPlaceholders(p.jd_text));
      root.appendChild(card("Job description (after redaction)", jpre));
    }
    return root;
  }

  // ---------------------------------------------------------------- AI insights
  function ai(r) {
    const l = r.llm;
    if (!l.used)
      return card("AI insights", empty("AI insights are off for this analysis", l.reason || "No AI model is configured."),
        hint("Every score and check in the other tabs is deterministic and works without AI. The AI only adds suggestions and never changes a score."));
    const root = el("div", { cls: "stack" });
    if (l.first_impression) root.appendChild(card("Recruiter's first impression", el("p", { cls: "lead", text: l.first_impression })));
    if (l.summary) root.appendChild(card("Summary", el("p", { text: l.summary })));
    if (l.suggestions.length) root.appendChild(card("Suggestions", el("ul", { cls: "plain-list" }, l.suggestions.map((s) => el("li", { text: s })))));
    if (l.bullet_rewrites.length)
      root.appendChild(card("Suggested bullet rewrites",
        hint("Checked automatically: a rewrite may not add numbers or skills that are not in the original."),
        el("ul", { cls: "rewrites" }, l.bullet_rewrites.map((w) =>
          el("li", null,
            el("div", { cls: "rw-before" }, el("span", { cls: "tag", text: `Before (score ${w.score_before})` }),
              hlButton("inline", [{ start: w.start, end: w.end, kind: "focus" }], "Original bullet", null, w.original)),
            el("div", { cls: "rw-after" }, el("span", { cls: "tag", text: "After" }), el("span", { text: w.rewrite })))))));
    if (l.interview_questions.length)
      root.appendChild(card("Interview questions to practise",
        el("ol", { cls: "plain-list" }, l.interview_questions.map((q) =>
          el("li", null, q.question + " ", el("span", { cls: "tag", text: `${q.skill}, ${q.difficulty}` }))))));
    root.appendChild(hint("AI text is generated from the redacted resume and never changes any score."));
    return root;
  }

  RA.views = { overview, bullets, skills, job: jobMatch, ats: atsChecks, privacy, ai };
})();
