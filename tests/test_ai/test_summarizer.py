"""Summarizer tests with mocked DeepSeekClient."""

import json
from unittest.mock import AsyncMock

import pytest

from src.ai.api_client import APIResponse, DeepSeekClient
from src.ai.summarizer import SummarizationError, summarize_thread
from src.fetchers.base import Comment, Thread


def _thread() -> Thread:
    return Thread(
        id='t1',
        platform='reddit',
        title='Sample',
        body='post body',
        author='op',
        score=10,
        num_comments=2,
        url='https://reddit.com/r/x/comments/t1/',
        comments=[
            Comment(
                id='c1',
                body='comment one',
                author='a',
                score=20,
                depth=0,
            ),
            Comment(
                id='c2',
                body='comment two',
                author='b',
                score=5,
                depth=0,
            ),
        ],
    )


def _ok_response(payload: dict[str, object]) -> APIResponse:
    return APIResponse(
        content=json.dumps(payload),
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        execution_time=1.23,
        success=True,
    )


def _fail_response() -> APIResponse:
    return APIResponse(
        content=None,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        execution_time=0.5,
        success=False,
    )


def _make_client() -> DeepSeekClient:
    client = DeepSeekClient.__new__(DeepSeekClient)
    client.chat_completion = AsyncMock()  # type: ignore[method-assign]
    return client


def _valid_payload() -> dict[str, object]:
    """Minimal schema-valid summary payload."""
    return {
        'tldr': 'Short.',
        'post_thesis': 'OP claim.',
        'key_arguments': [
            {'side': 'for', 'text': 'argA', 'votes': 20},
        ],
        'consensus': [],
        'controversial': [],
        'notable_quotes': [],
    }


class TestSummarizeThreadHappyPath:
    """Happy-path: client returns valid JSON, summarize_thread parses it."""

    async def test_returns_parsed_dict(self) -> None:
        client = _make_client()
        payload = {
            'tldr': 'Short.',
            'post_thesis': 'OP claim.',
            'key_arguments': [
                {'side': 'for', 'text': 'argA', 'votes': 20},
            ],
            'consensus': ['c1'],
            'controversial': [],
            'notable_quotes': [
                {'author': 'u/a', 'quote': 'comment one', 'score': 20},
            ],
        }
        client.chat_completion.return_value = _ok_response(payload)  # type: ignore[attr-defined]

        result = await summarize_thread(_thread(), client)

        assert result == payload
        assert result['tldr'] == 'Short.'

    async def test_passes_json_mode_true(self) -> None:
        client = _make_client()
        client.chat_completion.return_value = _ok_response(  # type: ignore[attr-defined]
            _valid_payload()
        )

        await summarize_thread(_thread(), client)

        kwargs = client.chat_completion.call_args.kwargs  # type: ignore[attr-defined]
        assert kwargs['json_mode'] is True
        assert kwargs['request_id'] == 't1'

    async def test_max_comments_passed_to_user_prompt(self) -> None:
        """max_comments override reaches the prompt builder."""
        client = _make_client()
        client.chat_completion.return_value = _ok_response(  # type: ignore[attr-defined]
            _valid_payload()
        )

        await summarize_thread(_thread(), client, max_comments=1)

        user_msg = client.chat_completion.call_args.kwargs['user_message']  # type: ignore[attr-defined]
        # Top-1 by score = 'comment one' (score 20)
        assert 'comment one' in user_msg
        assert 'comment two' not in user_msg

    async def test_accepts_empty_consensus_and_controversial(
        self,
    ) -> None:
        """0-4 rule: empty lists must validate."""
        client = _make_client()
        payload = _valid_payload()
        payload['consensus'] = []
        payload['controversial'] = []
        client.chat_completion.return_value = _ok_response(payload)  # type: ignore[attr-defined]

        result = await summarize_thread(_thread(), client)

        assert result['consensus'] == []
        assert result['controversial'] == []


class TestSummarizeThreadErrors:
    """Error paths."""

    async def test_raises_when_success_false(self) -> None:
        client = _make_client()
        client.chat_completion.return_value = _fail_response()  # type: ignore[attr-defined]

        with pytest.raises(SummarizationError, match='no content'):
            await summarize_thread(_thread(), client)

    async def test_raises_when_content_empty(self) -> None:
        client = _make_client()
        client.chat_completion.return_value = APIResponse(  # type: ignore[attr-defined]
            content='',
            prompt_tokens=10,
            completion_tokens=0,
            total_tokens=10,
            execution_time=0.1,
            success=True,
        )

        with pytest.raises(SummarizationError, match='no content'):
            await summarize_thread(_thread(), client)

    async def test_raises_on_invalid_json(self) -> None:
        client = _make_client()
        client.chat_completion.return_value = APIResponse(  # type: ignore[attr-defined]
            content='not valid json {{{',
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            execution_time=1.0,
            success=True,
        )

        with pytest.raises(SummarizationError, match='invalid JSON'):
            await summarize_thread(_thread(), client)


class TestSummarizeThreadSchemaValidation:
    """Pydantic schema enforcement after json.loads."""

    async def test_raises_when_required_key_missing(self) -> None:
        client = _make_client()
        payload = _valid_payload()
        del payload['notable_quotes']
        client.chat_completion.return_value = _ok_response(payload)  # type: ignore[attr-defined]

        with pytest.raises(SummarizationError, match='schema validation'):
            await summarize_thread(_thread(), client)

    async def test_raises_on_extra_top_level_key(self) -> None:
        client = _make_client()
        payload = _valid_payload()
        payload['extra_key'] = 'should not be here'
        client.chat_completion.return_value = _ok_response(payload)  # type: ignore[attr-defined]

        with pytest.raises(SummarizationError, match='schema validation'):
            await summarize_thread(_thread(), client)

    async def test_raises_on_invalid_side_enum(self) -> None:
        client = _make_client()
        payload = _valid_payload()
        payload['key_arguments'] = [
            {'side': 'pro', 'text': 'bad enum', 'votes': 1}
        ]
        client.chat_completion.return_value = _ok_response(payload)  # type: ignore[attr-defined]

        with pytest.raises(SummarizationError, match='schema validation'):
            await summarize_thread(_thread(), client)

    async def test_raises_on_extra_key_in_argument(self) -> None:
        """Sub-objects also forbid extra keys."""
        client = _make_client()
        payload = _valid_payload()
        payload['key_arguments'] = [
            {
                'side': 'for',
                'text': 'ok',
                'votes': 1,
                'rogue': 'nope',
            }
        ]
        client.chat_completion.return_value = _ok_response(payload)  # type: ignore[attr-defined]

        with pytest.raises(SummarizationError, match='schema validation'):
            await summarize_thread(_thread(), client)
