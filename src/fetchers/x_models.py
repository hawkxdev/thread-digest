"""Pydantic models for twitterapi.io."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# === Author ===


class XAuthor(BaseModel):
    """Tweet author."""

    model_config = ConfigDict(extra='ignore', populate_by_name=True)

    id: str
    user_name: str = Field(alias='userName')
    name: str | None = None


# === Tweet ===


class XTweet(BaseModel):
    """Single tweet."""

    model_config = ConfigDict(extra='ignore', populate_by_name=True)

    id: str
    text: str
    url: str
    created_at: str = Field(alias='createdAt')
    lang: str | None = None
    is_reply: bool = Field(alias='isReply', default=False)
    in_reply_to_id: str | None = Field(alias='inReplyToId', default=None)
    conversation_id: str = Field(alias='conversationId')
    like_count: int = Field(alias='likeCount', default=0)
    reply_count: int = Field(alias='replyCount', default=0)
    view_count: int = Field(alias='viewCount', default=0)
    is_limited_reply: bool = Field(alias='isLimitedReply', default=False)
    author: XAuthor


# === Response envelope ===


class XThreadResponse(BaseModel):
    """Thread context response."""

    model_config = ConfigDict(extra='ignore', populate_by_name=True)

    tweets: list[XTweet]
    has_next_page: bool = False
    next_cursor: str = ''
    status: Literal['success', 'error'] = 'success'
    msg: str = ''
