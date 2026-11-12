# Deploying to Render (free tier)

> **Untested.** `render.yaml`, this guide and the `Dockerfile` were written without Docker
> installed and without a Render account, so none of them has been built or run. The app itself
> runs locally (`resume-analyzer serve`) and is covered by the test suite. Expect to fix small
> things on the first deploy, and update this page when you do.

## Option A: Blueprint from the Dockerfile

1. Push the repository to GitHub.
2. In Render: **New > Blueprint**, pick the repository. Render reads `render.yaml`.
3. When asked for `GEMINI_API_KEY`, either paste a key or leave it empty (see below).
4. Wait for the build. Open the service URL; `/api/health` should return `{"status": "ok", ...}`.

## Option B: native Python (no Docker)

Create a **Web Service**, runtime **Python 3**, and set:

- Build command: `pip install .`
- Start command: `uvicorn resume_analyzer.api:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`
- The environment variables below.

## Environment variables

All are optional.

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Port to listen on. Render sets it; the Dockerfile command uses it. |
| `WEB_CONCURRENCY` | unset | Number of uvicorn worker processes (read by uvicorn). Keep it at `1` on the free tier. The rate limit is counted per worker, so N workers allow roughly N times the limit. |
| `RATE_LIMIT_MAX` | `20` | Analyses allowed per client per window. `0` turns the limit off. |
| `RATE_LIMIT_WINDOW_SECONDS` | `600` | Window length in seconds. |
| `TRUST_PROXY` | `false` | **Set to `true` on Render.** Behind Render's proxy every request appears to come from the proxy, so without it all visitors share one IP and one rate-limit bucket. When `true`, the last `X-Forwarded-For` entry (added by Render's proxy) is used. Do not enable it when the app is directly exposed, because clients could then forge the header. |
| `CORS_ORIGINS` | empty | Comma-separated origins allowed to call the API from another site. Empty disables CORS, which is right when the page is served by the same service. |
| `MAX_UPLOAD_MB` | `5` | Upload size limit. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model for the optional AI insights. |
| `GEMINI_API_KEY` | unset | Enables AI insights (see next section). |

## Adding GEMINI_API_KEY as a secret

The app works without a key: every score is deterministic and AI insights are marked as not
used. To enable them:

1. In the Render dashboard open the service > **Environment**.
2. Add `GEMINI_API_KEY` with your own key as the value. Render stores environment values
   privately; with the Blueprint the entry is declared with `sync: false`, so the value is never
   in the repository.
3. Save. Render redeploys. `/api/health` then reports `"llm_configured": true`.

Never commit a key, and never put it in `render.yaml` or the Dockerfile. When a key is set,
only redacted text is sent to the model (see the Privacy view in the app).

## Free-tier cold starts

Free web services on Render spin down after a period without traffic. The first request after
that can take tens of seconds while the service starts again, then it is fast. This is a hosting
property, not an app bug. Before showing the demo to someone, open the URL once to wake it. The
rate-limit counters live in memory, so they also reset on every restart.

## After deploying

- Open the URL and press **Try a sample resume**.
- Check `/api/health`, and check the security headers on the page (for example in the browser's
  network tab).
- Put the live URL in the README's `Live demo` line, replacing `[TODO]`.
