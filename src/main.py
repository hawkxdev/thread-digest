"""Entry point for thread-digest bot."""

import asyncio

from .bot.main import main


def run() -> None:
    """Run bot via asyncio."""
    asyncio.run(main())


if __name__ == '__main__':
    run()
