"""X fetcher via twitterapi.io."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from .base import BasePlatformFetcher, Comment, Thread
from .x_models import XThreadResponse, XTweet

THREAD_CONTEXT_PATH = '/twitter/tweet/thread_context'
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_BACKOFF_SECONDS = (0.5, 1.0)

STATUS_RE = re.compile(r'/status/(?P<id>\d+)', re.IGNORECASE)

ProgressCb = Callable[[int], Awaitable[None]]


class XFetchError(Exception):
    """X fetch failure."""


class XFetcher(BasePlatformFetcher):
    """X thread fetcher."""

    platform = 'x'

    def __init__(
        self,
        api_key: str,
        base_url: str = 'https://api.twitterapi.io',
        timeout: float = 60.0,
        max_pages: int = 5,
    ) -> None:
        """Init httpx client."""
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={'X-API-Key': api_key},
            timeout=timeout,
        )
        self._max_pages = max_pages

    async def fetch_thread(
        self,
        url: str,
        progress_cb: ProgressCb | None = None,
    ) -> Thread:
        """Fetch thread by URL."""
        tweet_id = self._extract_id(url)
        all_tweets = await self._fetch_pages(tweet_id, progress_cb)
        if not all_tweets:
            raise XFetchError(f'Empty thread for tweet {tweet_id}')
        return self._build_thread(all_tweets, url)

    async def close(self) -> None:
        """Close httpx client."""
        await self._client.aclose()

    @staticmethod
    def _extract_id(url: str) -> str:
        """Extract tweet id."""
        match = STATUS_RE.search(url)
        if match is None:
            raise XFetchError(f'Cannot parse X URL: {url}')
        return match.group('id')

    async def _fetch_pages(
        self,
        tweet_id: str,
        progress_cb: ProgressCb | None,
    ) -> list[XTweet]:
        """Paginate thread context."""
        collected: list[XTweet] = []
        seen_ids: set[str] = set()
        seen_cursors: set[str] = set()
        cursor = ''

        for page in range(1, self._max_pages + 1):
            payload = await self._get_thread_context(tweet_id, cursor)
            resp = XThreadResponse.model_validate(payload)
            if resp.status != 'success':
                raise XFetchError(
                    f'twitterapi.io status={resp.status} msg={resp.msg}'
                )

            new_tweets = [t for t in resp.tweets if t.id not in seen_ids]
            if not new_tweets:
                # Stop on empty page. has_next_page is unreliable.
                break

            for t in new_tweets:
                seen_ids.add(t.id)
            collected.extend(new_tweets)

            if progress_cb is not None:
                await progress_cb(page)

            if not resp.has_next_page or not resp.next_cursor:
                break
            if resp.next_cursor in seen_cursors:
                logger.info(
                    'Cursor repeated at page {}, stopping pagination', page
                )
                break
            seen_cursors.add(resp.next_cursor)
            cursor = resp.next_cursor

        return collected

    async def _get_thread_context(self, tweet_id: str, cursor: str) -> Any:
        """GET with retry."""
        params: dict[str, str] = {'tweetId': tweet_id}
        if cursor:
            params['cursor'] = cursor

        attempts = len(RETRY_BACKOFF_SECONDS) + 1
        response: httpx.Response | None = None
        for attempt in range(attempts):
            response = await self._client.get(
                THREAD_CONTEXT_PATH, params=params
            )
            if response.status_code not in RETRY_STATUSES:
                break
            if attempt < attempts - 1:
                backoff = RETRY_BACKOFF_SECONDS[attempt]
                logger.info(
                    'X retry {}/{} after {}s: status {} for tweet {}',
                    attempt + 1,
                    attempts - 1,
                    backoff,
                    response.status_code,
                    tweet_id,
                )
                await asyncio.sleep(backoff)

        if response is None:
            raise XFetchError(f'No response after retries for {tweet_id}')
        if response.status_code != 200:
            raise XFetchError(
                f'twitterapi.io returned {response.status_code} '
                f'for tweet {tweet_id}'
            )
        return response.json()

    def _build_thread(
        self, all_tweets: list[XTweet], source_url: str
    ) -> Thread:
        """Build Thread from tweets."""
        op = next(
            (t for t in all_tweets if t.id == t.conversation_id),
            None,
        )
        if op is None:
            non_replies = [t for t in all_tweets if not t.is_reply]
            if not non_replies:
                raise XFetchError('Cannot find OP tweet in response')
            op = non_replies[0]

        replies = [t for t in all_tweets if t.id != op.id]
        replies.sort(key=lambda t: t.created_at)

        return Thread(
            id=op.id,
            platform=self.platform,
            title=op.text[:100] if op.text else '',
            body=op.text,
            author=op.author.user_name,
            score=op.like_count,
            num_comments=op.reply_count,
            created_utc=_parse_dt(op.created_at),
            url=source_url,
            comments=[_to_comment(t) for t in replies],
        )


def _to_comment(tweet: XTweet) -> Comment:
    """Map XTweet to Comment."""
    return Comment(
        id=tweet.id,
        author=tweet.author.user_name,
        body=tweet.text,
        score=tweet.like_count,
        created_utc=_parse_dt(tweet.created_at),
        depth=0,
        replies=[],
    )


def _parse_dt(ts: str) -> datetime | None:
    """Parse createdAt to datetime."""
    if not ts:
        return None
    for fmt in (
        '%a %b %d %H:%M:%S %z %Y',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%SZ',
    ):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None
