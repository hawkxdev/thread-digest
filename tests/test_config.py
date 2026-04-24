"""Config tests."""

import pytest
from pydantic import ValidationError

from src.config import Config, get_config


class TestConfigLoading:
    """Required fields loading."""

    def test_required_fields_loaded(self, config: Config) -> None:
        assert config.BOT_TOKEN == '123456789:TEST_TOKEN'
        assert config.ADMIN_USER_ID == 111111
        assert config.ADMIN_CHAT_ID == 111111
        assert config.DEEPSEEK_API_KEY == 'sk-test-deepseek'
        assert config.REDDIT_USER_AGENT.startswith('thread-digest')

    def test_defaults_applied(self, config: Config) -> None:
        assert config.DEEPSEEK_MODEL == 'deepseek-chat'
        assert config.DEEPSEEK_MAX_TOKENS == 4000
        assert config.DEEPSEEK_TEMPERATURE == 0.3
        assert config.REDDIT_RATE_LIMIT_QPM == 5
        assert config.REDDIT_FETCH_TIMEOUT == 30.0
        assert config.log_level == 'INFO'
        assert config.environment == 'development'
        assert config.debug is False

    def test_missing_required_raises(
        self,
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv('BOT_TOKEN', raising=False)
        with pytest.raises(ValidationError):
            Config()  # type: ignore[call-arg]


class TestValidators:
    """Field validators."""

    def test_log_level_normalized_to_upper(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'debug')
        cfg = Config()  # type: ignore[call-arg]
        assert cfg.log_level == 'DEBUG'

    def test_log_level_invalid_raises(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'VERBOSE')
        with pytest.raises(ValidationError):
            Config()  # type: ignore[call-arg]

    def test_environment_invalid_raises(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv('ENVIRONMENT', 'preprod')
        with pytest.raises(ValidationError):
            Config()  # type: ignore[call-arg]

    @pytest.mark.parametrize('qpm', [0, 11, -1, 100])
    def test_qpm_out_of_range_raises(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
        qpm: int,
    ) -> None:
        monkeypatch.setenv('REDDIT_RATE_LIMIT_QPM', str(qpm))
        with pytest.raises(ValidationError):
            Config()  # type: ignore[call-arg]

    @pytest.mark.parametrize('temp', [-0.1, 1.1, 2.0])
    def test_temperature_out_of_range_raises(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
        temp: float,
    ) -> None:
        monkeypatch.setenv('DEEPSEEK_TEMPERATURE', str(temp))
        with pytest.raises(ValidationError):
            Config()  # type: ignore[call-arg]


class TestProperties:
    """Computed properties."""

    def test_is_development_true_by_default(self, config: Config) -> None:
        assert config.is_development is True
        assert config.is_production is False

    def test_is_production(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv('ENVIRONMENT', 'production')
        cfg = Config()  # type: ignore[call-arg]
        assert cfg.is_production is True
        assert cfg.is_development is False


class TestSingleton:
    """get_config singleton."""

    def test_singleton_returns_same_instance(
        self,
        env_vars: dict[str, str],
        reset_config_singleton: None,
    ) -> None:
        first = get_config()
        second = get_config()
        assert first is second

    def test_get_config_raises_on_missing_env(
        self,
        reset_config_singleton: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for key in ('BOT_TOKEN', 'ADMIN_USER_ID', 'DEEPSEEK_API_KEY'):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(RuntimeError):
            get_config()
