"""Platform adapters for supersocks-media-scraper."""

from __future__ import annotations

from ._util import detect_platform
from .facebook import scrape_facebook
from .instagram import scrape_instagram
from .reddit import scrape_reddit
from .x import scrape_x

__all__ = [
    "detect_platform",
    "scrape_facebook",
    "scrape_instagram",
    "scrape_reddit",
    "scrape_x",
]
