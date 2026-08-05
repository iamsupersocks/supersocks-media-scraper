"""Shared Cloak HTML parsing and gate detection for social media pages.

Adapted from supersocks-url-scraper cloak_social (MIT). Visible/public
extraction only — never claims exhaustiveness.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from ..schema import GATE_LABELS, build_action_required, make_result
from ..sanitize import trim_text
from ._util import clean_text

CLOAK_PLATFORMS = frozenset({"reddit", "instagram", "facebook"})
MIN_USEFUL_CHARS = 40
MAX_COMMENTS = 20

_LOGIN_MARKERS = (
    "log in",
    "sign in",
    "sign up",
    "create an account",
    "connexion",
    "identifiez-vous",
    "you must log in",
    "login to continue",
    "log in to continue",
    "please log in",
    "authwall",
    "checkpoint",
)
_MFA_MARKERS = (
    "two-factor",
    "two factor",
    "2fa",
    "multi-factor",
    "mfa",
    "verification code",
    "authenticator app",
    "enter the code",
    "one-time code",
    "one time password",
)
_CAPTCHA_MARKERS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "js_challenge",
)
_CHALLENGE_MARKERS = (
    "are you a robot",
    "security check",
    "unusual traffic",
    "verify you are human",
    "prove your humanity",
    "press & hold",
    "js_challenge",
)
_CONSENT_MARKERS = (
    "cookie consent",
    "consentement",
    "before you continue",
    "accept all cookies",
    "accepter tous les cookies",
    "autoriser tous les cookies",
    "privacy preference center",
)
_STRONG_CONSENT_MARKERS = ("autoriser tous les cookies",)
_RATE_LIMIT_MARKERS = (
    "too many requests",
    "rate limit",
    "rate-limit",
    "you are being rate limited",
    "try again later",
    "429",
)

_REDDIT_SHREDDIT_TITLE = re.compile(
    r"<shreddit-title[^>]*title=[\"']([^\"']+)[\"']",
    re.I,
)
_REDDIT_POST_CONTENT = re.compile(
    r"<(?:div|p|h1)[^>]*(?:slot=[\"']text-body[\"']|id=[\"']post-title[\"']|data-testid=[\"']post-content[\"']|"
    r"class=[\"'][^\"']*(?:Post|post-content|RichTextJSON-root)[^\"']*[\"'])[^>]*>(.*?)</(?:div|p|h1)>",
    re.I | re.S,
)
_IG_ARTICLE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.I | re.S)
_FB_POST_TEXT = re.compile(
    r"<(?:div|span)[^>]*(?:data-ad-preview=[\"']message[\"']|data-testid=[\"']post_message[\"']|"
    r"class=[\"'][^\"']*(?:userContent|x1iorvi4)[^\"']*[\"'])[^>]*>(.*?)</(?:div|span)>",
    re.I | re.S,
)
_AUTHOR_SELECTORS = (
    re.compile(
        r"<meta[^>]+(?:name|property)=[\"'](?:author|article:author|og:article:author)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.I,
    ),
    re.compile(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:name|property)=[\"'](?:author|article:author|og:article:author)[\"']",
        re.I,
    ),
    re.compile(
        r"<a\b[^>]*(?:class=[\"'][^\"']*(?:author|Author|username)[^\"']*[\"']|rel=[\"']author[\"'])[^>]*>(.*?)</a>",
        re.I | re.S,
    ),
)
_TIME_SELECTORS = (
    re.compile(
        r"<meta[^>]+(?:name|property)=[\"'](?:article:published_time|og:updated_time|datePublished)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.I,
    ),
    re.compile(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:name|property)=[\"'](?:article:published_time|og:updated_time|datePublished)[\"']",
        re.I,
    ),
    re.compile(r"<time\b[^>]*(?:datetime|content)=[\"']([^\"']+)[\"']", re.I),
)
_OG_IMAGE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_OG_IMAGE_ALT = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image:alt[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_OG_VIDEO = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?:og:video|og:video:url|twitter:player:stream)[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_METRIC_PATTERNS = {
    "likes": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.]*)\s*(?:likes?|j'?aime|reactions?)[\"']",
        re.I,
    ),
    "comments": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.]*)\s*(?:comments?|commentaires?)[\"']",
        re.I,
    ),
    "shares": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.]*)\s*(?:shares?|partages?)[\"']",
        re.I,
    ),
    "views": re.compile(
        r"(?:aria-label|title)=[\"'][^\"']*?(\d[\d,\.]*)\s*(?:views?|vues?)[\"']",
        re.I,
    ),
}
_COMMENT_BLOCK = re.compile(
    r"<(?:div|li|article)[^>]*(?:data-testid=[\"']comment[\"']|class=[\"'][^\"']*Comment[^\"']*[\"'])[^>]*>"
    r"(.*?)</(?:div|li|article)>",
    re.I | re.S,
)


def _strip_embedded_markup(markup: str) -> str:
    text = markup or ""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    for tag in ("script", "style", "noscript", "template"):
        text = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", " ", text, flags=re.I | re.S)
    return text


def _meta_content(markup: str, *, name: str | None = None, prop: str | None = None) -> str:
    attr = "name" if name else "property"
    key = name or prop
    if not key:
        return ""
    escaped = re.escape(key)
    patterns = [
        rf"<meta[^>]+{attr}=[\"']{escaped}[\"'][^>]+content=[\"']([^\"']{{1,5000}})[\"']",
        rf"<meta[^>]+content=[\"']([^\"']{{1,5000}})[\"'][^>]+{attr}=[\"']{escaped}[\"']",
    ]
    for pattern in patterns:
        match = re.search(pattern, markup or "", re.I | re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def _json_ld_nodes(markup: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for match in re.finditer(
        r'<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',
        markup or "",
        re.I | re.S,
    ):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item and isinstance(item["@graph"], list):
                    stack.extend(item["@graph"])
                else:
                    nodes.append(item)
            elif isinstance(item, list):
                stack.extend(item)
    return nodes


def _visible_challenge_text(*parts: object) -> str:
    return " ".join(clean_text(part).lower() for part in parts if part)


def detect_gate(
    markup: str,
    *,
    platform: str,
    page_title: str | None = None,
    http_status: int | None = None,
) -> str | None:
    """Return needs-human reason: login|mfa|captcha|consent|challenge|rate-limit."""
    if http_status == 429:
        return "rate-limit"
    visible = _strip_embedded_markup(markup)
    blob = clean_text(visible).lower()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", visible, re.I | re.S)
    html_title = title_match.group(1) if title_match else None
    challenge_blob = _visible_challenge_text(blob, page_title, html_title)
    if not challenge_blob:
        return None
    if any(marker in challenge_blob for marker in _RATE_LIMIT_MARKERS):
        return "rate-limit"
    if any(marker in challenge_blob for marker in _MFA_MARKERS):
        return "mfa"
    if any(marker in challenge_blob for marker in _CAPTCHA_MARKERS):
        return "captcha"
    if any(marker in challenge_blob for marker in _CHALLENGE_MARKERS):
        return "challenge"
    login_hits = sum(1 for marker in _LOGIN_MARKERS if marker in blob)
    useful_meta = bool(
        _meta_content(markup, prop="og:description")
        or _meta_content(markup, name="description")
        or _meta_content(markup, prop="og:title")
    )
    if login_hits >= 2 and not useful_meta:
        return "login"
    if platform == "instagram" and "login • instagram" in blob and not useful_meta:
        return "login"
    if platform == "facebook" and ("log into facebook" in blob or "créer un compte" in blob) and not useful_meta:
        return "login"
    if (
        platform == "reddit"
        and ("log in" in blob and "sign up" in blob)
        and "shreddit-post" not in visible.lower()
        and not useful_meta
    ):
        return "login"
    if any(marker in blob for marker in _STRONG_CONSENT_MARKERS):
        return "consent"
    if any(marker in blob for marker in _CONSENT_MARKERS) and len(blob) < 600 and not useful_meta:
        return "consent"
    return None


def _parse_count(raw: str) -> int | None:
    text = (raw or "").strip().lower().replace(",", "").replace("\u00a0", "")
    if not text:
        return None
    mult = 1
    if text.endswith("k"):
        mult = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        mult = 1_000_000
        text = text[:-1]
    try:
        return int(float(text) * mult)
    except ValueError:
        return None


def _extract_metrics(markup: str) -> dict[str, int | None]:
    out: dict[str, int | None] = {"likes": None, "comments": None, "shares": None, "views": None}
    for key, pattern in _METRIC_PATTERNS.items():
        match = pattern.search(markup or "")
        if match:
            out[key] = _parse_count(match.group(1))
    return out


def _extract_media(markup: str) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    alt = None
    alt_match = _OG_IMAGE_ALT.search(markup or "")
    if alt_match:
        alt = clean_text(alt_match.group(1)) or None
    for match in _OG_IMAGE.finditer(markup or ""):
        url = clean_text(match.group(1))
        if url:
            media.append({"kind": "image", "url": url, "alt": alt})
            break
    for match in _OG_VIDEO.finditer(markup or ""):
        url = clean_text(match.group(1))
        if url:
            media.append({"kind": "video", "url": url, "alt": None})
            break
    # Thumbnail: reuse first image when a video is present.
    if any(item["kind"] == "video" for item in media) and any(item["kind"] == "image" for item in media):
        image = next(item for item in media if item["kind"] == "image")
        media.append({"kind": "thumbnail", "url": image["url"], "alt": image.get("alt")})
    return media


def _extract_comments(markup: str) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for match in _COMMENT_BLOCK.finditer(markup or ""):
        block = match.group(1)
        text = clean_text(block)
        if not text or len(text) < 2:
            continue
        author = None
        author_match = re.search(
            r"<(?:a|span)[^>]*(?:class=[\"'][^\"']*(?:author|Author|username)[^\"']*[\"'])[^>]*>(.*?)</(?:a|span)>",
            block,
            re.I | re.S,
        )
        if author_match:
            author = clean_text(author_match.group(1)) or None
        comments.append({"author": author, "text": trim_text(text, 500), "published_at": None})
        if len(comments) >= MAX_COMMENTS:
            break
    return comments


def _extract_author(markup: str, nodes: list[dict[str, Any]]) -> dict[str, str | None]:
    name = None
    for pattern in _AUTHOR_SELECTORS:
        match = pattern.search(markup or "")
        if match:
            value = clean_text(match.group(1))
            if value:
                name = value
                break
    if not name:
        for node in nodes:
            for key in ("author", "creator", "publisher"):
                value = node.get(key)
                if isinstance(value, dict):
                    candidate = clean_text(value.get("name") or value.get("@id") or "")
                    if candidate:
                        name = candidate
                        break
                elif isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, dict):
                        candidate = clean_text(first.get("name") or "")
                    else:
                        candidate = clean_text(first)
                    if candidate:
                        name = candidate
                        break
                else:
                    candidate = clean_text(value)
                    if candidate:
                        name = candidate
                        break
            if name:
                break
    handle = None
    if name and name.startswith("@"):
        handle = name.lstrip("@")
    return {"name": name, "handle": handle, "url": None}


def _extract_published_at(markup: str, nodes: list[dict[str, Any]]) -> str | None:
    for pattern in _TIME_SELECTORS:
        match = pattern.search(markup or "")
        if match:
            value = clean_text(match.group(1))
            if value:
                return value
    for node in nodes:
        for key in ("datePublished", "uploadDate", "dateCreated", "dateModified"):
            value = clean_text(node.get(key))
            if value:
                return value
    return None


def _platform_body(markup: str, *, platform: str) -> str:
    chunks: list[str] = []
    if platform == "reddit":
        title = _REDDIT_SHREDDIT_TITLE.search(markup or "")
        if title:
            chunks.append(clean_text(title.group(1)))
        for match in _REDDIT_POST_CONTENT.finditer(markup or ""):
            text = clean_text(match.group(1))
            if text and text not in chunks:
                chunks.append(text)
    elif platform == "instagram":
        for match in _IG_ARTICLE.finditer(markup or ""):
            text = clean_text(match.group(1))
            if text:
                chunks.append(text)
                break
    elif platform == "facebook":
        for match in _FB_POST_TEXT.finditer(markup or ""):
            text = clean_text(match.group(1))
            if text and text not in chunks:
                chunks.append(text)
    return "\n\n".join(chunks).strip()


def infer_content_kind(url: str, platform: str) -> str:
    path = (url or "").lower()
    if platform == "instagram":
        if "/reel/" in path or "/reels/" in path:
            return "reel"
        if "/stories/" in path:
            return "story"
        if "/p/" in path:
            return "post"
        parts = [p for p in path.split("/") if p and p not in {"https:", "http:"}]
        if len(parts) <= 2:
            return "profile"
    if platform == "reddit":
        if "/comments/" in path:
            return "post"
        if "/user/" in path or "/u/" in path:
            return "profile"
    if platform == "facebook":
        if "/videos/" in path or "/watch" in path:
            return "video"
        if "/posts/" in path or "/permalink" in path or "story_fbid" in path:
            return "post"
    return "post"


def parse_cloak_html(
    markup: str,
    *,
    platform: str,
    source_url: str,
    final_url: str | None = None,
    page_title: str | None = None,
    max_chars: int = 4000,
    fetch_method: str = "cloak",
    extra_warnings: list[str] | None = None,
    http_status: int | None = None,
    max_comments: int = MAX_COMMENTS,
) -> dict[str, Any]:
    """Parse rendered social HTML into the media-scraper JSON contract."""
    warnings = list(extra_warnings or [])
    gate = detect_gate(markup, platform=platform, page_title=page_title, http_status=http_status)
    nodes = _json_ld_nodes(markup)
    title = (
        _meta_content(markup, prop="og:title")
        or _meta_content(markup, name="twitter:title")
        or clean_text(page_title)
        or None
    )
    if not title and platform == "reddit":
        match = _REDDIT_SHREDDIT_TITLE.search(markup or "")
        if match:
            title = clean_text(match.group(1)) or None
    for node in nodes:
        if not title:
            candidate = clean_text(node.get("headline") or node.get("name") or node.get("title"))
            if candidate:
                title = candidate
                break

    description = (
        _meta_content(markup, prop="og:description")
        or _meta_content(markup, name="description")
        or _meta_content(markup, name="twitter:description")
    )
    body = _platform_body(markup, platform=platform)
    for node in nodes:
        for key in ("articleBody", "text", "description", "caption"):
            value = clean_text(node.get(key))
            if value and value not in body:
                body = f"{body}\n\n{value}".strip() if body else value
    text = trim_text(body or description or "", max(50, min(int(max_chars or 4000), 20_000)))
    author = _extract_author(markup, nodes)
    published_at = _extract_published_at(markup, nodes)
    metrics = _extract_metrics(markup)
    media = _extract_media(markup)
    comments = _extract_comments(markup)[: max(0, int(max_comments))]
    useful = len(text) >= MIN_USEFUL_CHARS or bool(title and media)
    content_kind = infer_content_kind(final_url or source_url, platform)

    action = None
    if gate:
        label = GATE_LABELS.get(gate, gate)
        warnings.append(
            f"{platform} blocked by {label}; warm an operator-owned Cloak profile once "
            f"(MEDIA_BROWSER_PROFILES_ROOT/{platform}). Never automate login/MFA/CAPTCHA."
        )
        status = "error" if gate in {"captcha", "consent", "challenge", "mfa", "rate-limit"} else (
            "partial" if useful else "error"
        )
        text = ""
        media = []
        comments = []
        action = build_action_required(platform=platform, reason=gate)
    elif useful:
        status = "ok"
    elif title or text:
        status = "partial"
        warnings.append(f"{platform} rendered but useful text looks thin")
    else:
        status = "error"
        warnings.append(f"{platform} Cloak render produced no readable title/text")

    return make_result(
        status=status,
        platform=platform,
        content_kind=content_kind,
        source_url=source_url,
        final_url=final_url or source_url,
        title=title,
        text=text,
        author=author,
        published_at=published_at,
        metrics=metrics,
        media=media,
        comments=comments,
        warnings=warnings,
        action_required=action,
        fetch_method=fetch_method,
    )
