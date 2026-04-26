"""URL to fetcher dispatcher."""

import re
from re import Pattern

from ..config import get_config
from .base import BasePlatformFetcher
from .reddit import RedditFetcher
from .x import XFetcher

REDDIT_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r'^https?://(?:www\.|old\.)?reddit\.com/r/[^/]+/comments/[a-z0-9]+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^https?://(?:www\.)?reddit\.com/r/[^/]+/s/[A-Za-z0-9]+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^https?://redd\.it/[a-z0-9]+',
        re.IGNORECASE,
    ),
)

X_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r'^https?://(?:www\.)?x\.com/[^/]+/status/\d+',
        re.IGNORECASE,
    ),
    re.compile(
        r'^https?://(?:www\.|mobile\.)?twitter\.com/[^/]+/status/\d+',
        re.IGNORECASE,
    ),
)


def detect_fetcher(url: str) -> type[BasePlatformFetcher] | None:
    """Map URL to fetcher."""
    if any(pattern.match(url) for pattern in REDDIT_PATTERNS):
        return RedditFetcher
    if any(pattern.match(url) for pattern in X_PATTERNS):
        if get_config().X_API_KEY is None:
            return None
        return XFetcher
    return None
