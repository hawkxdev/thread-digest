"""SQLAlchemy models."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base ORM class."""


class DigestRequest(Base):
    """User digest request."""

    __tablename__ = 'digest_requests'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    platform: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f'<DigestRequest(id={self.id}, user_id={self.user_id}, '
            f'platform={self.platform})>'
        )


class DigestResult(Base):
    """AI summary result."""

    __tablename__ = 'digest_results'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('digest_requests.id'),
        nullable=False,
        index=True,
    )
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f'<DigestResult(id={self.id}, request_id={self.request_id}, '
            f'status={self.status})>'
        )
