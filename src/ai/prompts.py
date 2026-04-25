"""Summarization prompts for DeepSeek."""

from pathlib import Path

from ..fetchers.base import Comment, Thread

_PROMPT_FILE = Path(__file__).parent.parent.parent / 'prompts' / 'summarize.md'
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding='utf-8')


def _flatten(comments: list[Comment]) -> list[Comment]:
    """Recursively flatten a comment tree."""
    out: list[Comment] = []
    for c in comments:
        out.append(c)
        out.extend(_flatten(c.replies))
    return out


def build_user_prompt(thread: Thread, max_comments: int = 200) -> str:
    """Format thread + top-N comments as user message."""
    flat = _flatten(thread.comments)
    flat.sort(key=lambda c: c.score, reverse=True)
    top = flat[:max_comments]

    lines = [
        f'Title: {thread.title}',
        f'Author: u/{thread.author or "[unknown]"}',
        f'Score: {thread.score} | Total comments: {thread.num_comments}',
    ]
    if thread.body:
        lines.append('')
        lines.append(f'Post body:\n{thread.body}')

    lines.append('')
    lines.append(
        f'--- Top {len(top)} of {len(flat)} comments '
        f'(sorted by score desc) ---'
    )
    for i, c in enumerate(top, 1):
        author = f'u/{c.author}' if c.author else 'u/[deleted]'
        lines.append(
            f'[{i} | depth={c.depth} | score={c.score}] {author}: {c.body}'
        )

    return '\n'.join(lines)
