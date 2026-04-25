"""Admin middleware tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from src.bot.middleware import AdminAccessMiddleware
from src.config import Config


@pytest.fixture
def middleware() -> AdminAccessMiddleware:
    """Middleware instance."""
    return AdminAccessMiddleware()


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, config: Config) -> None:
    """Make get_config() return test config."""
    monkeypatch.setattr('src.bot.middleware.get_config', lambda: config)


def _message_event(user_id: int | None, text: str = 'hello') -> MagicMock:
    """Build a Message-like mock."""
    event = MagicMock(spec=Message)
    if user_id is None:
        event.from_user = None
    else:
        event.from_user = MagicMock()
        event.from_user.id = user_id
        event.from_user.username = 'tester'
    event.text = text
    return event


def _callback_event(user_id: int | None) -> MagicMock:
    """Build a CallbackQuery-like mock."""
    event = MagicMock(spec=CallbackQuery)
    if user_id is None:
        event.from_user = None
    else:
        event.from_user = MagicMock()
        event.from_user.id = user_id
        event.from_user.username = 'tester'
    event.data = 'cb:1'
    event.answer = AsyncMock()
    return event


@pytest.mark.asyncio
async def test_admin_message_passes_through(
    middleware: AdminAccessMiddleware,
    patch_config: None,
    config: Config,
) -> None:
    """Admin message reaches handler."""
    handler = AsyncMock(return_value='handled')
    event = _message_event(user_id=config.ADMIN_USER_ID)

    result = await middleware(handler, event, {})

    assert result == 'handled'
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_admin_message_silently_blocked(
    middleware: AdminAccessMiddleware,
    patch_config: None,
    config: Config,
) -> None:
    """Non-admin message returns None without calling handler."""
    handler = AsyncMock(return_value='handled')
    event = _message_event(user_id=config.ADMIN_USER_ID + 1)

    result = await middleware(handler, event, {})

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_callback_silently_blocked(
    middleware: AdminAccessMiddleware,
    patch_config: None,
    config: Config,
) -> None:
    """Non-admin callback returns None with no answer (no spinner reply)."""
    handler = AsyncMock(return_value='handled')
    event = _callback_event(user_id=config.ADMIN_USER_ID + 1)

    result = await middleware(handler, event, {})

    assert result is None
    handler.assert_not_awaited()
    event.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_without_user_returns_none(
    middleware: AdminAccessMiddleware,
    patch_config: None,
) -> None:
    """Message with no from_user is dropped."""
    handler = AsyncMock()
    event = _message_event(user_id=None)

    result = await middleware(handler, event, {})

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_event_passes_through(
    middleware: AdminAccessMiddleware,
    patch_config: None,
) -> None:
    """Non-Message non-Callback events are not gated."""
    handler = AsyncMock(return_value='handled')
    event = MagicMock()

    result = await middleware(handler, event, {})

    assert result == 'handled'
    handler.assert_awaited_once()
