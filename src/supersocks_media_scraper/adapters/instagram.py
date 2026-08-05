"""Instagram adapter (CloakBrowser optional)."""

from __future__ import annotations

from typing import Any

from .cloak import extract_cloak


def scrape_instagram(url: str, **kwargs: Any) -> dict[str, Any] | None:
    return extract_cloak(url, platform="instagram", **kwargs)
