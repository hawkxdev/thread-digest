"""Global pytest fixtures."""

from collections.abc import Iterator

import pytest

from src import config as config_module
from src.config import Config


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Minimal valid env."""
    defaults = {
        'BOT_TOKEN': '123456789:TEST_TOKEN',
        'ADMIN_USER_ID': '111111',
        'ADMIN_CHAT_ID': '111111',
        'DEEPSEEK_API_KEY': 'sk-test-deepseek',
        'REDDIT_USER_AGENT': 'thread-digest:test',
    }
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    return defaults


@pytest.fixture
def reset_config_singleton() -> Iterator[None]:
    """Reset singleton around test."""
    config_module._config = None
    yield
    config_module._config = None


@pytest.fixture
def config(env_vars: dict[str, str], reset_config_singleton: None) -> Config:
    """Fresh Config instance."""
    return Config()  # type: ignore[call-arg]
