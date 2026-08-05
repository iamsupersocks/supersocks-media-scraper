"""Isolated per-platform Cloak profile directories.

Contract:
1. Explicit ``browser_profile_dir`` / CLI ``--browser-profile-dir`` wins.
2. When ``MEDIA_BROWSER_PROFILES_ROOT`` is set and a Cloak platform is known,
   use ``{root}/{platform}`` (``reddit`` / ``instagram`` / ``facebook``).
3. Else legacy ``MEDIA_BROWSER_PROFILE_DIR`` / ``BROWSER_PROFILE_DIR``.

Never invents cookies/tokens. Callers must not echo resolved absolute paths in
JSON results; use :func:`profile_status` for non-sensitive health/warmup output.

Adapted from supersocks-url-scraper social profiles (MIT).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

CLOAK_PROFILE_PLATFORMS = ("reddit", "instagram", "facebook")
DEFAULT_WARMUP_URLS: dict[str, str] = {
    "reddit": "https://www.reddit.com/r/announcements/",
    "instagram": "https://www.instagram.com/instagram/",
    "facebook": "https://www.facebook.com/facebook",
}


def media_profiles_root(*, environ: Mapping[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    return str(env.get("MEDIA_BROWSER_PROFILES_ROOT") or "").strip()


def resolve_profile_dir(
    explicit: str = "",
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve optional persistent Cloak profile for media reads/warm-up."""
    if explicit and str(explicit).strip():
        return str(Path(str(explicit).strip()).expanduser())
    env = environ if environ is not None else os.environ
    platform_id = (platform or "").strip().lower()
    root = media_profiles_root(environ=env)
    if root and platform_id in CLOAK_PROFILE_PLATFORMS:
        return str(Path(root).expanduser() / platform_id)
    for key in ("MEDIA_BROWSER_PROFILE_DIR", "BROWSER_PROFILE_DIR"):
        value = str(env.get(key) or "").strip()
        if value:
            return str(Path(value).expanduser())
    return ""


def ensure_profile_dir(
    profile_dir: str,
    *,
    create: bool = False,
) -> tuple[str, bool]:
    """Optionally create a profile directory. Returns ``(path, created)``."""
    path = str(Path(profile_dir).expanduser()) if profile_dir else ""
    if not path:
        return "", False
    target = Path(path)
    created = False
    if create and not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        created = True
    return str(target), created


def profile_status(raw_path: str, *, kind: str = "dir") -> dict[str, bool]:
    """Non-sensitive path status for health/warmup JSON (no absolute path)."""
    configured = bool(str(raw_path or "").strip())
    if not configured:
        return {"configured": False, "exists": False, "writable": False}
    path = Path(raw_path).expanduser()
    check_path = path if kind == "dir" else path.parent
    return {
        "configured": True,
        "exists": path.exists(),
        "writable": check_path.exists() and os.access(check_path, os.W_OK),
    }


def default_warmup_url(platform: str) -> str:
    return DEFAULT_WARMUP_URLS.get(platform, "")
