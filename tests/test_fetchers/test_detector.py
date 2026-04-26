"""URL detector tests."""

import pytest

from src.fetchers.detector import detect_fetcher
from src.fetchers.reddit import RedditFetcher
from src.fetchers.x import XFetcher


class TestDetectReddit:
    """Reddit URL variants resolve to RedditFetcher."""

    @pytest.mark.parametrize(
        'url',
        [
            'https://www.reddit.com/r/Python/comments/abc123/some_title/',
            'https://reddit.com/r/AskReddit/comments/xyz789/',
            'https://old.reddit.com/r/ClaudeCode/comments/1soqwfl/',
            'https://www.reddit.com/r/ClaudeCode/s/md3aDLTBC9',
            'https://reddit.com/r/Python/s/AbCdEf123',
            'https://redd.it/abc123',
            'http://www.reddit.com/r/Python/comments/abc123/',
        ],
    )
    def test_returns_reddit_fetcher(
        self,
        config: object,  # noqa: ARG002 — ensures config singleton ready
        url: str,
    ) -> None:
        assert detect_fetcher(url) is RedditFetcher


class TestDetectXWithKey:
    """X URLs resolve to XFetcher when X_API_KEY is set."""

    @pytest.mark.parametrize(
        'url',
        [
            'https://x.com/user/status/123',
            'https://www.x.com/heygurisingh/status/2047900744960123050',
            'https://twitter.com/user/status/123',
            'https://www.twitter.com/user/status/123',
            'https://mobile.twitter.com/user/status/123',
            'http://x.com/u/status/9',
        ],
    )
    def test_returns_x_fetcher(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
        url: str,
    ) -> None:
        monkeypatch.setenv('X_API_KEY', 'new1_test')
        assert detect_fetcher(url) is XFetcher


class TestDetectXWithoutKey:
    """X URLs return None when X_API_KEY missing (graceful degradation)."""

    def test_returns_none_when_key_unset(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,  # type: ignore[no-untyped-def]
    ) -> None:
        # Isolate from local .env (T2 pattern in brain troubleshooting):
        # chdir prevents pydantic-settings from reading project .env
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('X_API_KEY', raising=False)
        url = 'https://x.com/user/status/123'
        assert detect_fetcher(url) is None


class TestDetectUnsupported:
    """Unsupported URLs return None regardless of config."""

    @pytest.mark.parametrize(
        'url',
        [
            'https://www.threads.net/@user/post/abc',
            'https://example.com/article',
            'https://news.ycombinator.com/item?id=42',
            'https://t.co/abc123',
            'not_a_url',
            '',
        ],
    )
    def test_returns_none(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
        url: str,
    ) -> None:
        monkeypatch.setenv('X_API_KEY', 'new1_test')
        assert detect_fetcher(url) is None
