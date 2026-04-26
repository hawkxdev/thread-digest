"""Tests for twitterapi.io Pydantic models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.fetchers.x_models import XAuthor, XThreadResponse, XTweet

FIXTURE_PATH = (
    Path(__file__).parent.parent / 'fixtures' / 'x_thread_small.json'
)


@pytest.fixture
def fixture_data() -> dict:  # type: ignore[type-arg]
    """Load sterilized X thread fixture."""
    return json.loads(FIXTURE_PATH.read_text())


class TestXThreadResponse:
    """Top-level response envelope."""

    def test_validates_real_fixture(self, fixture_data: dict) -> None:  # type: ignore[type-arg]
        resp = XThreadResponse.model_validate(fixture_data)
        assert len(resp.tweets) == 12
        assert resp.has_next_page is True
        assert resp.next_cursor == 'STERILIZED_CURSOR_PAGE_2'
        assert resp.status == 'success'

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            XThreadResponse.model_validate({'tweets': [], 'status': 'unknown'})

    def test_minimal_response(self) -> None:
        resp = XThreadResponse.model_validate({'tweets': []})
        assert resp.tweets == []
        assert resp.has_next_page is False
        assert resp.next_cursor is None
        assert resp.status == 'success'

    def test_validates_last_page_response_with_null_cursor(self) -> None:
        """Real API returns next_cursor=null on last page."""
        resp = XThreadResponse.model_validate(
            {
                'tweets': [],
                'has_next_page': False,
                'next_cursor': None,
                'status': 'success',
                'msg': None,
            }
        )
        assert resp.next_cursor is None
        assert resp.msg is None
        assert resp.has_next_page is False

    def test_extra_fields_ignored(self) -> None:
        resp = XThreadResponse.model_validate(
            {
                'tweets': [],
                'status': 'success',
                'extra_unknown_field': 'whatever',
            }
        )
        assert resp.status == 'success'


class TestXTweet:
    """Tweet model with camelCase alias support."""

    def test_op_tweet_has_id_equal_to_conversation_id(
        self,
        fixture_data: dict,  # type: ignore[type-arg]
    ) -> None:
        resp = XThreadResponse.model_validate(fixture_data)
        op = resp.tweets[0]
        assert op.id == op.conversation_id
        assert op.is_reply is False
        assert op.in_reply_to_id is None

    def test_replies_have_parent(
        self,
        fixture_data: dict,  # type: ignore[type-arg]
    ) -> None:
        resp = XThreadResponse.model_validate(fixture_data)
        op_id = resp.tweets[0].id
        for reply in resp.tweets[1:]:
            assert reply.is_reply is True
            assert reply.in_reply_to_id is not None
            assert reply.conversation_id == op_id

    def test_camelcase_alias_round_trip(self) -> None:
        """API delivers camelCase, model accepts via alias."""
        raw = {
            'id': '1',
            'text': 't',
            'url': 'https://x.com/u/status/1',
            'createdAt': '2026-04-26',
            'isReply': False,
            'conversationId': '1',
            'likeCount': 5,
            'replyCount': 2,
            'viewCount': 100,
            'isLimitedReply': False,
            'author': {'id': 'u1', 'userName': 'alice'},
        }
        tweet = XTweet.model_validate(raw)
        assert tweet.like_count == 5
        assert tweet.is_reply is False
        assert tweet.author.user_name == 'alice'


class TestXAuthor:
    """Author subset model."""

    def test_minimal_author(self) -> None:
        author = XAuthor.model_validate({'id': 'u1', 'userName': 'bob'})
        assert author.id == 'u1'
        assert author.user_name == 'bob'
        assert author.name is None

    def test_extra_fields_ignored(self) -> None:
        author = XAuthor.model_validate(
            {
                'id': 'u1',
                'userName': 'bob',
                'followers': 9999,
                'isVerified': True,
                'profile_bio': {'description': 'x'},
            }
        )
        assert author.user_name == 'bob'
