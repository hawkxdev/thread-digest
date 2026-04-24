"""Async database manager."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from .models import Base, DigestRequest, DigestResult


def _enable_sqlite_fk(dbapi_connection: Any, connection_record: Any) -> None:
    """Enforce foreign keys per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


class DatabaseManager:
    """Async SQLAlchemy wrapper."""

    def __init__(self, database_url: str) -> None:
        """Init engine and session factory."""
        self.database_url = database_url

        connect_args = {}
        if 'sqlite' in database_url:
            connect_args = {'check_same_thread': False}

        self.engine = create_async_engine(
            database_url,
            connect_args=connect_args,
            poolclass=StaticPool,
            echo=False,
        )

        if 'sqlite' in database_url:
            event.listen(self.engine.sync_engine, 'connect', _enable_sqlite_fk)

        self.async_session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self) -> None:
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Yield session with rollback on exception."""
        async with self.async_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        """Dispose engine."""
        await self.engine.dispose()

    async def health_check(self) -> bool:
        """Return True if DB reachable."""
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text('SELECT 1'))
            return True
        except Exception:
            return False

    async def create_digest_request(
        self, user_id: int, url: str, platform: str
    ) -> int:
        """Insert request, return new id."""
        async with self.async_session_factory() as session:
            request = DigestRequest(
                user_id=user_id, url=url, platform=platform
            )
            session.add(request)
            await session.commit()
            await session.refresh(request)
            return request.id

    async def save_digest_result(
        self,
        request_id: int,
        summary_json: str,
        tokens: int,
        status: str,
        error: str | None = None,
    ) -> None:
        """Persist summarization outcome."""
        async with self.async_session_factory() as session:
            result = DigestResult(
                request_id=request_id,
                summary_json=summary_json,
                tokens_used=tokens,
                status=status,
                error_message=error,
            )
            session.add(result)
            await session.commit()

    async def get_recent_requests(
        self, user_id: int, limit: int = 20
    ) -> list[DigestRequest]:
        """Return user requests newest first."""
        async with self.async_session_factory() as session:
            query = (
                select(DigestRequest)
                .where(DigestRequest.user_id == user_id)
                .order_by(
                    DigestRequest.created_at.desc(),
                    DigestRequest.id.desc(),
                )
                .limit(limit)
            )
            result = await session.execute(query)
            return list(result.scalars().all())


database_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Return singleton instance."""
    if database_manager is None:
        raise RuntimeError('Database manager not initialized')
    return database_manager


def initialize_database_manager(database_url: str) -> DatabaseManager:
    """Create and register singleton."""
    global database_manager
    database_manager = DatabaseManager(database_url)
    return database_manager


async def initialize_database(
    database_url: str, create_tables: bool = True
) -> DatabaseManager:
    """Init singleton, create tables, verify."""
    try:
        manager = initialize_database_manager(database_url)

        if create_tables:
            await manager.create_tables()

        if not await manager.health_check():
            raise RuntimeError('Database unavailable after init')

        return manager

    except Exception as e:
        raise RuntimeError(f'Failed to initialize database: {e}') from e
