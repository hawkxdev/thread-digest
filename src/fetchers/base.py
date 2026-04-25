"""Platform fetcher base."""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field


class Comment(BaseModel):
    """Single thread comment."""

    id: str
    author: str | None = None
    body: str
    score: int = 0
    created_utc: datetime | None = None
    depth: int = 0
    replies: list['Comment'] = Field(default_factory=list)


class Thread(BaseModel):
    """Thread post with comments."""

    id: str
    platform: str
    title: str
    body: str = ''
    author: str | None = None
    score: int = 0
    num_comments: int = 0
    created_utc: datetime | None = None
    url: str
    comments: list[Comment] = Field(default_factory=list)


class BasePlatformFetcher(ABC):
    """Abstract platform fetcher."""

    platform: str

    @abstractmethod
    async def fetch_thread(self, url: str) -> Thread:
        """Fetch thread from URL."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
