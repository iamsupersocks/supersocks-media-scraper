"""Stable public JSON contract for supersocks-media-scraper v0.1.

This is a visible/public extraction contract, not an exhaustive archive.
Never claim completeness. Fields absent on the page stay null/empty.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .sanitize import scrub_result

STATUSES = frozenset({"ok", "partial", "error"})
PLATFORMS = frozenset({"x", "instagram", "facebook", "reddit"})
CONTENT_KINDS = frozenset(
    {"post", "profile", "video", "reel", "story", "comment_thread", "unknown"}
)
GATE_REASONS = frozenset({"login", "mfa", "captcha", "consent", "challenge", "rate-limit"})
NEEDS_HUMAN_CODE = "needs-human"
GATE_LABELS = {
    "login": "login/auth wall",
    "mfa": "MFA/verification",
    "captcha": "CAPTCHA",
    "consent": "consent wall",
    "challenge": "challenge",
    "rate-limit": "rate limit",
}
DEFAULT_MAX_COMMENTS = 20


def empty_metrics() -> dict[str, int | None]:
    return {"likes": None, "comments": None, "shares": None, "views": None}


def empty_author() -> dict[str, str | None]:
    return {"name": None, "handle": None, "url": None}


def build_action_required(
    *,
    platform: str,
    reason: str,
    resume_instructions: str | None = None,
) -> dict[str, str] | None:
    if reason not in GATE_REASONS:
        return None
    label = GATE_LABELS.get(reason, reason)
    if resume_instructions is None:
        resume_instructions = (
            f"{platform} requires a human for {label}. "
            f"Run headed warm-up for the {platform} profile "
            f"(supersocks-media-scraper --warmup {platform} --create-profile), "
            "complete login/consent/challenge manually in the browser window, then retry. "
            "Never automate login, MFA, CAPTCHA, consent bypass, or rate-limit evasion."
        )
    return {
        "code": NEEDS_HUMAN_CODE,
        "reason": reason,
        "platform": platform,
        "resume_instructions": resume_instructions,
    }


def make_result(
    *,
    status: str,
    platform: str | None,
    content_kind: str = "unknown",
    source_url: str = "",
    final_url: str = "",
    title: str | None = None,
    text: str = "",
    author: Mapping[str, Any] | None = None,
    published_at: str | None = None,
    metrics: Mapping[str, Any] | None = None,
    media: Sequence[Mapping[str, Any]] | None = None,
    comments: Sequence[Mapping[str, Any]] | None = None,
    warnings: Sequence[str] | None = None,
    action_required: Mapping[str, Any] | None = None,
    fetch_method: str | None = None,
) -> dict[str, Any]:
    """Build the stable outbound contract, then scrub unsafe fields."""
    auth = dict(empty_author())
    if isinstance(author, Mapping):
        for key in ("name", "handle", "url"):
            value = author.get(key)
            auth[key] = str(value).strip() if value not in (None, "") else None

    mets = empty_metrics()
    if isinstance(metrics, Mapping):
        for key in ("likes", "comments", "shares", "views"):
            value = metrics.get(key)
            if value is None or value == "":
                mets[key] = None
            else:
                try:
                    mets[key] = int(value)
                except (TypeError, ValueError):
                    mets[key] = None

    media_out: list[dict[str, Any]] = []
    for item in media or ():
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind") or "image").strip().lower()
        if kind not in {"image", "video", "thumbnail"}:
            kind = "image"
        entry = {
            "kind": kind,
            "url": str(item.get("url") or "").strip() or None,
            "alt": str(item.get("alt") or "").strip() or None,
        }
        if entry["url"]:
            media_out.append(entry)

    comments_out: list[dict[str, Any]] = []
    for item in (comments or ())[:DEFAULT_MAX_COMMENTS]:
        if not isinstance(item, Mapping):
            continue
        comments_out.append(
            {
                "author": str(item.get("author") or "").strip() or None,
                "text": str(item.get("text") or "").strip() or None,
                "published_at": str(item.get("published_at") or "").strip() or None,
            }
        )

    kind = content_kind if content_kind in CONTENT_KINDS else "unknown"
    status_value = status if status in STATUSES else "error"
    platform_value = platform if platform in PLATFORMS else platform

    result: dict[str, Any] = {
        "status": status_value,
        "platform": platform_value,
        "content_kind": kind,
        "source_url": source_url or "",
        "final_url": final_url or source_url or "",
        "title": title,
        "text": text or "",
        "author": auth,
        "published_at": published_at,
        "metrics": mets,
        "media": media_out,
        "comments": comments_out,
        "warnings": [str(w) for w in (warnings or ())],
        "action_required": dict(action_required) if action_required else None,
    }
    if fetch_method:
        result["fetch_method"] = fetch_method
    return scrub_result(result)


def error_result(
    *,
    platform: str | None,
    source_url: str,
    warnings: Sequence[str],
    content_kind: str = "unknown",
    action_required: Mapping[str, Any] | None = None,
    fetch_method: str | None = None,
) -> dict[str, Any]:
    return make_result(
        status="error",
        platform=platform,
        content_kind=content_kind,
        source_url=source_url,
        final_url=source_url,
        warnings=warnings,
        action_required=action_required,
        fetch_method=fetch_method,
    )
