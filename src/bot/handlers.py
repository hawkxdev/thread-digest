"""Bot command and URL handlers."""

import json
import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from loguru import logger

from ..ai.api_client import DeepSeekClient
from ..ai.summarizer import SummarizationError, summarize_thread
from ..config import get_config
from ..database.manager import get_database_manager
from ..fetchers.base import BasePlatformFetcher
from ..fetchers.detector import detect_fetcher
from ..fetchers.reddit import RedditFetcher, RedditFetchError
from .formatter import format_summary

URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)

START_MESSAGE = (
    '👋 <b>Привет!</b>\n\n'
    'Пришли ссылку на Reddit-тред, и я верну краткую AI-сводку: '
    'TL;DR, ключевые аргументы, консенсус, спорные точки и цитаты.\n\n'
    '<b>Команды:</b>\n'
    '/help — справка\n'
    '/history — последние запросы'
)

HELP_MESSAGE = (
    '<b>Как пользоваться</b>\n\n'
    '1. Скопируй ссылку на Reddit-тред (canonical, old.reddit или /s/ short-link)\n'
    '2. Отправь её мне\n'
    '3. Получи структурированную сводку\n\n'
    '<b>Поддерживается:</b> Reddit (X/Twitter и Threads — в планах)'
)

UNSUPPORTED_MESSAGE = (
    '❌ Платформа не поддерживается. Сейчас работает только Reddit.'
)
NOT_FOUND_MESSAGE = '❌ Тред не найден или приватный.'
RATE_LIMIT_MESSAGE = '❌ Reddit rate limit, попробуйте через 30 сек.'
GENERIC_ERROR_MESSAGE = '❌ Не удалось обработать тред. Попробуйте позже.'

PROCESSING_MESSAGE = '⏳ Загружаю тред…'
SUMMARIZING_MESSAGE = '🤖 Готовлю сводку…'

STATUS_SUCCESS = 'success'
STATUS_FETCH_ERROR = 'fetch_error'
STATUS_SUMMARIZE_ERROR = 'summarize_error'
STATUS_UNEXPECTED_ERROR = 'unexpected_error'

router = Router()


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(START_MESSAGE)


@router.message(Command('help'))
async def on_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(HELP_MESSAGE)


@router.message(Command('history'))
async def on_history(message: Message) -> None:
    """Show last 20 user requests."""
    if not message.from_user:
        return
    db = get_database_manager()
    requests = await db.get_recent_requests(message.from_user.id, limit=20)
    if not requests:
        await message.answer('История пуста.')
        return
    lines = ['<b>📜 Последние запросы</b>']
    for req in requests:
        ts = req.created_at.strftime('%Y-%m-%d %H:%M')
        lines.append(f'• {ts} — {escape(req.url, quote=False)}')
    await message.answer('\n'.join(lines))


async def _safe_edit(progress: Message, text: str) -> None:
    """Edit message; swallow Telegram failures so persistence is not blocked."""
    try:
        await progress.edit_text(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'progress.edit_text failed: {exc}')


def _build_fetcher(
    fetcher_class: type[BasePlatformFetcher],
) -> BasePlatformFetcher:
    """Instantiate fetcher with config."""
    if fetcher_class is RedditFetcher:
        config = get_config()
        return RedditFetcher(
            user_agent=config.REDDIT_USER_AGENT,
            rate_limit_qpm=config.REDDIT_RATE_LIMIT_QPM,
            timeout=config.REDDIT_FETCH_TIMEOUT,
        )
    raise RuntimeError(f'No factory for fetcher: {fetcher_class}')


@router.message(F.text.regexp(URL_RE))
async def on_url(message: Message) -> None:
    """Handle URL: detect → fetch → summarize → format → reply."""
    if not message.from_user or not message.text:
        return

    match = URL_RE.search(message.text)
    if match is None:
        return
    url = match.group(0)

    fetcher_class = detect_fetcher(url)
    if fetcher_class is None:
        await message.answer(UNSUPPORTED_MESSAGE)
        return

    db = get_database_manager()
    request_id = await db.create_digest_request(
        user_id=message.from_user.id,
        url=url,
        platform=fetcher_class.platform,
    )

    progress = await message.answer(PROCESSING_MESSAGE)
    fetcher: BasePlatformFetcher | None = None
    client: DeepSeekClient | None = None

    try:
        fetcher = _build_fetcher(fetcher_class)
        client = DeepSeekClient(get_config())

        try:
            thread = await fetcher.fetch_thread(url)
        except RedditFetchError as exc:
            text_lower = str(exc).lower()
            error_text = str(exc)
            if 'rate' in text_lower or '429' in error_text:
                user_message = RATE_LIMIT_MESSAGE
            else:
                user_message = NOT_FOUND_MESSAGE
            logger.warning(f'Fetch failed for {url}: {exc}')
            await db.save_digest_result(
                request_id=request_id,
                summary_json='',
                tokens=0,
                status=STATUS_FETCH_ERROR,
                error=str(exc),
            )
            await _safe_edit(progress, user_message)
            return

        await _safe_edit(progress, SUMMARIZING_MESSAGE)

        try:
            summary = await summarize_thread(thread, client)
        except SummarizationError as exc:
            logger.error(f'Summarization failed for {url}: {exc}')
            await db.save_digest_result(
                request_id=request_id,
                summary_json='',
                tokens=0,
                status=STATUS_SUMMARIZE_ERROR,
                error=str(exc),
            )
            await _safe_edit(progress, GENERIC_ERROR_MESSAGE)
            return

        formatted = format_summary(summary, thread)
        await db.save_digest_result(
            request_id=request_id,
            summary_json=json.dumps(summary, ensure_ascii=False),
            tokens=0,
            status=STATUS_SUCCESS,
        )
        await _safe_edit(progress, formatted)

    except Exception as exc:  # noqa: BLE001
        logger.exception(f'Unexpected error processing {url}')
        await db.save_digest_result(
            request_id=request_id,
            summary_json='',
            tokens=0,
            status=STATUS_UNEXPECTED_ERROR,
            error=str(exc),
        )
        await _safe_edit(progress, GENERIC_ERROR_MESSAGE)
    finally:
        if fetcher is not None:
            await fetcher.close()
        if client is not None:
            await client.close()
