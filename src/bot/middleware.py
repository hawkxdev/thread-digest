"""Bot access middleware."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..config import get_config
from ..utils.logging import get_logger, log_telegram_event

logger = get_logger(__name__)


class AdminAccessMiddleware(BaseMiddleware):
    """Admin-only access guard."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Check user access."""
        config = get_config()

        user_id = None
        username = 'unknown'

        if isinstance(event, Message):
            if not event.from_user:
                logger.warning('Message received without user info')
                return None
            user_id = event.from_user.id
            username = event.from_user.username or 'unknown'
            event_type = 'message'
            event_details = {'message_text': event.text or ''}

        elif isinstance(event, CallbackQuery):
            if not event.from_user:
                logger.warning('Callback received without user info')
                return None
            user_id = event.from_user.id
            username = event.from_user.username or 'unknown'
            event_type = 'callback'
            event_details = {'callback_data': event.data or ''}

        else:
            return await handler(event, data)

        if user_id != config.ADMIN_USER_ID:
            log_telegram_event(
                f'{event_type}_access_denied',
                user_id,
                username=username,
                **event_details,
            )

            logger.warning(
                f'Unauthorized access attempt: '
                f'user_id={user_id}, username=@{username}, '
                f'event_type={event_type}'
            )

            if isinstance(event, CallbackQuery):
                await event.answer('❌ Доступ запрещён', show_alert=True)

            return None

        log_telegram_event(
            f'{event_type}_access_granted', user_id, username=username
        )
        return await handler(event, data)
