"""Telegram HTML formatter."""

from html import escape
from typing import Any

from ..fetchers.base import Thread

TELEGRAM_MESSAGE_LIMIT = 4000
TRUNCATE_SUFFIX = '\n\n<i>...(обрезано)</i>'

_SIDE_LABELS = {
    'for': 'За',
    'against': 'Против',
    'neutral': 'Нейтрально',
}


def _h(text: str) -> str:
    """Escape HTML special chars."""
    return escape(text, quote=False)


def _format_arguments(arguments: list[dict[str, Any]]) -> str:
    """Render key arguments block."""
    if not arguments:
        return ''
    lines = ['<b>💬 Аргументы</b>']
    for arg in arguments:
        side = _SIDE_LABELS.get(arg['side'], arg['side'])
        text = _h(arg['text'])
        votes = arg['votes']
        lines.append(f'• <b>{side}</b> ({votes}): {text}')
    return '\n'.join(lines)


def _format_list(title: str, items: list[str]) -> str:
    """Render bullet list block."""
    if not items:
        return ''
    lines = [f'<b>{title}</b>']
    lines.extend(f'• {_h(item)}' for item in items)
    return '\n'.join(lines)


def _format_quotes(quotes: list[dict[str, Any]]) -> str:
    """Render notable quotes block."""
    if not quotes:
        return ''
    lines = ['<b>💎 Цитаты</b>']
    for q in quotes:
        author = _h(q['author'])
        quote = _h(q['quote'])
        score = q['score']
        lines.append(f'<blockquote>{quote}\n— {author} ({score})</blockquote>')
    return '\n'.join(lines)


def _truncate(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> str:
    """Trim text to fit Telegram limit."""
    if len(text) <= limit:
        return text
    cutoff = limit - len(TRUNCATE_SUFFIX)
    return text[:cutoff].rstrip() + TRUNCATE_SUFFIX


def format_summary(summary: dict[str, Any], thread: Thread) -> str:
    """Render summary as Telegram HTML."""
    blocks: list[str] = []

    title = _h(thread.title)
    blocks.append(f'<b>📰 {title}</b>')

    tldr = _h(summary['tldr'])
    blocks.append(f'<b>🎯 TL;DR</b>\n{tldr}')

    thesis = _h(summary['post_thesis'])
    blocks.append(f'<b>📝 Тезис поста</b>\n{thesis}')

    args_block = _format_arguments(summary['key_arguments'])
    if args_block:
        blocks.append(args_block)

    consensus_block = _format_list('✅ Консенсус', summary['consensus'])
    if consensus_block:
        blocks.append(consensus_block)

    controversial_block = _format_list(
        '⚡ Спорные точки', summary['controversial']
    )
    if controversial_block:
        blocks.append(controversial_block)

    quotes_block = _format_quotes(summary['notable_quotes'])
    if quotes_block:
        blocks.append(quotes_block)

    text = '\n\n'.join(blocks)
    return _truncate(text)
