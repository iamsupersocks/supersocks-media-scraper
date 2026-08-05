# Supersocks Media Scraper

[![Python >=3.10](https://img.shields.io/badge/python-%3E%3D3.10-blue)](pyproject.toml)
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-informational)](pyproject.toml)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Supersocks Media Scraper turns a public social post URL into a small, stable JSON
object of the fields that are already visible on the page. It is a private-by-default
library and CLI for developers and agent builders — not a bulk downloader, archive
tool, or login bypass.

## What you get

- A CLI and Python `scrape()` API that return the same JSON contract
- Adapters for X, Instagram, Facebook, and Reddit
- Sanitized outbound URLs (no userinfo, query, or fragment)
- Honest `action_required` / `needs-human` signals when a page needs a person
- Optional extras so you only install the backends you need

Not exhaustive. Not a media download tool. Never automates login, MFA, CAPTCHA,
consent, or rate-limit evasion. Cookies, tokens, and profile paths never appear
in output.

## Supported platforms

| In this package | Stays in [`supersocks-url-scraper`](https://github.com/iamsupersocks/supersocks-url-scraper) |
| --- | --- |
| X / Twitter | LinkedIn public pages |
| Instagram | YouTube |
| Facebook | Generic HTTP / articles / PDF |
| Reddit | |

**URL Scraper boundary:** LinkedIn, YouTube, and generic page/article/PDF reads
belong in `supersocks-url-scraper`. This package only handles the four social
platforms above.

## Terms used here

- **Optional extra** — a pip/pipx install group such as `[x]`, `[browser]`, or
  `[all]` that pulls optional dependencies. The base install has no hard
  third-party runtime deps.
- **CloakBrowser** — the optional browser engine used for Instagram, Facebook,
  and Reddit when you install the `[browser]` (or `[all]`) extra.
- **Persistent profile** — a per-platform browser profile directory under
  `MEDIA_BROWSER_PROFILES_ROOT/{reddit|instagram|facebook}` (or an explicit
  `--browser-profile-dir`). Profiles hold session state you create yourself;
  the package never invents cookies.
- **Headed warm-up** — opening a real browser window with `--warmup` so you can
  complete login, consent, or challenge manually. Never automated.
- **needs-human** — the `action_required.code` value when the page requires a
  person (`reason` is one of `login`, `mfa`, `captcha`, `consent`, `challenge`,
  `rate-limit`).
- **twitter-cli** — the optional X/Twitter backend (`twitter` on PATH, or
  `python -m twitter_cli.cli` when the module is importable). Required for X
  reads when using the `[x]` / `[all]` extra.

`clix` is a separate, unsupported backend and is not needed for public use of
this package.

## Install chooser

| Extra | Installs | Who it is for |
| --- | --- | --- |
| `[all]` | `twitter-cli` + `cloakbrowser` | **Recommended for most users** — X plus Meta/Reddit browser reads |
| `[x]` | `twitter-cli` | X/Twitter only |
| `[browser]` | `cloakbrowser` | Instagram / Facebook / Reddit only |
| *(base)* | nothing optional | Integrators who bring their own backends / test harnesses |

### From GitHub (PEP 508)

```bash
# Recommended: X + CloakBrowser
pipx install 'supersocks-media-scraper[all] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# X/Twitter backend only
pipx install 'supersocks-media-scraper[x] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# CloakBrowser for Instagram / Facebook / Reddit
pipx install 'supersocks-media-scraper[browser] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# Base API/CLI only (no optional backends)
pipx install 'git+https://github.com/iamsupersocks/supersocks-media-scraper.git'
```

### From a clone

```bash
pip install -e '.[test]'
pip install -e '.[x]'
pip install -e '.[browser]'
pip install -e '.[all]'
```

With pipx and the `[x]` extra, the `twitter` binary may be missing from PATH;
the X adapter falls back to `python -m twitter_cli.cli` in the same environment.

**pipx** is an isolated CLI installer: each tool gets its own virtualenv without
touching your system Python.

## Five-minute quick start (one public URL)

1. Install the recommended extra:

   ```bash
   pipx install 'supersocks-media-scraper[all] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'
   ```

2. Scrape a public Reddit post URL (no X credentials required):

   ```bash
   supersocks-media-scraper 'https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/'
   ```

3. Only if the JSON includes `action_required` with `needs-human`, configure a
   browser profile, run a headed warm-up once, complete any login/consent in
   the browser window yourself, then retry the same URL:

   ```bash
   export MEDIA_BROWSER_PROFILES_ROOT="$HOME/media-browser-profiles"
   # Linux: attach an existing DISPLAY or Xvfb yourself first (this package
   # never installs or starts Xvfb). Example if you already run Xvfb on :99:
   # export DISPLAY=:99
   supersocks-media-scraper --warmup reddit --create-profile --warmup-seconds 120
   supersocks-media-scraper 'https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/'
   ```

Useful CLI flags (validated against the code): `--max-chars`, `--max-comments`,
`--timeout`, `--browser-profile-dir`, `--headed`, `--warmup`, `--create-profile`,
`--warmup-seconds`, `--warmup-url`, `--version`.

## Python API

```python
from supersocks_media_scraper import scrape

result = scrape(
    "https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/"
)
print(result["status"], result["platform"], result["text"][:200])
```

## Example JSON (stable contract)

Compact realistic payload matching the schema (fields absent on a page stay
`null` / empty):

```json
{
  "status": "ok",
  "platform": "reddit",
  "content_kind": "post",
  "source_url": "https://www.reddit.com/r/announcements/comments/abc123/example/",
  "final_url": "https://www.reddit.com/r/announcements/comments/abc123/example/",
  "title": "Example announcement",
  "text": "Visible post body truncated to --max-chars.",
  "author": {
    "name": "example_user",
    "handle": "example_user",
    "url": "https://www.reddit.com/user/example_user"
  },
  "published_at": "2024-06-01T12:00:00+00:00",
  "metrics": {
    "likes": 42,
    "comments": 3,
    "shares": null,
    "views": null
  },
  "media": [
    {
      "kind": "image",
      "url": "https://i.redd.it/example.png",
      "alt": null
    }
  ],
  "comments": [
    {
      "author": "reply_user",
      "text": "Visible comment text only.",
      "published_at": null
    }
  ],
  "warnings": [],
  "action_required": null
}
```

When a gate blocks the read, `status` is typically `error` or `partial` and
`action_required` looks like:

```json
{
  "code": "needs-human",
  "reason": "login",
  "platform": "instagram",
  "resume_instructions": "Run a headed warm-up, complete login manually, then retry the same URL."
}
```

## Authentication (honest)

| Platform | What you must provide |
| --- | --- |
| **X / Twitter** | Install `[x]` or `[all]`. Export **both** `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in your shell (see below). |
| **Instagram / Facebook / Reddit** | Install `[browser]` or `[all]`. A cold profile often returns `needs-human`; one manual headed warm-up may be required. |

**X credentials in plain English:** `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` are two
sensitive cookie values from your signed-in x.com session — effectively
credentials for that account. Obtain and export them manually with a cookie
inspection or export tool (for example Cookie-Editor). Never print, share, or
commit them. This scraper never reads your browser cookie store; it only uses
values you explicitly export into the shell.

There is **no** automated login, MFA, CAPTCHA, consent wall, or rate-limit bypass.

```bash
export TWITTER_AUTH_TOKEN='paste-auth-token-from-x.com-cookies'
export TWITTER_CT0='paste-ct0-from-x.com-cookies'
supersocks-media-scraper 'https://x.com/example/status/1234567890123456789'
```

## Linux headless / headed notes

- Default Cloak reads run headless when a display is not forced.
- `--headed` and `--warmup` need a real display: on Linux, set `DISPLAY` or
  `WAYLAND_DISPLAY` yourself (for example attach an existing Xvfb session).
- **The Python package itself does not install or start Xvfb.** The optional
  Docker `warmup` image does (see below).

## Docker (runtime + guided warm-up)

Prerequisites on the host:

- Docker Engine (Linux) with permission to build and run images
- For X reads: export `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in your shell
  (values never appear in images, READMEs, or scraper JSON)
- Named volume `sms-media-profiles` for Reddit / Instagram / Facebook profiles
  (shared by Compose `scraper` and `warmup` services)

Two Dockerfile targets:

| Target | Purpose |
| --- | --- |
| `runtime` (default) | Lean headless scraper (Cloak Chromium pre-cached at build) |
| `warmup` | Same non-root user + Xvfb, openbox, x11vnc, noVNC/websockify for guided login |

### One-command guided warm-up (key in hand)

Warm a platform profile once, complete login/consent/challenge yourself in the
browser, then reuse the same named volume headless:

```bash
git clone https://github.com/iamsupersocks/supersocks-media-scraper.git
cd supersocks-media-scraper

# Build + start noVNC warm-up (allowlisted: reddit|instagram|facebook)
WARMUP_PLATFORM=instagram docker compose up --build warmup
```

In another terminal (or local browser on the Docker host):

```text
http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale
```

Complete any login, consent, or challenge manually in the noVNC session. Stop
the warm-up service when finished (`Ctrl+C`). Sessions can expire later — re-run
warm-up if headless reads return `needs-human` again.

**SECURITY:** noVNC has **no password**. Compose publishes **only**
`127.0.0.1:6080`. Never change the port mapping to `0.0.0.0` / a public bind.
Do not expose 6080 on the internet.

Remote Linux host — SSH local-forward, then open the same URL on your laptop:

```bash
ssh -L 6080:127.0.0.1:6080 user@docker-host
```

Optional longer wait (default `WARMUP_SECONDS=600`):

```bash
WARMUP_PLATFORM=reddit WARMUP_SECONDS=900 docker compose up --build warmup
```

### Resume headless scrape (same volume)

```bash
docker compose run --rm scraper \
  'https://www.instagram.com/p/EXAMPLE/'
```

Equivalent with plain Docker after `docker build` (default target = lean runtime):

```bash
docker build -t supersocks-media-scraper:runtime .
docker run --rm \
  -v sms-media-profiles:/home/scraper/media-browser-profiles \
  supersocks-media-scraper:runtime \
  'https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/'
```

X credentials as environment variables (pass from your shell; do not bake them
into the image or print them; the scraper never inspects browser cookies):

```bash
docker compose run --rm \
  -e TWITTER_AUTH_TOKEN \
  -e TWITTER_CT0 \
  scraper \
  'https://x.com/example/status/1234567890123456789'
```

Profiles live under `MEDIA_BROWSER_PROFILES_ROOT/{reddit|instagram|facebook}`
inside the container (`/home/scraper/media-browser-profiles/...`) on the shared
named volume `sms-media-profiles`.

**Headless cold profile vs headed warm-up:** a cold profile does not bypass
Instagram / Facebook / Reddit login, consent, or challenge gates. Use the
`warmup` Compose service (or a host display with `--warmup`) once as an
operator. Docker does **not** bypass platform gates, CAPTCHA, MFA, or rate
limits. Images have no fake healthcheck and never automate login.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing X backend | Install `[x]` or `[all]`. Confirm `twitter` on PATH or that `python -m twitter_cli.cli` imports in the same env. |
| X `needs-human` / login | Export both `TWITTER_AUTH_TOKEN` and `TWITTER_CT0`. Do not rely on browser auto-read. |
| Missing CloakBrowser | Install `[browser]` or `[all]`. |
| Profile not configured | Set `MEDIA_BROWSER_PROFILES_ROOT` (uses `{root}/{platform}`) or pass `--browser-profile-dir`. Use `--create-profile` during warm-up. |
| Meta/Reddit `needs-human` | Run `--warmup <platform> --create-profile`, or `WARMUP_PLATFORM=... docker compose up warmup`, complete login/consent/challenge manually, retry. |
| Rate-limit / 429 / “Prove your humanity” | Stop and wait; do not automate evasion. `action_required.reason` may be `rate-limit` or `challenge`. |
| Headed warm-up fails on Linux | Attach an existing `DISPLAY` / `WAYLAND_DISPLAY` / Xvfb session, or use the Docker `warmup` target. |
| Docker browser launch / missing libraries | Use the official Dockerfile in this repo (it installs Chromium Linux deps). Public JSON warnings stay actionable and never dump local paths or launch command lines. |
| Docker noVNC unreachable | Confirm Compose still maps `127.0.0.1:6080:6080`. On a remote host, use `ssh -L 6080:127.0.0.1:6080`. |
| Invalid `WARMUP_PLATFORM` | Allowlist only: `reddit`, `instagram`, `facebook`. |

## License and credits

MIT — see [LICENSE](LICENSE).

Portions adapted from [`supersocks-url-scraper`](https://github.com/iamsupersocks/supersocks-url-scraper) (MIT).
