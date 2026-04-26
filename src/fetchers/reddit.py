"""Reddit fetcher via public .json endpoint."""

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from aiolimiter import AsyncLimiter
from loguru import logger

from .base import BasePlatformFetcher, Comment, Thread

REDDIT_BASE = 'https://www.reddit.com'
DELETED_BODIES = ('[deleted]', '[removed]')
COMMENT_QUERY = '.json?limit=500&depth=10&sort=confidence'
RETRY_STATUSES = (403, 429, 503)
RETRY_BACKOFF_SECONDS = (0.5, 1.0)

CANONICAL_RE = re.compile(
    r'reddit\.com/r/(?P<sub>[^/]+)/comments/(?P<post>[a-z0-9]+)',
    re.IGNORECASE,
)


class RedditFetchError(Exception):
    """Raised when Reddit returns non-2xx or malformed body."""


class RedditFetcher(BasePlatformFetcher):
    """Fetches Reddit threads through .json endpoint."""

    platform = 'reddit'

    def __init__(
        self,
        user_agent: str,
        rate_limit_qpm: int = 5,
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> None:
        """Init httpx client + per-minute rate limiter."""
        client_kwargs: dict[str, Any] = {
            'headers': {'User-Agent': user_agent},
            'follow_redirects': True,
            'timeout': timeout,
        }
        if proxy:
            client_kwargs['proxy'] = proxy
        self._client = httpx.AsyncClient(**client_kwargs)
        self._limiter = AsyncLimiter(rate_limit_qpm, 60)

    async def fetch_thread(self, url: str) -> Thread:
        """Resolve URL, fetch JSON, build Thread."""
        canonical = await self._resolve_url(url)
        match = CANONICAL_RE.search(canonical)
        if match is None:
            raise RedditFetchError(f'Cannot parse Reddit URL: {url}')

        api_url = (
            f'{REDDIT_BASE}/r/{match["sub"]}/comments/'
            f'{match["post"]}/{COMMENT_QUERY}'
        )
        payload = await self._get_json(api_url)
        return self._build_thread(payload, canonical)

    async def close(self) -> None:
        """Close httpx client."""
        await self._client.aclose()

    async def _resolve_url(self, url: str) -> str:
        """Follow redirects to get canonical URL (handles /s/ short-links)."""
        if '/s/' not in url:
            return url
        response = await self._get_with_retry(url)
        if response.status_code >= 400:
            logger.warning(
                'Short-link resolution failed: {} for {}',
                response.status_code,
                url,
            )
            raise RedditFetchError(
                f'Short-link resolution failed: {response.status_code}'
            )
        return str(response.url)

    async def _get_json(self, url: str) -> Any:
        """GET with rate limiting and HTTP error mapping."""
        response = await self._get_with_retry(url)
        if response.status_code != 200:
            logger.warning(
                'Reddit returned {} for {}', response.status_code, url
            )
            raise RedditFetchError(f'Reddit returned {response.status_code}')
        return response.json()

    async def _get_with_retry(self, url: str) -> httpx.Response:
        """GET with retry on transient statuses (residential IP rotation)."""
        attempts = len(RETRY_BACKOFF_SECONDS) + 1
        response: httpx.Response | None = None
        for attempt in range(attempts):
            async with self._limiter:
                response = await self._client.get(url)
            if response.status_code not in RETRY_STATUSES:
                return response
            if attempt < attempts - 1:
                backoff = RETRY_BACKOFF_SECONDS[attempt]
                logger.info(
                    'Retry {}/{} after {}s: status {} for {}',
                    attempt + 1,
                    attempts - 1,
                    backoff,
                    response.status_code,
                    url,
                )
                await asyncio.sleep(backoff)
        if response is None:
            raise RedditFetchError(f'No response after retries for {url}')
        return response

    def _build_thread(self, payload: Any, source_url: str) -> Thread:
        """Build Thread model from Reddit JSON payload."""
        if not isinstance(payload, list) or len(payload) < 2:
            raise RedditFetchError('Unexpected Reddit response shape')

        post_children = payload[0].get('data', {}).get('children', [])
        if not post_children:
            raise RedditFetchError('Empty post listing (deleted or locked?)')

        post_data = post_children[0]['data']
        comment_listing = payload[1].get('data', {}).get('children', [])

        return Thread(
            id=post_data['id'],
            platform=self.platform,
            title=post_data.get('title', ''),
            body=post_data.get('selftext', '') or '',
            author=post_data.get('author'),
            score=post_data.get('score', 0),
            num_comments=post_data.get('num_comments', 0),
            created_utc=_to_dt(post_data.get('created_utc')),
            url=source_url,
            comments=self._parse_comments(comment_listing, depth=0),
        )

    def _parse_comments(
        self, items: list[dict[str, Any]], depth: int
    ) -> list[Comment]:
        """Recursively flatten t1 comments, skip MoreComments and deleted."""
        result: list[Comment] = []
        for item in items:
            if item.get('kind') != 't1':
                continue
            data = item.get('data', {})
            body = data.get('body', '')
            if body in DELETED_BODIES:
                continue

            replies_field = data.get('replies')
            child_items: list[dict[str, Any]] = []
            if isinstance(replies_field, dict):
                child_items = replies_field.get('data', {}).get('children', [])

            result.append(
                Comment(
                    id=data['id'],
                    author=data.get('author'),
                    body=body,
                    score=data.get('score', 0),
                    created_utc=_to_dt(data.get('created_utc')),
                    depth=depth,
                    replies=self._parse_comments(child_items, depth + 1),
                )
            )
        return result


def _to_dt(ts: float | None) -> datetime | None:
    """Reddit unix timestamp to UTC datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)
