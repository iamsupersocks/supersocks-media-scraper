# Supersocks Media Scraper

[![Python >=3.10](https://img.shields.io/badge/python-%3E%3D3.10-blue)](pyproject.toml)
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-informational)](pyproject.toml)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Private-by-default scraper for **visible public fields** on X, Instagram, Facebook, and Reddit.

Not exhaustive. Not a download tool. Not a login/MFA/CAPTCHA bypass.

LinkedIn public pages and YouTube stay in [`supersocks-url-scraper`](https://github.com/iamsupersocks/supersocks-url-scraper).

Portions adapted from `supersocks-url-scraper` (MIT).

---

## Français

### Frontière produit

| Dans ce paquet | Reste dans supersocks-url-scraper |
| --- | --- |
| X / Twitter (twitter-cli) | LinkedIn public |
| Instagram (Cloak optionnel) | YouTube |
| Facebook (Cloak optionnel) | Lecteur HTTP générique / articles / PDF |
| Reddit (Cloak optionnel) | |

### Installation

Extras (dépendances optionnelles) :

| Extra | Contenu | Pour quoi |
| --- | --- | --- |
| *(aucun)* | Rien | API/CLI seule + adaptateur X (twitter-cli requis) |
| `[x]` | `twitter-cli` | Backend X/Twitter étendu (`twitter` ou module `twitter_cli.cli`) |
| `[browser]` | `cloakbrowser` | Instagram / Facebook / Reddit via CloakBrowser |
| `[all]` | `twitter-cli` + `cloakbrowser` | Tout le ci-dessus |

```bash
# Depuis GitHub (PEP 508), avec CloakBrowser pour Instagram / Facebook / Reddit
pipx install 'supersocks-media-scraper[browser] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# Depuis GitHub, avec le backend X twitter-cli
pipx install 'supersocks-media-scraper[x] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# Depuis GitHub, tout (X + CloakBrowser)
pipx install 'supersocks-media-scraper[all] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# Version minimale (API/CLI + adaptateur X, sans navigateur Cloak)
pipx install 'git+https://github.com/iamsupersocks/supersocks-media-scraper.git'

# Ou depuis un clone
pip install -e '.[test]'
# Backend X (twitter-cli) :
pip install -e '.[x]'
# CloakBrowser pour Reddit / Instagram / Facebook :
pip install -e '.[browser]'
# Tout :
pip install -e '.[all]'
```

> `clix` est un outil distinct, non requis et non utilisé comme backend public.
> Sous pipx avec l'extra `[x]`, twitter-cli est disponible même sans
> `--include-deps` grâce au fallback `python -m twitter_cli.cli`.

### Exemples

CLI :

```bash
supersocks-media-scraper 'https://x.com/example/status/123'
supersocks-media-scraper --max-chars 2000 'https://www.reddit.com/r/announcements/comments/…'
```

Bibliothèque :

```python
from supersocks_media_scraper import scrape

result = scrape("https://www.instagram.com/p/EXAMPLE/")
print(result["status"], result["platform"], result["text"][:200])
```

Warm-up headed (jamais d'automatisation login/MFA/CAPTCHA) :

```bash
export MEDIA_BROWSER_PROFILES_ROOT="$HOME/media-browser-profiles"
# Linux privé : attacher un DISPLAY / Xvfb existant (le paquet ne démarre pas Xvfb)
# export DISPLAY=:99
supersocks-media-scraper --warmup reddit --create-profile --warmup-seconds 120
```

X nécessite twitter-cli (exécutable `twitter` **ou** module importable) **et**
les deux variables opérateur :

```bash
export TWITTER_AUTH_TOKEN=…   # export manuel Cookie-Editor uniquement
export TWITTER_CT0=…
supersocks-media-scraper 'https://x.com/example/status/123'
```

Avec `pipx install '…[x]…'`, le binaire `twitter` peut ne pas être sur le PATH ;
l'adaptateur X bascule alors sur `python -m twitter_cli.cli` dans le même
environnement pipx.

### Contrat JSON (stable)

`status`, `platform`, `content_kind`, `source_url` / `final_url` assainies,
`title`, `text`, `author` structuré, `published_at`, `metrics`
(likes/comments/shares/views quand visibles), `media[]`
(image/video/thumbnail/alt), `comments[]` (uniquement visibles, bornés),
`warnings`, `action_required` (`code=needs-human`,
`reason=login|mfa|captcha|consent|challenge|rate-limit`).

Les URLs de sortie retirent userinfo / query / fragment. Cookies, tokens et
chemins de profil ne sortent jamais.

### Limites

- Extraction du visible / public uniquement — jamais « exhaustif ».
- Pas d'automatisation login, MFA, CAPTCHA, consentement ou contournement de rate-limit.
- CloakBrowser est optionnel ; sans profil réchauffé, Instagram/Facebook/Reddit
  renvoient souvent `action_required`.
- X : backend explicite twitter-cli ; jamais d'autolecture navigateur.
- Détection de 429 / « Too Many Requests » / `js_challenge` / « Prove your humanity ».

---

## English

### Product boundary

This package covers **X, Instagram, Facebook, Reddit**. LinkedIn public pages
and YouTube remain in `supersocks-url-scraper`.

### Install

Optional extras:

| Extra | Contents | Use for |
| --- | --- | --- |
| *(none)* | Nothing | Standalone API/CLI + X adapter (requires twitter-cli) |
| `[x]` | `twitter-cli` | Extended X/Twitter backend (`twitter` executable or `twitter_cli.cli` module) |
| `[browser]` | `cloakbrowser` | Instagram / Facebook / Reddit via CloakBrowser |
| `[all]` | `twitter-cli` + `cloakbrowser` | Everything above |

```bash
# From GitHub (PEP 508), with CloakBrowser for Instagram / Facebook / Reddit
pipx install 'supersocks-media-scraper[browser] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'
# From GitHub, with the X backend twitter-cli
pipx install 'supersocks-media-scraper[x] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'
# From GitHub, everything (X + CloakBrowser)
pipx install 'supersocks-media-scraper[all] @ git+https://github.com/iamsupersocks/supersocks-media-scraper.git'
# or from a clone
pip install -e '.[test]'
pip install -e '.[x]'
pip install -e '.[browser]'
pip install -e '.[all]'
```

> `clix` is a separate tool, not required and not used as a public backend.
> With pipx and the `[x]` extra, twitter-cli remains reachable without
> `--include-deps` via the `python -m twitter_cli.cli` module fallback.

### CLI / library / warm-up

```bash
supersocks-media-scraper 'https://x.com/example/status/123'

export MEDIA_BROWSER_PROFILES_ROOT="$HOME/media-browser-profiles"
# Linux private host: attach existing DISPLAY/Xvfb yourself
supersocks-media-scraper --warmup instagram --create-profile
```

```python
from supersocks_media_scraper import scrape
print(scrape("https://www.reddit.com/r/announcements/")["status"])
```

### Security & limits

- Output URLs are sanitized (no userinfo/query/fragment).
- Never prints cookies, tokens, or profile paths.
- Never automates login/MFA/CAPTCHA/consent/rate-limit evasion.
- Detects 429, Too Many Requests, `js_challenge`, Prove your humanity.
- Visible fields only — never claim completeness.
- X requires operator-supplied `TWITTER_AUTH_TOKEN` + `TWITTER_CT0` only.
  Under pipx `[x]`, the adapter falls back to `python -m twitter_cli.cli` when
  the `twitter` executable is not on PATH.

### License

MIT — see [LICENSE](LICENSE).
