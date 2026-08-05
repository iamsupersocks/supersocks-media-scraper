"""URL sanitization and secret redaction for public JSON output.

Adapted from patterns in supersocks-url-scraper (MIT). Never echo cookies,
tokens, profile paths, userinfo, query, or fragment in scraper results.
Cloak/Playwright failures are classified into concise actionable warnings —
never raw exception dumps, launch command lines, or local cache paths.
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
    re.compile(
        r"(?i)(CLOAKBROWSER_CACHE_DIR|CLOAKBROWSER_BINARY_PATH|CLOAKBROWSER_LICENSE_KEY|"
        r"CLOAKBROWSER_DOWNLOAD_URL|HOME|DISPLAY|WAYLAND_DISPLAY)\s*[:=]\s*['\"]?([^\s'\"]+)"
    ),
)

# Absolute / home-relative paths that must never appear in public warnings.
_PATH_LEAK_PATTERNS = (
    re.compile(r"(?i)/root/\.cloakbrowser[^\s\"'`]{0,200}"),
    re.compile(r"(?i)/home/[^\s\"'`]{0,200}"),
    re.compile(r"(?i)/Users/[^\s\"'`]{0,200}"),
    re.compile(r"(?i)~/?\.cloakbrowser[^\s\"'`]{0,200}"),
    re.compile(r"(?i)(?:^|[\s\"'=])(/[^\s\"'`]*(?:cloakbrowser|browser-profiles|media-browser-profiles|chromium-)[^\s\"'`]*)"),
    re.compile(r"(?i)[A-Za-z]:\\[^\s\"'`]{0,200}"),
)

# Chrome/Playwright launch command lines and dump markers.
_DUMP_PATTERNS = (
    re.compile(r"(?is)={5,}.*?logs.*?={5,}.*?(?=\Z|\n\n)"),
    re.compile(r"(?is)Call log:.*"),
    re.compile(r"(?is)Traceback \(most recent call last\):.*"),
    re.compile(r"(?i)(?:^|\s)((?:/usr/bin/)?(?:google-chrome|chromium(?:-browser)?|chrome)(?:-[^\s]*)?(?:\s+--[^\n]*)+)"),
    re.compile(r"(?i)--(?:user-data-dir|disable-field-trial-config|no-sandbox|remote-debugging-port)=?[^\s]*"),
)

_ALREADY_SAFE_PREFIXES = (
    "headed CloakBrowser on Linux requires",
    "Install the browser extra:",
    "cloakbrowser not installed",
    "cloak rendered an empty page",
    "browser concurrency limit reached",
    "browser launch failed:",
    "browser navigation timed out",
    "browser session closed",
    "cloak media render failed:",
    "media warm-up failed:",
    "no media profile configured",
    "configured media Cloak profile is absent",
    "media Cloak profile directory is absent",
)

_MISSING_LIBRARY_RE = re.compile(
    r"(?i)(error while loading shared libraries|libnss\d|libatk|libgbm|libxkb|"
    r"libasound|libcups|libdrm|libgtk|libxcomposite|libxdamage|libxrandr|"
    r"shared object|cannot open shared object)"
)
_BINARY_MISSING_RE = re.compile(
    r"(?i)(executable doesn'?t exist|ensure_binary|failed to download|"
    r"binary (?:is )?(?:missing|not found)|"
    r"Failed to launch(?: browser)?(?![^\n]{0,80}shared librar)|"
    r"chromium-[\d.]+/[^\s]+(?:chrome|chromium))"
)
_TIMEOUT_RE = re.compile(r"(?i)(timeout\s+\d+ms\s+exceeded|TimeoutError|navigation timeout)")
_SESSION_CLOSED_RE = re.compile(
    r"(?i)(target (page|context|browser)[, ].*closed|browser has been closed|"
    r"context\.close|TargetClosedError)"
)
_DISPLAY_RE = re.compile(r"(?i)(DISPLAY|WAYLAND_DISPLAY|no display|headed CloakBrowser)")
_LAUNCH_FAIL_RE = re.compile(
    r"(?i)(browserType\.launch|launchPersistentContext|launch_persistent_context|"
    r"Failed to launch)"
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


def _strip_path_and_dump_leaks(text: str) -> str:
    value = text or ""
    for pattern in _DUMP_PATTERNS:
        value = pattern.sub(" [omitted]", value)
    for pattern in _PATH_LEAK_PATTERNS:
        value = pattern.sub("[path-redacted]", value)
    # Collapse noisy whitespace after redaction.
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def scrub_public_warning(text: str) -> str:
    """Defense-in-depth scrub for any public warning/error string."""
    value = redact_secrets(text or "")
    value = _strip_path_and_dump_leaks(value)
    lower = value.lower()
    if "traceback (most recent call last)" in lower or "file \"" in lower:
        return "browser engine error (details omitted)"
    # Drop leftover multi-line exception dumps; keep a short single line.
    if "\n" in value and any(
        marker in lower for marker in ("call log:", "browserType.", "playwright", "chromium")
    ):
        first = value.splitlines()[0].strip()
        first = _strip_path_and_dump_leaks(redact_secrets(first))
        if len(first) > 220:
            first = first[:217].rstrip() + "…"
        return first or "browser engine error (details omitted)"
    if len(value) > 280:
        value = value[:277].rstrip() + "…"
    return value


def sanitize_browser_error(
    exc: BaseException | str,
    *,
    context: str = "render",
) -> str:
    """Classify Cloak/Playwright failures into concise public-safe messages.

    Never returns raw exception dumps, Chromium launch command lines, local
    paths (e.g. ``/root/.cloakbrowser``), cookies, tokens, or env values.
    Preserves already-safe ``BrowserFetchError`` operator messages.
    """
    raw = str(exc) if not isinstance(exc, str) else (exc or "")
    compact = " ".join(raw.split())
    prefix = "media warm-up failed" if context == "warmup" else "cloak media render failed"

    for safe in _ALREADY_SAFE_PREFIXES:
        if compact.startswith(safe) or safe in compact[:120]:
            # Known operator-facing messages: scrub only, do not reclassify.
            cleaned = scrub_public_warning(compact)
            if cleaned.startswith(("cloak media render failed", "media warm-up failed")):
                return cleaned
            if context == "warmup" and cleaned.startswith("headed CloakBrowser"):
                return f"{prefix}: {cleaned}"
            if any(
                cleaned.startswith(p)
                for p in (
                    "headed CloakBrowser",
                    "Install the browser",
                    "cloakbrowser not installed",
                    "cloak rendered",
                    "browser concurrency",
                    "browser launch failed",
                    "browser navigation",
                    "browser session",
                )
            ):
                return f"{prefix}: {cleaned}" if context in {"render", "warmup"} else cleaned
            return cleaned

    if _DISPLAY_RE.search(compact) and "requires" in compact.lower():
        return scrub_public_warning(compact.splitlines()[0][:240])

    if _MISSING_LIBRARY_RE.search(compact):
        return (
            f"{prefix}: browser launch failed: missing Chromium system libraries; "
            "install the official Docker image (or matching Linux packages), then retry"
        )
    if _TIMEOUT_RE.search(compact):
        return f"{prefix}: browser navigation timed out; retry later or increase --timeout"
    if _SESSION_CLOSED_RE.search(compact):
        return f"{prefix}: browser session closed before the page finished loading"
    if _BINARY_MISSING_RE.search(compact) or _LAUNCH_FAIL_RE.search(compact):
        return (
            f"{prefix}: browser launch failed: CloakBrowser/Chromium binary unavailable "
            "or could not start; ensure the [browser] or [all] extra is installed and "
            "binaries are cached, then retry"
        )

    # Default: never echo the raw Playwright/Cloak dump.
    return f"{prefix}: browser engine error (details omitted)"


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
        out["warnings"] = [scrub_public_warning(str(w)) for w in warnings]
    # Never leak profile path fields if a caller accidentally injected them.
    for banned in ("profile_dir", "profile_path", "cookies", "auth_token", "ct0", "cookie"):
        out.pop(banned, None)
    return out
