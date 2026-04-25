"""URL detector tests."""

import pytest

from src.fetchers.detector import detect_fetcher
from src.fetchers.reddit import RedditFetcher


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
    def test_returns_reddit_fetcher(self, url: str) -> None:
        assert detect_fetcher(url) is RedditFetcher


class TestDetectUnsupported:
    """Unsupported URLs return None."""

    @pytest.mark.parametrize(
        'url',
        [
            'https://twitter.com/user/status/123',
            'https://x.com/user/status/123',
            'https://www.threads.net/@user/post/abc',
            'https://example.com/article',
            'https://news.ycombinator.com/item?id=42',
            'not_a_url',
            '',
        ],
    )
    def test_returns_none(self, url: str) -> None:
        assert detect_fetcher(url) is None
