# AI Resume Analyzer v2 — Build Spec

v1 (see `docs/SPEC.md`, `docs/ARCHITECTURE.md`) is a solid deterministic pipeline with a plain one-page UI.
v2 makes it **advanced** (more analysis layers) and **polished** (a real product UI), and makes it
**deploy-ready**. Core principle is unchanged: **deterministic first, LLM second; the LLM never changes
a score; everything works with no API key.** Existing guardrails and tests must keep passing.

## Hard rules
- Keep every v1 guardrail and test green. Add tests for everything new (offline, FakeLLM). Target: all new modules covered.
- No invented facts or claims in docs; no fabricated metrics. Eval numbers only from running the eval.
- Fictional sample data only (example.com emails, 555 phones, obviously fake names).
- No secrets, no `.env`, no tracking/analytics, no resume storage. In-memory only.
- Do not git commit/push/switch branches. Do not deploy. Docker is NOT installed here: write Docker/Render config carefully but say it is untested.
- Readable by a final-year student who must explain it in an interview: small functions, docstrings, comments on *why*. No over-engineering, no heavy frameworks, no DB.

## New analysis layers (all deterministic, pure functions, each in its own module + tests)
1. **Bullet analyzer** (`bullets.py`): split experience/projects into bullets; score each 0-100 on action verb,
   quantification, length (ideal 12-28 words), weak phrases ("responsible for", "worked on", "helped"),
   buzzwords, first-person pronouns, tense consistency. Return per-bullet score, issues, and a deterministic
   improved-rewrite *template hint* (e.g. "Start with a strong verb; add a metric: 'Reduced X by N%'") — not invented numbers.
2. **ATS parse-ability check** (`ats_checks.py`): detect risk signals in extracted text: missing contact info, no
   email/phone, inconsistent date formats, multiple-column artifacts, very long lines/tables, special bullet glyphs,
   missing standard section headings, resume too long/short, section order. Output pass/warn/fail checklist with explanations.
3. **JD intelligence** (`jd.py` extends matching): split JD into *required* vs *preferred* (heading + phrase cues:
   "must", "required", "nice to have", "bonus"); weight required 2x; extract years-of-experience asks and seniority
   cue; produce weighted match %, per-skill status, and "where to add it" hints (which resume section).
4. **Role profiles** (`roles.py` + `data/roles.json`): ~8 target roles (ML Engineer, Data Analyst, Data Scientist,
   Backend/Python Developer, Frontend Developer, DevOps/Cloud, Full-Stack, Automation/RPA Engineer) each with core
   and bonus skills. With no JD, user can pick a role to get role-fit % and a ranked "skills to learn next" list
   (missing core skills first, with related-skill hints from the taxonomy).
5. **Evidence + explainability**: for every score criterion return *evidence snippets* (the lines that earned or lost
   points) and character offsets so the UI can highlight them in the resume text.
6. **Tone & readability** (`readability.py`): passive-voice rate, average sentence/bullet length, buzzword density,
   repeated-verb detection ("Developed" x6) with suggested alternatives from a small verb bank.
7. **Skill depth signals**: for each found skill, count mentions and whether it appears in experience/projects
   (evidence of use) vs only in a skills list; flag "listed but never demonstrated".
8. **Privacy view**: endpoint/field returning the exact redacted text the LLM would see (so users can verify guardrail 1),
   with redaction counts. Works without a key.
9. **Optional LLM layer additions** (still guarded: redaction, delimiters, schema validation + retries, grounding, bounds,
   fallback): a tailored rewrite for up to 3 weakest bullets (must not add numbers/skills not in the original — grounding
   check enforces; drop violators), and a 3-sentence "recruiter's first impression". LLM output never alters scores.
10. **Overall report**: combine ATS score (existing), bullet quality avg, parse-ability, JD/role fit into a clearly
    labelled *composite readiness* view WITHOUT replacing the v1 explainable ATS score (keep both; explain each).

## API (keep v1 `POST /api/analyze` response backward compatible; add fields)
- `POST /api/analyze` multipart: `resume`, optional `job_description`, optional `role` (id from `/api/roles`).
  New response fields: `bullets`, `ats_checks`, `jd_analysis`, `role_fit`, `readability`, `skill_evidence`, `evidence`, `redacted_preview`.
- `GET /api/roles`, `GET /api/sample` (returns a fictional sample resume + JD for the "Try a sample" button),
  `GET /api/health` (+ version).
- `POST /api/report` or client-side export: Markdown and JSON download; print-friendly CSS for "Save as PDF".
- Public-deploy hardening: simple in-memory per-IP rate limit (e.g. 20 analyses/10 min, configurable via env), request size
  limit already exists, security headers (CSP suited to the static page, X-Content-Type-Options, Referrer-Policy,
  X-Frame-Options), CORS disabled by default, `PORT` env respected, `WEB_CONCURRENCY` documented.

## UI (static, no framework build step; vanilla JS + CSS modules in `static/`, served by FastAPI)
Make it feel like a real product, not a form:
- Landing/hero with one-line value prop, privacy note, **drag-and-drop upload**, **"Try a sample resume"** button
  (no upload needed — essential for recruiters visiting the demo), role selector, JD textarea (collapsible).
- Results as a dashboard: **animated score gauge**, **radar/bar chart of score criteria** (inline SVG, no chart lib),
  **tabs/sections**: Overview · Bullets · Skills · Job match · ATS checks · Privacy view · AI insights.
- **Resume viewer with highlights**: evidence snippets highlighted in the resume text; click a criterion to jump/highlight.
- Bullets table with per-bullet score pills and issues; skills as grouped chips with "demonstrated vs listed only" marks;
  JD match with required/preferred lanes and "where to add" hints; ATS checklist with pass/warn/fail icons.
- **Light/dark theme** (system default + toggle), responsive down to 360px, keyboard accessible, visible focus,
  reduced-motion respected, AA contrast, loading skeleton and friendly error states, no layout shift.
- Export buttons: Download JSON, Download Markdown, Print/Save as PDF.
- Distinctive but professional look (not generic purple-gradient AI template); one accent color; real typography;
  fonts may be system stack (no external requests) to keep the privacy promise.
- All user text inserted via textContent (no innerHTML with user data) — XSS-safe; test for it.

## Quality
- ruff clean, pytest all green, eval script extended (add bullets/ATS sanity checks on the 4 samples; keep F1 gate) and
  CI updated. Add a few more fictional samples if needed (e.g. a weak resume that should score low) so the layers are
  demonstrably discriminating — e.g. tests asserting weak < strong.
- Update `docs/ARCHITECTURE.md` (new Mermaid diagram of layers, guardrail table still accurate), `README.md`
  (recruiter-first, accurate feature list; screenshots placeholders for new UI at `docs/screenshots/*.png` — the lead will
  capture them; live demo line stays `[TODO]` until deployed), and add `render.yaml` + `DEPLOY.md` (Render free web service
  from the Dockerfile or native Python: build/start commands, env vars, free-tier cold-start note, how to add GEMINI_API_KEY
  as a secret). State clearly that deploy config is untested here.
- Bump version to 2.0.0.
