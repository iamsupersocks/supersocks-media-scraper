# Live testing (smoke harness)

Dated guide for running the four-platform live smoke harness against
`supersocks-media-scraper`. This is a reproducible verification helper, not a
claim of universal scraping.

**Baseline commit (clean main start):** `95d59fa01f4226d10d99776ca2efbf58698cf0f1`
**Harness commit:** `fd2fcb140688753d7b4136edc32b6d1a074c817f`
**Evidence commit:** `c8375a83e807e228b1f0e2822eeaa1874ecceae0`
**Doc date:** 2026-08-06

Live network rows below record only observed evidence. Warmed or authenticated
reruns are listed separately when not performed.

## What the harness does

Entry points:

```bash
supersocks-media-scraper-smoke
# or
python -m supersocks_media_scraper.live_smoke
```

It invokes the **installed/current** scraper CLI (`supersocks-media-scraper` on
PATH, else `python -m supersocks_media_scraper.cli`) for each requested
platform, classifies the JSON, and prints one sanitized aggregate summary.

Classifications (minimum set):

| Classification | Meaning |
| --- | --- |
| `content-success` | Valid stable JSON with non-empty useful content (text/title/author/media/comments) |
| `needs-human` | Valid JSON with `action_required.code=needs-human` — **not** successful extraction |
| `runtime-error` | Invocation failure, non-JSON stdout, or empty extraction without a human gate |
| `unsupported/invalid` | Bad/unsafe URL or platform mismatch |
| `schema-error` | JSON missing required contract fields, unsanitized URLs, or banned fields |

Exit modes:

- **Default verify** (`--require-success` off): exit `0` when every requested
  platform is `content-success` **or** honest `needs-human`.
- **`--require-success`**: exit `0` only when every requested platform is
  `content-success`.

The summary never prints cookie values, `TWITTER_*` secrets, profile paths, or
raw browser dumps. `auth_hints` reports **presence booleans only**.

X remains explicit `TWITTER_AUTH_TOKEN` + `TWITTER_CT0` only. The harness does
not inspect browser cookie stores.

## Local install

```bash
git clone https://github.com/iamsupersocks/supersocks-media-scraper.git
cd supersocks-media-scraper
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all,test]'
```

Minimal browser-only or X-only installs also work:

```bash
pip install -e '.[browser,test]'   # reddit / instagram / facebook
pip install -e '.[x,test]'         # x only
```

## Docker

Runtime image (headless scraper):

```bash
docker build -t supersocks-media-scraper:runtime .
docker run --rm \
  -v sms-media-profiles:/home/scraper/media-browser-profiles \
  supersocks-media-scraper:runtime \
  'https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/'
```

Guided warm-up (noVNC on loopback only):

```bash
docker compose up --build warmup
# open http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale
# complete login/consent/challenge manually, then stop
```

Smoke inside a local venv still talks to the same backends; Docker is optional
for profile warm-up and dependency packaging. Do not bake tokens into images.

## Default public smoke URLs (overridable)

| Platform | Default URL |
| --- | --- |
| x | `https://x.com/X/status/20` |
| reddit | `https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/` |
| instagram | `https://www.instagram.com/instagram/` |
| facebook | `https://www.facebook.com/facebook/` |

Overrides:

```bash
supersocks-media-scraper-smoke \
  --url-x 'https://x.com/<user>/status/<id>' \
  --url-reddit 'https://www.reddit.com/r/<sub>/comments/<id>/<slug>/' \
  --url-instagram 'https://www.instagram.com/p/<shortcode>/' \
  --url-facebook 'https://www.facebook.com/<page>/posts/<id>'
```

Subset:

```bash
supersocks-media-scraper-smoke --platforms reddit,instagram
```

Profile / options (paths are passed to the child process, never printed):

```bash
export MEDIA_BROWSER_PROFILES_ROOT="$HOME/media-browser-profiles"
supersocks-media-scraper-smoke --profiles-root "$MEDIA_BROWSER_PROFILES_ROOT" --timeout 60
```

## Commands

Anonymous / cold-profile baseline (default verify):

```bash
# No X tokens, cold or absent Cloak profiles — needs-human is an acceptable pass
supersocks-media-scraper-smoke
echo $?   # 0 if each platform is content-success or needs-human
```

Strict content requirement:

```bash
supersocks-media-scraper-smoke --require-success
echo $?   # 0 only if every platform returned non-empty useful content
```

Warmed / authenticated rerun:

```bash
# X: export both tokens manually (never commit; never auto-read browser cookies)
export TWITTER_AUTH_TOKEN='…'
export TWITTER_CT0='…'

# Browser platforms: warm once, then retry
export MEDIA_BROWSER_PROFILES_ROOT="$HOME/media-browser-profiles"
supersocks-media-scraper --warmup reddit --create-profile --warmup-seconds 120
# (likewise instagram / facebook, or docker compose warmup)

supersocks-media-scraper-smoke --require-success --profiles-root "$MEDIA_BROWSER_PROFILES_ROOT"
```

## Interpreting results

1. Read `pass`, `mode`, and per-case `classification`.
2. `needs-human` means the scraper returned a stable gate (`login`, `mfa`,
   `captcha`, `consent`, `challenge`, `rate-limit`). Warm or authenticate, then
   rerun. Do not treat it as scraped content.
3. `content-success` means useful visible fields were present. Still not an
   archive guarantee.
4. `schema-error` / `runtime-error` are failures in both modes.
5. `auth_hints.x_env_present` and `*_configured` are booleans only.

## Deterministic coverage (offline, separate from live)

Parser/routing/sanitize contracts are covered by pytest fixtures — no network:

```bash
pytest -q
```

Notable offline suites:

| Area | Tests |
| --- | --- |
| Schema + URL/secret scrubbing | `tests/test_sanitize_schema.py` |
| Cloak HTML fixtures (reddit/instagram/facebook) | `tests/test_cloak_html.py` |
| X adapter mocked twitter-cli | `tests/test_x_adapter.py` |
| Routing / warm-up / CLI offline | `tests/test_routing_warmup_cli.py` |
| Browser error sanitization | `tests/test_browser_error_sanitize.py` |
| Docker contract text | `tests/test_docker_contract.py` |
| Smoke classifier / exit modes / redaction | `tests/test_live_smoke.py` |

Keep fixture results separate from the live matrix below.

## Verification matrix (2026-08-06)

**Environment (Codex independent QA, Docker):**

| Field | Value |
| --- | --- |
| Date | 2026-08-06 |
| Repo | supersocks-media-scraper |
| Commit | `c8375a83e807e228b1f0e2822eeaa1874ecceae0` |
| Host | Linux x86_64 |
| Image | `supersocks-media-scraper:smoke-c8375a8` (`docker build -t supersocks-media-scraper:smoke-c8375a8 .`) |
| Profiles volume | `sms-live-smoke-c8375a8` (fresh isolated Docker volume) |
| X credentials | explicit blank (`TWITTER_AUTH_TOKEN` / `TWITTER_CT0` unset) |
| Harness | `supersocks-media-scraper-smoke` |
| Offline tests | `pytest -q` → 83 passed (2026-08-06, evidence commit worktree) |

Smoke URLs (explicit overrides for this run):

| Platform | URL used |
| --- | --- |
| x | `https://x.com/iamsupersocks/status/2082846361494417549` |
| reddit | `https://www.reddit.com/r/ModSupport/comments/1rshtk3/how_do_i_post_an_announcement_i_dont_see_anywhere/` |
| instagram | `https://www.instagram.com/instagram/p/DbbY9pdm6Q2/` |
| facebook | `https://www.facebook.com/facebook` |

**Default verify mode** (`--require-success` off, cold profiles, blank X tokens):

| Platform | Classification | Schema | Notes |
| --- | --- | --- | --- |
| x | `needs-human` / `login` | valid | no useful content extracted |
| reddit | `needs-human` / `challenge` | valid | no useful content extracted |
| instagram | `needs-human` / `consent` | valid | no useful content extracted |
| facebook | `needs-human` / `consent` | valid | no useful content extracted |

Run summary: exit `0`; `content-success` count **0** (all four returned honest
human gates, not scraped content).

Example Docker invocation (verify):

```bash
docker build -t supersocks-media-scraper:smoke-c8375a8 .
docker volume create sms-live-smoke-c8375a8
docker run --rm \
  -v sms-live-smoke-c8375a8:/home/scraper/media-browser-profiles \
  -e TWITTER_AUTH_TOKEN= -e TWITTER_CT0= \
  --entrypoint supersocks-media-scraper-smoke \
  supersocks-media-scraper:smoke-c8375a8 \
  --url-x 'https://x.com/iamsupersocks/status/2082846361494417549' \
  --url-instagram 'https://www.instagram.com/instagram/p/DbbY9pdm6Q2/'
echo $?   # 0 on 2026-08-06 Codex QA run
```

**Strict mode rerun** (`--require-success`, same URLs/volume/credentials):

| Platform | Classification | Schema | Notes |
| --- | --- | --- | --- |
| x | `needs-human` | valid | still gated |
| reddit | `runtime-error` | valid | empty Cloak render without a human gate |
| instagram | `needs-human` | valid | still gated |
| facebook | `needs-human` | valid | still gated |

Run summary: exit `1`. Reddit flipped from `needs-human/challenge` to
`runtime-error` on rerun — live backends vary; do not treat a single cold run
as universal.

**Warmed / authenticated rerun (live):** **not performed.** No headed warm-up,
no `TWITTER_AUTH_TOKEN`/`TWITTER_CT0`, and no `--require-success` pass with
`content-success` on any platform in this QA cycle.

**Deterministic fixture status (offline):** covered by existing pytest suites listed
above; run `pytest -q` after install. Treat offline green separately from live
network evidence.

## Safety

- Private-by-default. Do not commit `.env`, cookies, profiles, or tokens.
- Never automate login, MFA, CAPTCHA, consent bypass, or rate-limit evasion.
- noVNC warm-up binds loopback only; do not expose port 6080 publicly.
- This package scrapes visible public fields from operator-supplied URLs; it is
  not a bulk copyrighted-media downloader.
