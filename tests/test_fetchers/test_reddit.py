"""RedditFetcher tests with httpx.MockTransport."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from aiolimiter import AsyncLimiter

from src.fetchers.base import Comment
from src.fetchers.reddit import RedditFetcher, RedditFetchError

FIXTURE_DIR = Path(__file__).parent.parent / 'fixtures'
USER_AGENT = 'thread-digest:test (by /u/hawkxdev)'


def _load(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def _flatten(comments: list[Comment]) -> list[Comment]:
    """Recursively flatten nested comment list."""
    out: list[Comment] = []
    for c in comments:
        out.append(c)
        out.extend(_flatten(c.replies))
    return out


def _make_fetcher(handler: httpx.MockTransport) -> RedditFetcher:
    """Build fetcher with injected transport (bypasses real network)."""
    fetcher = RedditFetcher(user_agent=USER_AGENT, rate_limit_qpm=600)
    fetcher._client = httpx.AsyncClient(  # noqa: SLF001
        headers={'User-Agent': USER_AGENT},
        follow_redirects=True,
        transport=handler,
    )
    return fetcher


@pytest.fixture
async def small_fetcher() -> AsyncIterator[RedditFetcher]:
    payload = _load('reddit_small.json')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    fetcher = _make_fetcher(httpx.MockTransport(handler))
    yield fetcher
    await fetcher.close()


@pytest.fixture
async def big_fetcher() -> AsyncIterator[RedditFetcher]:
    payload = _load('reddit_big.json')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    fetcher = _make_fetcher(httpx.MockTransport(handler))
    yield fetcher
    await fetcher.close()


class TestParseSmallThread:
    """Small fixture: real-world Reddit thread, all comments accessible."""

    async def test_post_metadata(self, small_fetcher: RedditFetcher) -> None:
        thread = await small_fetcher.fetch_thread(
            'https://www.reddit.com/r/ClaudeCode/comments/1soqwfl/'
        )
        assert thread.platform == 'reddit'
        assert thread.id == '1soqwfl'
        assert thread.title.startswith('Claude Code effort levels')
        assert thread.author is not None
        assert thread.score > 0
        assert thread.created_utc is not None

    async def test_top_level_count(self, small_fetcher: RedditFetcher) -> None:
        thread = await small_fetcher.fetch_thread(
            'https://www.reddit.com/r/ClaudeCode/comments/1soqwfl/'
        )
        # Empirical fixture: 18 top-level t1 entries
        assert len(thread.comments) == 18

    async def test_total_recursive_count(
        self, small_fetcher: RedditFetcher
    ) -> None:
        thread = await small_fetcher.fetch_thread(
            'https://www.reddit.com/r/ClaudeCode/comments/1soqwfl/'
        )
        flat = _flatten(thread.comments)
        # Empirical: 40 t1 across tree after deleted/removed filter
        assert len(flat) == 40

    async def test_depth_assigned(self, small_fetcher: RedditFetcher) -> None:
        thread = await small_fetcher.fetch_thread(
            'https://www.reddit.com/r/ClaudeCode/comments/1soqwfl/'
        )
        for top in thread.comments:
            assert top.depth == 0
            for reply in top.replies:
                assert reply.depth == 1


class TestParseBigThread:
    """Big fixture: 6394 comments, only 499 returned in single .json call."""

    async def test_returns_partial_tree(
        self, big_fetcher: RedditFetcher
    ) -> None:
        thread = await big_fetcher.fetch_thread(
            'https://www.reddit.com/r/AskReddit/comments/1skb3e3/'
        )
        flat = _flatten(thread.comments)
        # Empirical: 488 t1 from 6394+ thread after deleted/removed filter
        assert len(flat) == 488
        assert thread.num_comments > 6000


class TestFilterDeletedRemoved:
    """Comments with body [deleted]/[removed] are skipped."""

    @pytest.mark.parametrize('marker', ['[deleted]', '[removed]'])
    async def test_skip_deleted_marker(self, marker: str) -> None:
        synthetic = json.dumps(
            [
                {
                    'data': {
                        'children': [
                            {
                                'kind': 't3',
                                'data': {
                                    'id': 'p1',
                                    'title': 'T',
                                    'selftext': '',
                                    'author': 'a',
                                    'score': 1,
                                    'num_comments': 2,
                                    'created_utc': 1700000000.0,
                                },
                            }
                        ]
                    }
                },
                {
                    'data': {
                        'children': [
                            {
                                'kind': 't1',
                                'data': {
                                    'id': 'c1',
                                    'body': 'real comment',
                                    'author': 'u1',
                                    'score': 5,
                                    'created_utc': 1700000001.0,
                                    'replies': '',
                                },
                            },
                            {
                                'kind': 't1',
                                'data': {
                                    'id': 'c2',
                                    'body': marker,
                                    'author': 'u2',
                                    'score': 0,
                                    'created_utc': 1700000002.0,
                                    'replies': '',
                                },
                            },
                        ]
                    }
                },
            ]
        ).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=synthetic)

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        try:
            thread = await fetcher.fetch_thread(
                'https://www.reddit.com/r/x/comments/p1/'
            )
        finally:
            await fetcher.close()

        ids = [c.id for c in thread.comments]
        assert ids == ['c1']


class TestErrorHandling:
    """Non-2xx and malformed payloads raise RedditFetchError."""

    async def test_raises_on_404(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text='not found')

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        try:
            with pytest.raises(RedditFetchError, match='404'):
                await fetcher.fetch_thread(
                    'https://www.reddit.com/r/x/comments/abc/'
                )
        finally:
            await fetcher.close()

    async def test_raises_on_short_link_404(self) -> None:
        """Broken /s/ short-link must surface as RedditFetchError, not httpx."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text='not found')

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        try:
            with pytest.raises(RedditFetchError, match='Short-link'):
                await fetcher.fetch_thread(
                    'https://www.reddit.com/r/x/s/abc123'
                )
        finally:
            await fetcher.close()

    async def test_raises_on_empty_post_listing(self) -> None:
        """Deleted/locked thread returns 200 with empty children -> error."""
        empty_payload = json.dumps(
            [
                {'data': {'children': []}},
                {'data': {'children': []}},
            ]
        ).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=empty_payload)

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        try:
            with pytest.raises(RedditFetchError, match='Empty post listing'):
                await fetcher.fetch_thread(
                    'https://www.reddit.com/r/x/comments/abc/'
                )
        finally:
            await fetcher.close()

    async def test_raises_on_unparseable_url(self) -> None:
        fetcher = _make_fetcher(
            httpx.MockTransport(lambda r: httpx.Response(200))
        )
        try:
            with pytest.raises(RedditFetchError, match='Cannot parse'):
                await fetcher.fetch_thread('https://example.com/nothing')
        finally:
            await fetcher.close()


class TestRateLimiter:
    """aiolimiter throttles concurrent requests within configured QPM."""

    async def test_throttles_burst(self) -> None:
        # Test feasibility: real 5/min limiter would need a 60s test.
        # Use 2 req/s + 6 parallel requests instead — same semantics,
        # fast enough for CI. Production rate is integration-verified
        # in Stage 7, not here.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {
                        'data': {
                            'children': [
                                {
                                    'kind': 't3',
                                    'data': {
                                        'id': 'p1',
                                        'title': 't',
                                        'selftext': '',
                                        'num_comments': 0,
                                    },
                                }
                            ]
                        }
                    },
                    {'data': {'children': []}},
                ],
            )

        fetcher = RedditFetcher(user_agent=USER_AGENT, rate_limit_qpm=600)
        # Override with fast limiter for test feasibility: 2 requests / 1 second.
        fetcher._limiter = AsyncLimiter(2, 1)  # noqa: SLF001
        fetcher._client = httpx.AsyncClient(  # noqa: SLF001
            headers={'User-Agent': USER_AGENT},
            transport=httpx.MockTransport(handler),
        )
        try:
            url = 'https://www.reddit.com/r/x/comments/p1/'
            start = time.perf_counter()
            await asyncio.gather(
                *(fetcher.fetch_thread(url) for _ in range(6))
            )
            elapsed = time.perf_counter() - start
        finally:
            await fetcher.close()

        # 6 requests at 2 req/s: 2 free, 4 throttled in 0.5s windows
        assert elapsed >= 1.5, f'expected throttling, got {elapsed:.2f}s'
