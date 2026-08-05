"""URL sanitization and secret redaction for public JSON output.

Adapted from patterns in supersocks-url-scraper (MIT). Never echo cookies,
tokens, profile paths, userinfo, query, or fragment in scraper results.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

_SECRET_PATTERNS = (
    re.compile(r"(?i)(auth[_-]?token|ct0|cookie|authorization|bearer)\s*[:=]\s*['\"]?([^\s'\"]+)"),
    re.compile(r"(?i)(TWITTER_AUTH_TOKEN|TWITTER_CT0)\s*[:=]\s*['\"]?([^\s'\"]+)"),
    re.compile(r"(?i)(auth_token|ct0)=([^\s;]+)"),
    re.compile(r"(?i)(access_token|refresh_token|sessionid|csrftoken)\s*[:=]\s*['\"]?([^\s'\"]+)"),
    re.compile(r"(?i)(js_challenge|cf_chl|g-recaptcha)[^\s]*[=:]\s*['\"]?([^\s'\"]+)"),
    re.compile(r"(?i)([?&](?:token|code|auth|session|key|sig))=([^\s&\"']+)"),
    re.compile(r"(?i)(/home/[^\s\"']+/browser-profiles[^\s\"']*)"),
    re.compile(r"(?i)(/Users/[^\s\"']+/browser-profiles[^\s\"']*)"),
    re.compile(r"(?i)(MEDIA_BROWSER_PROFILES_ROOT|BROWSER_PROFILE_DIR)\s*[:=]\s*['\"]?([^\s'\"]+)"),
)


def sanitize_url(url: str | None) -> str:
    """Return scheme + host + path only (no userinfo, query, or fragment)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        host = parsed.hostname
        port = parsed.port
        default_port = (parsed.scheme == "http" and port == 80) or (
            parsed.scheme == "https" and port == 443
        )
        netloc = host if not port or default_port else f"{host}:{port}"
        path = parsed.path or ""
        return urlunparse((parsed.scheme.lower(), netloc, path, "", "", ""))
    without_fragment = raw.split("#", 1)[0]
    without_query = without_fragment.split("?", 1)[0]
    if "@" in without_query:
        scheme_sep = without_query.find("://")
        if scheme_sep >= 0:
            without_query = without_query[: scheme_sep + 3] + without_query.split("@", 1)[-1]
    return without_query


def redact_secrets(text: str) -> str:
    """Redact credential-looking substrings from warnings and errors."""
    value = text or ""
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    return value


def trim_text(text: str, max_chars: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars + 1]
    space = cut.rfind(" ", 0, max_chars)
    return ((cut[:space] if space >= int(max_chars * 0.5) else cut[: max_chars - 1]) + "…").strip()


def scrub_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure outbound JSON never carries unsafe URL parts or absolute profile paths."""
    out = dict(payload)
    for key in ("source_url", "final_url"):
        if key in out and out[key] is not None:
            out[key] = sanitize_url(str(out[key]))
    author = out.get("author")
    if isinstance(author, dict) and author.get("url"):
        author = dict(author)
        author["url"] = sanitize_url(str(author["url"]))
        out["author"] = author
    media = out.get("media")
    if isinstance(media, list):
        cleaned_media = []
        for item in media:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            if entry.get("url"):
                entry["url"] = sanitize_url(str(entry["url"]))
            cleaned_media.append(entry)
        out["media"] = cleaned_media
    warnings = out.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [redact_secrets(str(w)) for w in warnings]
    # Never leak profile path fields if a caller accidentally injected them.
    for banned in ("profile_dir", "profile_path", "cookies", "auth_token", "ct0", "cookie"):
        out.pop(banned, None)
    return out
