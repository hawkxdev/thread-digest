"""Bot init and polling entry."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

from ..config import get_config
from ..database.manager import get_database_manager, initialize_database
from ..utils.logging import get_logger, log_telegram_event, setup_logging
from .handlers import router
from .middleware import AdminAccessMiddleware


async def create_bot() -> Bot:
    """Create Bot from config."""
    config = get_config()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    return bot


async def create_dispatcher() -> Dispatcher:
    """Create Dispatcher with middleware and router."""
    dp = Dispatcher()

    dp.message.middleware(AdminAccessMiddleware())
    dp.callback_query.middleware(AdminAccessMiddleware())

    dp.include_router(router)

    return dp


async def setup_bot_commands(bot: Bot) -> None:
    """Register admin-only command list."""
    config = get_config()

    await bot.set_my_commands([])

    owner_commands = [
        BotCommand(command='start', description='Запустить бота'),
        BotCommand(command='help', description='Показать справку'),
        BotCommand(command='history', description='История запросов'),
    ]

    await bot.set_my_commands(
        owner_commands, scope=BotCommandScopeChat(chat_id=config.ADMIN_USER_ID)
    )


async def on_startup(bot: Bot) -> None:
    """Init DB and register commands on startup."""
    logger = get_logger(__name__)
    config = get_config()

    logger.info('Starting thread-digest bot...')

    try:
        await initialize_database(config.DATABASE_URL)
        logger.info('Database initialized')

        await setup_bot_commands(bot)
        logger.info('Bot commands registered')

        bot_info = await bot.get_me()
        logger.info(
            f'Bot started: @{bot_info.username} ({bot_info.full_name})'
        )

        log_telegram_event('bot_startup', None, bot_username=bot_info.username)

    except Exception as e:
        logger.error(f'Bot startup failed: {e}')
        raise


async def on_shutdown(bot: Bot) -> None:
    """Close DB and Telegram session."""
    logger = get_logger(__name__)

    logger.info('Stopping thread-digest bot...')

    try:
        db_manager = get_database_manager()
        await db_manager.close()
        logger.info('Database connection closed')

        log_telegram_event('bot_shutdown', None)

    except Exception as e:
        logger.error(f'Bot shutdown error: {e}')

    await bot.session.close()


async def start_polling() -> None:
    """Run bot in polling mode."""
    logger = get_logger(__name__)

    try:
        bot = await create_bot()
        dp = await create_dispatcher()

        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        await dp.start_polling(bot, drop_pending_updates=True)

    except asyncio.CancelledError:
        logger.info('Stop signal received')
    except Exception as e:
        logger.error(f'Critical error during polling: {e}')
        raise


async def main() -> None:
    """Entry point: setup logging and run polling."""
    setup_logging()
    logger = get_logger(__name__)

    try:
        logger.info('Initializing thread-digest bot...')
        await start_polling()

    except KeyboardInterrupt:
        logger.info('Keyboard interrupt received')
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        raise
    finally:
        logger.info('thread-digest bot stopped')


if __name__ == '__main__':
    asyncio.run(main())
