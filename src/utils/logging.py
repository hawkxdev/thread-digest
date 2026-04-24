"""Structured logging via loguru."""

import asyncio
import contextlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiogram.types import BufferedInputFile
from loguru import logger

from ..config import get_config

if TYPE_CHECKING:
    from aiogram import Bot

_logging_configured = False


def setup_logging() -> None:
    """Initialize logging."""
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    config = get_config()

    logger.remove()

    log_format = _get_log_format(config.debug)
    log_level = config.log_level

    _setup_console_logging(log_format, log_level)

    if config.environment != 'development':
        _setup_file_logging(log_format, log_level)


def _get_log_format(debug: bool) -> str:
    """Log format by mode."""
    if debug:
        return (
            '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | '
            '<level>{level: <8}</level> | '
            '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
            '<level>{message}</level>'
        )
    else:
        return (
            '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | '
            '<level>{level: <8}</level> | '
            '<level>{message}</level>'
        )


def _setup_console_logging(log_format: str, log_level: str) -> None:
    """Console sink."""
    logger.add(
        sys.stderr,
        format=log_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )


def _setup_file_logging(log_format: str, log_level: str) -> None:
    """File sinks with rotation."""
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)

    logger.add(
        logs_dir / 'thread_digest.log',
        format=log_format,
        level=log_level,
        rotation='1 day',
        retention='30 days',
        compression='gz',
        backtrace=True,
        diagnose=True,
    )

    logger.add(
        logs_dir / 'errors.log',
        format=log_format,
        level='ERROR',
        rotation='1 week',
        retention='12 weeks',
        compression='gz',
        backtrace=True,
        diagnose=True,
    )


def get_logger(name: str) -> Any:
    """Named logger."""
    return logger.bind(name=name)


def log_function_call(func_name: str, **kwargs: Any) -> None:
    """Log function call."""
    params = ', '.join(f'{k}={v}' for k, v in kwargs.items())
    logger.debug(f'Function call: {func_name}({params})')


def log_database_operation(operation: str, table: str, **details: Any) -> None:
    """Log database operation."""
    extra_info = ', '.join(f'{k}={v}' for k, v in details.items())
    logger.info(f'DB op: {operation} {table} | {extra_info}')


def log_telegram_event(
    event_type: str, user_id: int | None = None, **details: Any
) -> None:
    """Log Telegram event."""
    user_info = f'user_id={user_id}' if user_id else 'system'
    extra_info = ', '.join(f'{k}={v}' for k, v in details.items())
    logger.info(f'Telegram {event_type}: {user_info} | {extra_info}')


def log_parser_activity(
    parser_name: str, action: str, count: int = 0, **details: Any
) -> None:
    """Log parser activity."""
    extra_info = ', '.join(f'{k}={v}' for k, v in details.items())
    logger.info(
        f'Parser {parser_name}: {action} | count={count} | {extra_info}'
    )


class TelegramErrorHandler:
    """Ship ERROR logs to Telegram."""

    _queue: asyncio.Queue[str] | None = None
    _bot: 'Bot | None' = None
    _admin_id: int | None = None
    _initialized: bool = False

    @classmethod
    def initialize(cls, bot: 'Bot', admin_id: int) -> None:
        """Initialize handler."""
        if cls._initialized:
            return

        cls._queue = asyncio.Queue()
        cls._bot = bot
        cls._admin_id = admin_id
        cls._initialized = True

        logger.add(
            cls._sink,
            level='WARNING',
            format='{level.name}: {message}',
            filter=lambda record: record['level'].name in ('WARNING', 'ERROR'),
        )

    @classmethod
    def _sink(cls, message: str) -> None:
        """Enqueue message."""
        if cls._queue is not None:
            with contextlib.suppress(Exception):
                cls._queue.put_nowait(str(message).strip())

    @classmethod
    async def run_sender(cls) -> None:
        """Background queue drain."""
        if cls._queue is None or cls._bot is None or cls._admin_id is None:
            return

        while True:
            try:
                msg = await cls._queue.get()
                emoji = '🔴' if 'ERROR' in msg else '🟡'
                text = f'{emoji} {msg[:4000]}'
                await cls._bot.send_message(cls._admin_id, text)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f'TelegramErrorHandler send failed: {e}')

    @classmethod
    async def send_screenshot(cls, photo: bytes, caption: str) -> None:
        """Send screenshot to admin."""
        if not cls._bot or not cls._admin_id:
            return

        try:
            await cls._bot.send_photo(
                cls._admin_id,
                BufferedInputFile(photo, filename='screenshot.png'),
                caption=caption[:1024],
            )
        except Exception as e:
            print(f'TelegramErrorHandler send_screenshot failed: {e}')
