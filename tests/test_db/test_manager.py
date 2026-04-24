"""Tests for DatabaseManager."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.database.manager import DatabaseManager
from src.database.models import DigestRequest, DigestResult

TEST_DB_URL = 'sqlite+aiosqlite:///:memory:'


@pytest_asyncio.fixture
async def db_manager() -> AsyncIterator[DatabaseManager]:
    """Fresh in-memory manager per test."""
    manager = DatabaseManager(TEST_DB_URL)
    await manager.create_tables()
    try:
        yield manager
    finally:
        await manager.close()


class TestHealthCheck:
    async def test_returns_true_for_fresh_db(
        self, db_manager: DatabaseManager
    ) -> None:
        assert await db_manager.health_check() is True


class TestCreateDigestRequest:
    async def test_persists_fields(self, db_manager: DatabaseManager) -> None:
        request_id = await db_manager.create_digest_request(
            user_id=222,
            url='https://reddit.com/r/b/2',
            platform='reddit',
        )
        async with db_manager.async_session_factory() as session:
            row = await session.get(DigestRequest, request_id)
        assert row is not None
        assert row.user_id == 222
        assert row.url == 'https://reddit.com/r/b/2'
        assert row.platform == 'reddit'
        assert row.created_at is not None


class TestSaveDigestResult:
    async def test_stores_success_record(
        self, db_manager: DatabaseManager
    ) -> None:
        request_id = await db_manager.create_digest_request(
            user_id=1, url='https://x', platform='reddit'
        )
        await db_manager.save_digest_result(
            request_id=request_id,
            summary_json='{"tldr": "ok"}',
            tokens=500,
            status='success',
        )
        async with db_manager.async_session_factory() as session:
            rows = (
                (await session.execute(select(DigestResult))).scalars().all()
            )
        assert len(rows) == 1
        assert rows[0].request_id == request_id
        assert rows[0].summary_json == '{"tldr": "ok"}'
        assert rows[0].tokens_used == 500
        assert rows[0].status == 'success'
        assert rows[0].error_message is None

    async def test_stores_error_message(
        self, db_manager: DatabaseManager
    ) -> None:
        request_id = await db_manager.create_digest_request(
            user_id=1, url='https://x', platform='reddit'
        )
        await db_manager.save_digest_result(
            request_id=request_id,
            summary_json='',
            tokens=0,
            status='error',
            error='DeepSeek timeout',
        )
        async with db_manager.async_session_factory() as session:
            row = (await session.execute(select(DigestResult))).scalars().one()
        assert row.status == 'error'
        assert row.error_message == 'DeepSeek timeout'


class TestGetRecentRequests:
    async def test_returns_empty_for_unknown_user(
        self, db_manager: DatabaseManager
    ) -> None:
        result = await db_manager.get_recent_requests(user_id=9999)
        assert result == []

    async def test_filters_by_user(self, db_manager: DatabaseManager) -> None:
        await db_manager.create_digest_request(
            user_id=1, url='https://a', platform='reddit'
        )
        await db_manager.create_digest_request(
            user_id=2, url='https://b', platform='reddit'
        )
        own = await db_manager.get_recent_requests(user_id=1)
        assert len(own) == 1
        assert own[0].user_id == 1

    async def test_sorted_newest_first(
        self, db_manager: DatabaseManager
    ) -> None:
        first = await db_manager.create_digest_request(
            user_id=7, url='https://a', platform='reddit'
        )
        second = await db_manager.create_digest_request(
            user_id=7, url='https://b', platform='reddit'
        )
        third = await db_manager.create_digest_request(
            user_id=7, url='https://c', platform='reddit'
        )
        recent = await db_manager.get_recent_requests(user_id=7)
        returned_ids = [r.id for r in recent]
        assert returned_ids == [third, second, first]

    async def test_respects_limit(self, db_manager: DatabaseManager) -> None:
        for i in range(5):
            await db_manager.create_digest_request(
                user_id=8, url=f'https://x/{i}', platform='reddit'
            )
        recent = await db_manager.get_recent_requests(user_id=8, limit=2)
        assert len(recent) == 2


class TestGetSession:
    async def test_context_manager_rolls_back_on_exception(
        self, db_manager: DatabaseManager
    ) -> None:
        with pytest.raises(ValueError, match='boom'):
            async with db_manager.get_session() as session:
                session.add(
                    DigestRequest(
                        user_id=42,
                        url='https://x',
                        platform='reddit',
                    )
                )
                raise ValueError('boom')

        async with db_manager.async_session_factory() as verify:
            rows = (
                (await verify.execute(select(DigestRequest))).scalars().all()
            )
        assert rows == []


class TestForeignKey:
    async def test_orphan_request_id_rejected(
        self, db_manager: DatabaseManager
    ) -> None:
        with pytest.raises(IntegrityError):
            await db_manager.save_digest_result(
                request_id=99999,
                summary_json='{}',
                tokens=0,
                status='success',
            )
