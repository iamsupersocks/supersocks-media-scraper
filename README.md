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
- **This package does not install or start Xvfb.**

## Docker (official runtime)

Prerequisites on the host:

- Docker Engine (Linux) with permission to build and run images
- For X reads: export `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in your shell
  (values never appear in images, READMEs, or scraper JSON)
- Optional named volume for Reddit / Instagram / Facebook persistent profiles

Build the official Python 3.12 slim image (installs CloakBrowser/Chromium Linux
dependencies, the local package with `[all]`, and runs as a non-root user with a
writable Cloak cache + `MEDIA_BROWSER_PROFILES_ROOT`):

```bash
git clone https://github.com/iamsupersocks/supersocks-media-scraper.git
cd supersocks-media-scraper
docker build -t supersocks-media-scraper:local .
docker run --rm supersocks-media-scraper:local --version
```

Scrape a public URL headless (cold profile — often returns `needs-human` until
you warm a profile on a machine with a real display):

```bash
docker run --rm \
  -v sms-media-profiles:/home/scraper/media-browser-profiles \
  supersocks-media-scraper:local \
  'https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/'
```

X credentials as environment variables (pass from your shell; do not bake them
into the image or print them):

```bash
docker run --rm \
  -e TWITTER_AUTH_TOKEN \
  -e TWITTER_CT0 \
  supersocks-media-scraper:local \
  'https://x.com/example/status/1234567890123456789'
```

The image initializes empty per-platform profile directories on first use.
Named-volume profile persistence for Reddit / Instagram / Facebook maps to
`MEDIA_BROWSER_PROFILES_ROOT/{reddit|instagram|facebook}` inside the container
(`/home/scraper/media-browser-profiles/...`). Reuse the same volume across runs.

**Headless cold profile vs headed warm-up:** the standard image is headless. A
cold profile does not bypass Instagram / Facebook / Reddit login, consent, or
challenge gates. Manual headed warm-up (`--warmup` / `--headed`) requires a
display attached outside this headless container (for example X11/Wayland/Xvfb
on the host, or a custom image/session you manage). Docker does **not** bypass
platform gates, CAPTCHA, MFA, or rate limits. This image has no fake healthcheck
and never automates login.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing X backend | Install `[x]` or `[all]`. Confirm `twitter` on PATH or that `python -m twitter_cli.cli` imports in the same env. |
| X `needs-human` / login | Export both `TWITTER_AUTH_TOKEN` and `TWITTER_CT0`. Do not rely on browser auto-read. |
| Missing CloakBrowser | Install `[browser]` or `[all]`. |
| Profile not configured | Set `MEDIA_BROWSER_PROFILES_ROOT` (uses `{root}/{platform}`) or pass `--browser-profile-dir`. Use `--create-profile` during warm-up. |
| Meta/Reddit `needs-human` | Run `--warmup <platform> --create-profile`, complete login/consent/challenge manually, retry. |
| Rate-limit / 429 / “Prove your humanity” | Stop and wait; do not automate evasion. `action_required.reason` may be `rate-limit` or `challenge`. |
| Headed warm-up fails on Linux | Attach an existing `DISPLAY` / `WAYLAND_DISPLAY` / Xvfb session first. |
| Docker browser launch / missing libraries | Use the official Dockerfile in this repo (it installs Chromium Linux deps). Public JSON warnings stay actionable and never dump local paths or launch command lines. |
| Docker headed warm-up | Not supported in the standard headless image; use a host display outside the container. |

## License and credits

MIT — see [LICENSE](LICENSE).

Portions adapted from [`supersocks-url-scraper`](https://github.com/iamsupersocks/supersocks-url-scraper) (MIT).
