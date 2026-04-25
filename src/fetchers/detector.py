"""URL to fetcher dispatcher."""

import re
from re import Pattern

from .base import BasePlatformFetcher
from .reddit import RedditFetcher

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

# TODO: add X/Twitter patterns when XFetcher implemented
# TODO: add Threads patterns when ThreadsFetcher implemented


def detect_fetcher(url: str) -> type[BasePlatformFetcher] | None:
    """Map URL to fetcher class, None if unsupported."""
    if any(pattern.match(url) for pattern in REDDIT_PATTERNS):
        return RedditFetcher
    return None
