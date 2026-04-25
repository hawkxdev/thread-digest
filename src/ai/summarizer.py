"""Thread summarization via DeepSeek."""

import json
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

from ..fetchers.base import Thread
from .api_client import APIResponse, DeepSeekClient
from .prompts import SYSTEM_PROMPT, build_user_prompt


class _KeyArgument(BaseModel):
    """One pro/contra/neutral argument with its supporting score."""

    model_config = ConfigDict(extra='forbid')

    side: Literal['for', 'against', 'neutral']
    text: str
    votes: int


class _NotableQuote(BaseModel):
    """Verbatim quote with attribution."""

    model_config = ConfigDict(extra='forbid')

    author: str
    quote: str
    score: int


class ThreadSummary(BaseModel):
    """Validated DeepSeek summarization response."""

    model_config = ConfigDict(extra='forbid')

    tldr: str
    post_thesis: str
    key_arguments: list[_KeyArgument]
    consensus: list[str]
    controversial: list[str]
    notable_quotes: list[_NotableQuote]


class SummarizationError(Exception):
    """Raised when the model fails to produce a usable summary."""


async def summarize_thread(
    thread: Thread,
    client: DeepSeekClient,
    *,
    max_comments: int = 200,
) -> dict[str, Any]:
    """Summarize a Reddit thread into structured JSON."""
    user_message = build_user_prompt(thread, max_comments=max_comments)

    response: APIResponse = await client.chat_completion(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        json_mode=True,
        operation_name='Thread summarization',
        request_id=thread.id,
    )

    if not response.success or not response.content:
        raise SummarizationError(
            f'DeepSeek returned no content for thread {thread.id}'
        )

    try:
        parsed: dict[str, Any] = json.loads(response.content)
    except json.JSONDecodeError as exc:
        logger.error(
            'Invalid JSON from DeepSeek for thread {} | error: {}',
            thread.id,
            exc,
        )
        raise SummarizationError(
            f'DeepSeek returned invalid JSON for thread {thread.id}: {exc}'
        ) from exc

    try:
        validated = ThreadSummary.model_validate(parsed)
    except ValidationError as exc:
        logger.error(
            'Schema mismatch from DeepSeek for thread {} | error: {}',
            thread.id,
            exc,
        )
        raise SummarizationError(
            f'DeepSeek response failed schema validation for thread '
            f'{thread.id}: {exc}'
        ) from exc

    return validated.model_dump()
