# OSINT Lookup

FastAPI app that checks where an email or username is registered.

- Email: our own checks in `email_checks.py` (20 sites: Adobe, Atlassian, Chess.com, Codecademy, Duolingo, Firefox, GitHub (public commits by the address), Gravatar, HubSpot, Internet Archive, Komoot, LastPass, Microsoft, Snapchat, Spotify, Tumblr, Twitter / X, Vivino, WordPress.com, Zoho) and [GHunt](https://github.com/mxrch/GHunt) (public Google account info: Gaia ID, profile photo, last profile edit, Maps contributions, public Calendar, Play Games). Each check uses one public, unauthenticated signup or login signal and answers Found, Not Found or Couldn't check (blocked or changed, so unknown). Duolingo, GitHub and Gravatar also return the profile link, username and, for Duolingo, the creation date.
- Username: public profile checks in `email_checks.py` (Chess.com, Duolingo, GitHub, Gravatar: profile link, created and last active dates) and [Sherlock](https://github.com/sherlock-project/sherlock).

## Self-test

Sites change their signup APIs, so every email check is tested against a known registered address and a random unused one: `python selftest.py` locally, or `GET /api/selftest` on the app (cached for 30 minutes, HTTP 503 when a check is broken). The `Daily email check self-test` GitHub Actions workflow calls the deployed app every day and fails, listing the broken checks, when one stops working. To add a site, add a function and an `EMAIL_CHECKS` entry in `email_checks.py`, then run the self-test.

## Run

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Tests (no network): `pip install pytest && python -m pytest tests`.

GHunt needs Python 3.10+.

## GHunt setup

GHunt needs a logged-in Google account (use a throwaway Gmail). Without it the app still runs and shows GHunt as "Not configured".

1. Install GHunt locally (`pip install ghunt`) and run `ghunt login`.
2. Get the login code with either:
   - the [GHunt Companion Firefox add-on](https://addons.mozilla.org/en-US/firefox/addon/ghunt-companion/) (the Chrome listing was removed): pick the clipboard method, sign in with the throwaway Gmail, and choose option 2 in `ghunt login` to paste it; or
   - no extension: sign in at [this Google page](https://accounts.google.com/o/oauth2/programmatic_auth?client_id=1070009224336-sdh77n7uot3oc99ais00jmuft6sk2fg9.apps.googleusercontent.com&scope=https://www.google.com/accounts/OAuthLogin&access_type=offline&set_oauth_token_cookie=true), copy the `oauth_token` cookie of accounts.google.com from DevTools (starts with `oauth2_4/`), and choose option 3 in `ghunt login`.

   The code expires within minutes.
3. GHunt prints the account and saves `~/.malfrats/ghunt/creds.m`. Set one of these environment variables where the app runs (on Render: Environment tab):
   - `GHUNT_MASTER_TOKEN`: the `master_token` value (starts with `aas_et/`) from that file: `base64 -d ~/.malfrats/ghunt/creds.m | python3 -c "import json,sys;print(json.load(sys.stdin)['android']['master_token'])"`
   - or `GHUNT_CREDS`: the whole contents of `creds.m`.

Treat the master token like the account password. The app refreshes Google cookies from it on its own and caches them in `$TMPDIR/ghunt/creds.m` (override with `GHUNT_CREDS_PATH`).
