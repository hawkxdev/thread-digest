"""XFetcher tests with httpx.MockTransport."""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from src.fetchers.x import XFetcher, XFetchError, _parse_dt

FIXTURE_DIR = Path(__file__).parent.parent / 'fixtures'
API_KEY = 'new1_test_key'


def _load_fixture() -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURE_DIR / 'x_thread_small.json').read_text())


def _make_fetcher(handler: httpx.MockTransport) -> XFetcher:
    """Build fetcher with injected transport."""
    fetcher = XFetcher(api_key=API_KEY, max_pages=5)
    fetcher._client = httpx.AsyncClient(  # noqa: SLF001
        base_url='https://api.twitterapi.io',
        headers={'X-API-Key': API_KEY},
        transport=handler,
    )
    return fetcher


@pytest.fixture
def fixture_payload() -> dict:  # type: ignore[type-arg]
    return _load_fixture()


@pytest.fixture
def single_page_fetcher(
    fixture_payload: dict,  # type: ignore[type-arg]
) -> Iterator[XFetcher]:
    """Returns full thread in a single page (has_next_page False)."""
    payload = {**fixture_payload, 'has_next_page': False, 'next_cursor': ''}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    fetcher = _make_fetcher(httpx.MockTransport(handler))
    yield fetcher


# === extract_id ===


class TestExtractId:
    """URL → tweet id."""

    @pytest.mark.parametrize(
        ('url', 'expected'),
        [
            ('https://x.com/u/status/123', '123'),
            (
                'https://twitter.com/heygurisingh/status/2047900744960123050',
                '2047900744960123050',
            ),
            ('https://www.x.com/u/status/9?s=46', '9'),
        ],
    )
    def test_extracts(self, url: str, expected: str) -> None:
        assert XFetcher._extract_id(url) == expected  # noqa: SLF001

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(XFetchError, match='Cannot parse'):
            XFetcher._extract_id('https://x.com/u/profile')  # noqa: SLF001


# === build_thread ===


class TestBuildThread:
    """OP detection + sort + tree construction."""

    @pytest.mark.asyncio
    async def test_op_detected_via_conversation_id(
        self, single_page_fetcher: XFetcher
    ) -> None:
        thread = await single_page_fetcher.fetch_thread(
            'https://x.com/user/status/1000000000000000000'
        )
        assert thread.id == '1000000000000000000'
        assert thread.author == 'user0'
        assert thread.platform == 'x'
        assert len(thread.comments) == 11  # 12 total minus OP
        await single_page_fetcher.close()

    @pytest.mark.asyncio
    async def test_op_detection_works_for_reply_url(
        self, single_page_fetcher: XFetcher
    ) -> None:
        # User pastes reply URL (not OP) — OP still found via conversationId
        thread = await single_page_fetcher.fetch_thread(
            'https://x.com/user/status/1000000000000000005'
        )
        assert thread.id == '1000000000000000000'
        await single_page_fetcher.close()

    @pytest.mark.asyncio
    async def test_replies_sorted_by_created_at(
        self, single_page_fetcher: XFetcher
    ) -> None:
        thread = await single_page_fetcher.fetch_thread(
            'https://x.com/user/status/1000000000000000000'
        )
        timestamps = [c.created_utc for c in thread.comments]
        non_none = [t for t in timestamps if t is not None]
        assert non_none == sorted(non_none)
        await single_page_fetcher.close()


# === pagination ===


class TestPagination:
    """Multi-page loop, cursor handling, MAX_PAGES cap."""

    @pytest.mark.asyncio
    async def test_two_pages_then_stops(
        self,
        fixture_payload: dict,  # type: ignore[type-arg]
    ) -> None:
        page1_tweets = fixture_payload['tweets'][:6]
        page2_tweets = fixture_payload['tweets'][6:]
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            if call_count['n'] == 1:
                return httpx.Response(
                    200,
                    json={
                        'tweets': page1_tweets,
                        'has_next_page': True,
                        'next_cursor': 'CURSOR_2',
                        'status': 'success',
                        'msg': '',
                    },
                )
            return httpx.Response(
                200,
                json={
                    'tweets': page2_tweets,
                    'has_next_page': False,
                    'next_cursor': None,
                    'status': 'success',
                    'msg': None,
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        thread = await fetcher.fetch_thread(
            'https://x.com/u/status/1000000000000000000'
        )
        assert call_count['n'] == 2
        assert len(thread.comments) == 11
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_empty_page_breaks_loop(
        self,
        fixture_payload: dict,  # type: ignore[type-arg]
    ) -> None:
        # has_next_page lies — second page returns no tweets
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            if call_count['n'] == 1:
                return httpx.Response(
                    200,
                    json={
                        **fixture_payload,
                        'has_next_page': True,
                        'next_cursor': 'CURSOR_2',
                    },
                )
            return httpx.Response(
                200,
                json={
                    'tweets': [],
                    'has_next_page': True,
                    'next_cursor': 'CURSOR_3',
                    'status': 'success',
                    'msg': '',
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        await fetcher.fetch_thread(
            'https://x.com/u/status/1000000000000000000'
        )
        assert call_count['n'] == 2  # break on empty
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_repeated_cursor_breaks_loop(
        self,
        fixture_payload: dict,  # type: ignore[type-arg]
    ) -> None:
        # Server keeps sending same cursor with new tweets — break
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            return httpx.Response(
                200,
                json={
                    **fixture_payload,
                    'has_next_page': True,
                    'next_cursor': 'SAME_CURSOR',
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        await fetcher.fetch_thread(
            'https://x.com/u/status/1000000000000000000'
        )
        # First page accepted, second page same cursor → break
        assert call_count['n'] == 2
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_max_pages_caps_runaway(
        self,
        fixture_payload: dict,  # type: ignore[type-arg]
    ) -> None:
        # Endless distinct pages — MAX_PAGES caps at 5
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            # Each page has unique tweets to avoid id-dedup break;
            # all are replies so OP fallback returns nothing → expected error
            tweets = [
                {
                    **fixture_payload['tweets'][1],
                    'id': f'unique_{call_count["n"]}_{i}',
                    'isReply': True,
                    'inReplyToId': '9999999999999999999',
                }
                for i in range(3)
            ]
            return httpx.Response(
                200,
                json={
                    'tweets': tweets,
                    'has_next_page': True,
                    'next_cursor': f'CURSOR_{call_count["n"]}',
                    'status': 'success',
                    'msg': '',
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        with pytest.raises(XFetchError, match='Cannot find OP'):
            await fetcher.fetch_thread(
                'https://x.com/u/status/9999999999999999999'
            )
        # Loop stopped at MAX_PAGES = 5 (would be infinite without cap)
        assert call_count['n'] == 5
        await fetcher.close()


# === errors ===


class TestErrors:
    """Status/auth/network failures."""

    @pytest.mark.asyncio
    async def test_401_raises_no_retry(self) -> None:
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            return httpx.Response(401, json={'msg': 'unauthorized'})

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        with pytest.raises(XFetchError, match='401'):
            await fetcher.fetch_thread('https://x.com/u/status/1')
        assert call_count['n'] == 1  # No retry on 401
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_429_retries_then_succeeds(
        self,
        fixture_payload: dict,  # type: ignore[type-arg]
    ) -> None:
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            if call_count['n'] == 1:
                return httpx.Response(429, json={'msg': 'rate limit'})
            return httpx.Response(
                200,
                json={
                    **fixture_payload,
                    'has_next_page': False,
                    'next_cursor': '',
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        thread = await fetcher.fetch_thread(
            'https://x.com/u/status/1000000000000000000'
        )
        assert call_count['n'] == 2  # First 429, second 200
        assert thread.id == '1000000000000000000'
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_status_error_in_payload_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    'tweets': [],
                    'has_next_page': False,
                    'next_cursor': '',
                    'status': 'error',
                    'msg': 'tweet not found',
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        with pytest.raises(XFetchError, match='tweet not found'):
            await fetcher.fetch_thread('https://x.com/u/status/1')
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_empty_thread_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    'tweets': [],
                    'has_next_page': False,
                    'next_cursor': '',
                    'status': 'success',
                    'msg': '',
                },
            )

        fetcher = _make_fetcher(httpx.MockTransport(handler))
        with pytest.raises(XFetchError, match='Empty thread'):
            await fetcher.fetch_thread('https://x.com/u/status/1')
        await fetcher.close()


# === datetime parsing ===


class TestParseDt:
    """createdAt string formats."""

    @pytest.mark.parametrize(
        'ts',
        [
            'Wed Apr 16 21:23:45 +0000 2026',
            '2026-04-16T21:23:45+00:00',
            '2026-04-16T21:23:45Z',
        ],
    )
    def test_parses_known_formats(self, ts: str) -> None:
        assert _parse_dt(ts) is not None

    def test_unparsable_returns_none(self) -> None:
        assert _parse_dt('garbage') is None
        assert _parse_dt('') is None
