"""Bot handler tests with mocked pipeline."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.summarizer import SummarizationError
from src.bot import handlers
from src.config import Config
from src.fetchers.base import BasePlatformFetcher, Comment, Thread
from src.fetchers.reddit import RedditFetcher, RedditFetchError
from src.fetchers.x import XFetcher, XFetchError


def _thread() -> Thread:
    """Build a thread fixture."""
    return Thread(
        id='abc',
        platform='reddit',
        title='Sample',
        body='post body',
        author='op',
        score=10,
        num_comments=1,
        url='https://reddit.com/r/x/comments/abc/sample/',
        comments=[
            Comment(id='c1', body='hi', author='a', score=20, depth=0),
        ],
    )


def _summary() -> dict[str, object]:
    """Validated summary dict."""
    return {
        'tldr': 'Short summary.',
        'post_thesis': 'Post thesis.',
        'key_arguments': [
            {'side': 'for', 'text': 'arg one', 'votes': 20},
        ],
        'consensus': ['point A'],
        'controversial': ['point B'],
        'notable_quotes': [
            {'author': 'a', 'quote': 'hi', 'score': 20},
        ],
    }


def _message(text: str, user_id: int = 111111) -> MagicMock:
    """Build a Message-like mock."""
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.username = 'tester'
    msg.text = text
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch get_database_manager to return AsyncMock."""
    db = AsyncMock()
    db.create_digest_request.return_value = 42
    db.save_digest_result.return_value = None
    db.get_recent_requests.return_value = []
    monkeypatch.setattr(handlers, 'get_database_manager', lambda: db)
    return db


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, config: Config) -> Config:
    """Make handlers.get_config() return test config."""
    monkeypatch.setattr(handlers, 'get_config', lambda: config)
    return config


@pytest.mark.asyncio
async def test_start_sends_welcome(mock_db: AsyncMock) -> None:
    """/start replies with greeting."""
    msg = _message('/start')
    await handlers.on_start(msg)
    msg.answer.assert_awaited_once_with(handlers.START_MESSAGE)


@pytest.mark.asyncio
async def test_help_sends_help(mock_db: AsyncMock) -> None:
    """/help replies with help."""
    msg = _message('/help')
    await handlers.on_help(msg)
    msg.answer.assert_awaited_once_with(handlers.HELP_MESSAGE)


@pytest.mark.asyncio
async def test_history_empty(mock_db: AsyncMock) -> None:
    """Empty history returns explicit empty message."""
    msg = _message('/history')
    await handlers.on_history(msg)
    msg.answer.assert_awaited_once()
    text = msg.answer.call_args[0][0]
    assert 'История пуста' in text


@pytest.mark.asyncio
async def test_history_renders_recent(mock_db: AsyncMock) -> None:
    """Non-empty history lists URLs."""
    request = MagicMock()
    request.created_at = datetime(2026, 4, 25, 12, 30)
    request.url = 'https://reddit.com/r/x/comments/abc/'
    mock_db.get_recent_requests.return_value = [request]

    msg = _message('/history')
    await handlers.on_history(msg)

    text = msg.answer.call_args[0][0]
    assert '2026-04-25 12:30' in text
    assert 'reddit.com/r/x/comments/abc' in text


@pytest.mark.asyncio
async def test_url_unsupported_platform(
    mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-Reddit URL replies with unsupported message."""
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: None)
    msg = _message('https://twitter.com/x/status/1')

    await handlers.on_url(msg)

    msg.answer.assert_awaited_once_with(handlers.UNSUPPORTED_MESSAGE)
    mock_db.create_digest_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_url_happy_path(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full pipeline saves success and edits with formatted summary."""
    fetcher = AsyncMock()
    fetcher.fetch_thread.return_value = _thread()
    fetcher.close = AsyncMock()
    monkeypatch.setattr(handlers, '_build_fetcher', lambda cls: fetcher)
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: RedditFetcher)

    client = AsyncMock()
    client.close = AsyncMock()
    monkeypatch.setattr(handlers, 'DeepSeekClient', lambda config: client)

    monkeypatch.setattr(
        handlers,
        'summarize_thread',
        AsyncMock(return_value=_summary()),
    )

    progress = AsyncMock()
    progress.edit_text = AsyncMock()
    msg = _message('https://reddit.com/r/x/comments/abc/')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    mock_db.create_digest_request.assert_awaited_once()
    fetcher.fetch_thread.assert_awaited_once()
    progress.edit_text.assert_awaited()
    saved = mock_db.save_digest_result.await_args.kwargs
    assert saved['status'] == handlers.STATUS_SUCCESS
    assert json.loads(saved['summary_json'])['tldr'] == 'Short summary.'
    fetcher.close.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_url_fetch_error_not_found(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic Reddit error → not-found user message + fetch_error status."""
    fetcher = AsyncMock()
    fetcher.fetch_thread.side_effect = RedditFetchError('Reddit returned 404')
    fetcher.close = AsyncMock()
    monkeypatch.setattr(handlers, '_build_fetcher', lambda cls: fetcher)
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: RedditFetcher)
    monkeypatch.setattr(handlers, 'DeepSeekClient', lambda c: AsyncMock())

    progress = AsyncMock()
    progress.edit_text = AsyncMock()
    msg = _message('https://reddit.com/r/x/comments/zzz/')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    progress.edit_text.assert_awaited_with(handlers.NOT_FOUND_MESSAGE)
    saved = mock_db.save_digest_result.await_args.kwargs
    assert saved['status'] == handlers.STATUS_FETCH_ERROR


@pytest.mark.asyncio
async def test_url_fetch_error_rate_limit(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """429 error → rate-limit message."""
    fetcher = AsyncMock()
    fetcher.fetch_thread.side_effect = RedditFetchError('Reddit returned 429')
    fetcher.close = AsyncMock()
    monkeypatch.setattr(handlers, '_build_fetcher', lambda cls: fetcher)
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: RedditFetcher)
    monkeypatch.setattr(handlers, 'DeepSeekClient', lambda c: AsyncMock())

    progress = AsyncMock()
    progress.edit_text = AsyncMock()
    msg = _message('https://reddit.com/r/x/comments/zzz/')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    progress.edit_text.assert_awaited_with(handlers.RATE_LIMIT_MESSAGE)


@pytest.mark.asyncio
async def test_url_summarize_error(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SummarizationError → generic error + summarize_error status."""
    fetcher = AsyncMock()
    fetcher.fetch_thread.return_value = _thread()
    fetcher.close = AsyncMock()
    monkeypatch.setattr(handlers, '_build_fetcher', lambda cls: fetcher)
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: RedditFetcher)
    client = AsyncMock()
    client.close = AsyncMock()
    monkeypatch.setattr(handlers, 'DeepSeekClient', lambda c: client)
    monkeypatch.setattr(
        handlers,
        'summarize_thread',
        AsyncMock(side_effect=SummarizationError('schema mismatch')),
    )

    progress = AsyncMock()
    progress.edit_text = AsyncMock()
    msg = _message('https://reddit.com/r/x/comments/abc/')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    progress.edit_text.assert_awaited_with(handlers.GENERIC_ERROR_MESSAGE)
    saved = mock_db.save_digest_result.await_args.kwargs
    assert saved['status'] == handlers.STATUS_SUMMARIZE_ERROR


@pytest.mark.asyncio
async def test_url_setup_failure_persists_record(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_build_fetcher failure → unexpected_error saved + progress updated."""
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: RedditFetcher)

    def _boom(_: type) -> BasePlatformFetcher:
        raise RuntimeError('factory boom')

    monkeypatch.setattr(handlers, '_build_fetcher', _boom)

    progress = AsyncMock()
    progress.edit_text = AsyncMock()
    msg = _message('https://reddit.com/r/x/comments/abc/')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    saved = mock_db.save_digest_result.await_args.kwargs
    assert saved['status'] == handlers.STATUS_UNEXPECTED_ERROR
    assert 'factory boom' in saved['error']
    progress.edit_text.assert_awaited_with(handlers.GENERIC_ERROR_MESSAGE)


@pytest.mark.asyncio
async def test_url_edit_text_failure_does_not_block_persistence(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """edit_text raising must not prevent save_digest_result."""
    fetcher = AsyncMock()
    fetcher.fetch_thread.return_value = _thread()
    fetcher.close = AsyncMock()
    monkeypatch.setattr(handlers, '_build_fetcher', lambda cls: fetcher)
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: RedditFetcher)
    client = AsyncMock()
    client.close = AsyncMock()
    monkeypatch.setattr(handlers, 'DeepSeekClient', lambda c: client)
    monkeypatch.setattr(
        handlers,
        'summarize_thread',
        AsyncMock(return_value=_summary()),
    )

    progress = AsyncMock()
    progress.edit_text = AsyncMock(side_effect=RuntimeError('telegram api'))
    msg = _message('https://reddit.com/r/x/comments/abc/')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    mock_db.save_digest_result.assert_awaited()
    saved = mock_db.save_digest_result.await_args.kwargs
    assert saved['status'] == handlers.STATUS_SUCCESS
    fetcher.close.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_escapes_html_in_url(mock_db: AsyncMock) -> None:
    """Share URL with & must be escaped to survive HTML parse_mode."""
    request = MagicMock()
    request.created_at = datetime(2026, 4, 25, 12, 30)
    request.url = (
        'https://reddit.com/r/x/comments/abc/?utm_source=share&utm_medium=ios'
    )
    mock_db.get_recent_requests.return_value = [request]

    msg = _message('/history')
    await handlers.on_history(msg)

    text = msg.answer.call_args[0][0]
    assert '&amp;utm_medium=ios' in text
    assert '&utm_medium=ios' not in text.replace('&amp;', '')


@pytest.mark.asyncio
async def test_build_fetcher_returns_reddit_for_reddit_class(
    patch_config: Config,
) -> None:
    """Factory returns a RedditFetcher when given the RedditFetcher class."""
    fetcher = handlers._build_fetcher(RedditFetcher)
    try:
        assert isinstance(fetcher, RedditFetcher)
    finally:
        await fetcher.close()


@pytest.mark.asyncio
async def test_build_fetcher_returns_x_for_x_class(
    env_vars: dict[str, str],
    reset_config_singleton: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Factory returns XFetcher when X_API_KEY is set."""
    monkeypatch.setenv('X_API_KEY', 'new1_test_key')
    cfg = Config()  # type: ignore[call-arg]
    monkeypatch.setattr(handlers, 'get_config', lambda: cfg)
    fetcher = handlers._build_fetcher(XFetcher)
    try:
        assert isinstance(fetcher, XFetcher)
    finally:
        await fetcher.close()


@pytest.mark.asyncio
async def test_build_fetcher_x_raises_when_key_missing(
    env_vars: dict[str, str],
    reset_config_singleton: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    """Factory raises RuntimeError when X_API_KEY is None."""
    # Isolate from local .env (T2 pattern)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('X_API_KEY', raising=False)
    cfg = Config()  # type: ignore[call-arg]
    assert cfg.X_API_KEY is None
    monkeypatch.setattr(handlers, 'get_config', lambda: cfg)
    with pytest.raises(RuntimeError, match='X_API_KEY not configured'):
        handlers._build_fetcher(XFetcher)


@pytest.mark.asyncio
async def test_url_x_fetch_error_maps_to_user_message(
    mock_db: AsyncMock,
    patch_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XFetchError → STATUS_FETCH_ERROR + NOT_FOUND_MESSAGE."""
    fetcher = AsyncMock()
    fetcher.fetch_thread.side_effect = XFetchError('tweet not found')
    fetcher.close = AsyncMock()
    monkeypatch.setattr(handlers, '_build_fetcher', lambda cls: fetcher)
    monkeypatch.setattr(handlers, 'detect_fetcher', lambda url: XFetcher)
    client = AsyncMock()
    client.close = AsyncMock()
    monkeypatch.setattr(handlers, 'DeepSeekClient', lambda c: client)

    progress = AsyncMock()
    progress.edit_text = AsyncMock()
    msg = _message('https://x.com/user/status/123')
    msg.answer = AsyncMock(return_value=progress)

    await handlers.on_url(msg)

    saved = mock_db.save_digest_result.await_args.kwargs
    assert saved['status'] == handlers.STATUS_FETCH_ERROR
    assert 'tweet not found' in saved['error']
    progress.edit_text.assert_awaited_with(handlers.NOT_FOUND_MESSAGE)


def test_build_fetcher_raises_for_unknown_class() -> None:
    """Factory raises RuntimeError for unsupported fetcher classes."""

    class _OtherFetcher(BasePlatformFetcher):
        platform = 'other'

        async def fetch_thread(self, url: str) -> Thread:  # pragma: no cover
            raise NotImplementedError

        async def close(self) -> None:  # pragma: no cover
            return None

    with pytest.raises(RuntimeError, match='No factory for fetcher'):
        handlers._build_fetcher(_OtherFetcher)
