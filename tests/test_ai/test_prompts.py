"""Prompt builder tests."""

from datetime import UTC, datetime

from src.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from src.fetchers.base import Comment, Thread


def _make_thread(
    *,
    body: str = '',
    comments: list[Comment] | None = None,
    num_comments: int = 0,
) -> Thread:
    return Thread(
        id='abc',
        platform='reddit',
        title='Test thread title',
        body=body,
        author='op',
        score=42,
        num_comments=num_comments,
        created_utc=datetime(2026, 4, 1, tzinfo=UTC),
        url='https://reddit.com/r/x/comments/abc/',
        comments=comments or [],
    )


class TestSystemPrompt:
    """SYSTEM_PROMPT contract."""

    def test_mentions_all_required_sections(self) -> None:
        for field in [
            'tldr',
            'post_thesis',
            'key_arguments',
            'consensus',
            'controversial',
            'notable_quotes',
        ]:
            assert field in SYSTEM_PROMPT, f'missing field: {field}'

    def test_instructs_to_weight_by_score(self) -> None:
        assert 'score' in SYSTEM_PROMPT.lower()
        assert (
            'weight' in SYSTEM_PROMPT.lower()
            or 'weighting' in SYSTEM_PROMPT.lower()
        )

    def test_requests_strict_json(self) -> None:
        assert 'json' in SYSTEM_PROMPT.lower()
        assert 'no markdown' in SYSTEM_PROMPT.lower() or (
            'no prose' in SYSTEM_PROMPT.lower()
        )

    def test_requires_russian_output(self) -> None:
        assert 'Russian' in SYSTEM_PROMPT
        assert 'verbatim' in SYSTEM_PROMPT.lower()

    def test_declares_strict_six_key_contract(self) -> None:
        text = SYSTEM_PROMPT.lower()
        assert 'exactly these six top-level keys' in text
        assert 'do not add, omit, or rename keys' in text

    def test_declares_strict_side_enum(self) -> None:
        text = SYSTEM_PROMPT
        assert (
            '"side" must be exactly one of' in text.lower()
            or 'side must be exactly one of' in text.lower()
        )

    def test_allows_empty_consensus_and_controversial(self) -> None:
        text = SYSTEM_PROMPT.lower()
        assert '0-4' in text
        assert 'do not invent filler' in text

    def test_declares_votes_provenance(self) -> None:
        text = SYSTEM_PROMPT.lower()
        assert 'votes' in text
        assert 'exact score' in text
        assert (
            'do not sum, average, or estimate' in text
            or 'do not sum, average or estimate' in text
        )

    def test_anti_hallucination_clause_present(self) -> None:
        text = SYSTEM_PROMPT.lower()
        assert 'anti-hallucination' in text
        assert 'do not invent' in text

    def test_anti_overclaim_clause_present(self) -> None:
        text = SYSTEM_PROMPT.lower()
        assert 'anti-overclaim' in text
        assert 'unseen' in text

    def test_anti_injection_clause_present(self) -> None:
        text = SYSTEM_PROMPT.lower()
        assert 'input boundary' in text
        assert 'not as instructions' in text


class TestBuildUserPromptHeader:
    """Header section content."""

    def test_includes_title_author_score(self) -> None:
        thread = _make_thread()
        prompt = build_user_prompt(thread)
        assert 'Title: Test thread title' in prompt
        assert 'Author: u/op' in prompt
        assert 'Score: 42' in prompt
        assert 'Total comments: 0' in prompt

    def test_omits_post_body_when_empty(self) -> None:
        thread = _make_thread(body='')
        prompt = build_user_prompt(thread)
        assert 'Post body' not in prompt

    def test_includes_post_body_when_present(self) -> None:
        thread = _make_thread(body='Original post content here.')
        prompt = build_user_prompt(thread)
        assert 'Post body:' in prompt
        assert 'Original post content here.' in prompt

    def test_handles_missing_author(self) -> None:
        thread = Thread(
            id='abc',
            platform='reddit',
            title='t',
            url='https://reddit.com/x',
            author=None,
        )
        prompt = build_user_prompt(thread)
        assert 'u/[unknown]' in prompt


class TestBuildUserPromptComments:
    """Comment formatting and sorting."""

    def test_sorts_by_score_descending(self) -> None:
        comments = [
            Comment(id='c1', body='low', author='a', score=5, depth=0),
            Comment(id='c2', body='high', author='b', score=100, depth=0),
            Comment(id='c3', body='mid', author='c', score=20, depth=0),
        ]
        thread = _make_thread(comments=comments, num_comments=3)
        prompt = build_user_prompt(thread)

        idx_high = prompt.index('high')
        idx_mid = prompt.index('mid')
        idx_low = prompt.index('low')
        assert idx_high < idx_mid < idx_low

    def test_flattens_nested_replies(self) -> None:
        deep = Comment(
            id='c1',
            body='top',
            author='a',
            score=10,
            depth=0,
            replies=[
                Comment(
                    id='c2',
                    body='reply',
                    author='b',
                    score=5,
                    depth=1,
                    replies=[
                        Comment(
                            id='c3',
                            body='deep_reply',
                            author='c',
                            score=3,
                            depth=2,
                        )
                    ],
                )
            ],
        )
        thread = _make_thread(comments=[deep], num_comments=3)
        prompt = build_user_prompt(thread)
        assert 'top' in prompt
        assert 'reply' in prompt
        assert 'deep_reply' in prompt

    def test_respects_max_comments_limit(self) -> None:
        comments = [
            Comment(id=f'c{i}', body=f'b{i}', author='a', score=i, depth=0)
            for i in range(10)
        ]
        thread = _make_thread(comments=comments, num_comments=10)
        prompt = build_user_prompt(thread, max_comments=3)

        # Top-3 by score are b9, b8, b7
        assert 'b9' in prompt
        assert 'b8' in prompt
        assert 'b7' in prompt
        # b0..b6 must NOT appear
        for excluded in range(7):
            assert f'b{excluded}' not in prompt

    def test_emits_depth_and_score_metadata(self) -> None:
        comments = [
            Comment(id='c1', body='hello', author='a', score=99, depth=2),
        ]
        thread = _make_thread(comments=comments, num_comments=1)
        prompt = build_user_prompt(thread)
        assert 'depth=2' in prompt
        assert 'score=99' in prompt

    def test_handles_deleted_author_label(self) -> None:
        comments = [
            Comment(id='c1', body='x', author=None, score=1, depth=0),
        ]
        thread = _make_thread(comments=comments, num_comments=1)
        prompt = build_user_prompt(thread)
        assert 'u/[deleted]' in prompt

    def test_summary_line_reports_top_and_total(self) -> None:
        comments = [
            Comment(id=f'c{i}', body=f'b{i}', author='a', score=i, depth=0)
            for i in range(5)
        ]
        thread = _make_thread(comments=comments, num_comments=5)
        prompt = build_user_prompt(thread, max_comments=2)
        assert 'Top 2 of 5' in prompt
