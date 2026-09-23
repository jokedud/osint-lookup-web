# OSINT Hub (osint-lookup-web)

A self-hosted web app that shows, live, which sites and accounts are attached
to an email address, username, or phone number. Results stream over SSE with
clickable profile links so you can verify each hit.

## Features

- **Email** — syntax/MX/disposable/provider checks, Gravatar profile lookup,
  [holehe](https://github.com/megadose/holehe) (100+ sites), HaveIBeenPwned
  breaches, [GHunt](https://github.com/mxrch/GHunt) for Google accounts, and
  custom best-effort checks for Pinterest, Adobe, Grammarly and Duolingo.
- **Username** — [maigret](https://github.com/soxoj/maigret) (top 500 sites by
  ranking) and [sherlock](https://github.com/sherlock-project/sherlock).
- **Phone** — validation, region/carrier/timezone/type via `phonenumbers`, plus
  lookup links for WhatsApp, Telegram and TrueCaller.
- Dark-theme UI: found-only filter, per-tool toggles, summary chips, pivots
  (email → username of the local part, phone hints → phone scan), JSON/CSV
  export, and localStorage scan history.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```

Open http://localhost:8000

## Optional configuration

Copy `.env.example` to `.env` or set environment variables directly:

- `HIBP_API_KEY` — enables HaveIBeenPwned breach lookups.
- GHunt — run `ghunt login` once to store Google credentials
  (`~/.malfrats/ghunt/creds.m`); email scans then include Google account data
  (Gaia ID, profile photo, Maps reviews, etc.).

## Deploy on Render

`render.yaml` is preconfigured (`pip install -r requirements.txt`, then
`uvicorn main:app --host 0.0.0.0 --port $PORT`, `PYTHON_VERSION=3.12`).
`main.py` at the repo root is a thin shim (`from app.main import app`) so the
start command works unchanged. Set `HIBP_API_KEY` in the Render dashboard if
you want breach lookups.

Note: on shared hosting IPs (including Render) many holehe modules will
report `rate_limited` — that's expected; found/not_found results are still
accurate for the modules that get through.

## Legal / ethical note

Only investigate email addresses, usernames and phone numbers that **you own**
or are **explicitly authorized** to investigate. Unauthorized use may violate
the target sites' terms of service and applicable law.

## Layout

```
main.py            shim -> app.main:app (Render entry point)
app/main.py        FastAPI app (static UI + /api)
app/api.py         SSE scan endpoints
app/scanners/      one module per tool
static/            vanilla JS frontend (no build step)
```
