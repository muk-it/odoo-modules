from __future__ import annotations

import json
import re

TITLE_MAX_WORDS = 6
TITLE_MAX_CHARS = 60
ERROR_MAX_CHARS = 200
LOG_FIELD_MAX_CHARS = 8192


def is_output(item) -> bool:
    """Return whether a conversation item is a tool output."""
    return isinstance(item, dict) and item.get('type') == 'function_call_output'


def open_call_ids(conversation: list) -> list[str]:
    """Return the ids of the tool calls the conversation holds no output for."""
    answered = {item.get('call_id') for item in conversation if is_output(item)}
    return [
        item['call_id']
        for item in conversation
        if isinstance(item, dict)
        and item.get('type') == 'function_call'
        and item.get('call_id')
        and item['call_id'] not in answered
    ]


def order_outputs(outputs: list) -> list:
    """Return round outputs with every tool output first, user entries after."""
    return sorted(outputs, key=lambda item: not is_output(item))


def is_counted_user_entry(item) -> bool:
    """Return whether the item is a user entry backed by a user_message event.

    Answer-carried, tool-produced vision and system notice entries have no
    such event.
    """
    return (
        isinstance(item, dict)
        and item.get('role') == 'user'
        and not item.get('_answer_entry')
        and not item.get('_vision_entry')
        and not item.get('_notice_entry')
    )


def count_messages(items: list) -> int:
    """Count the user and assistant messages among conversation items."""
    return sum(
        1
        for item in items
        if isinstance(item, dict) and item.get('role') in ('user', 'assistant')
    )


def estimate_tokens(entry) -> int:
    """Roughly estimate the token count of a conversation entry."""
    if not isinstance(entry, dict):
        return 0
    content = entry.get('content')
    if isinstance(content, str):
        texts = [content]
    else:
        texts = [
            block.get('text') or block.get('arguments') or ''
            for block in content or []
            if isinstance(block, dict)
        ]
    texts += [entry.get(key) for key in ('arguments', 'output', 'text')]
    return sum(len(text) // 4 for text in texts if isinstance(text, str))


def split_for_compact(conversation: list, keep_budget: int) -> tuple[list, list]:
    """Split the conversation into a prefix to summarize and a tail to keep.

    The tail holds the latest entries within ``keep_budget`` tokens and starts
    at a user entry; failing that, it starts at the last user entry.
    """
    tail, used = [], 0
    for entry in reversed(conversation):
        estimate = estimate_tokens(entry)
        if used + estimate > keep_budget and tail:
            break
        tail.insert(0, entry)
        used += estimate
    while tail and not (isinstance(tail[0], dict) and tail[0].get('role') == 'user'):
        tail.pop(0)
    if tail and len(tail) < len(conversation):
        return conversation[: -len(tail)], tail
    users = [
        index
        for index, entry in enumerate(conversation)
        if isinstance(entry, dict) and entry.get('role') == 'user'
    ]
    split = users[-1] if users else len(conversation)
    return conversation[:split], conversation[split:]


def chat_title(raw: str | None) -> str:
    """Derive a short chat title from the first sentence of a message."""
    text = re.sub(r'\s+', ' ', raw or '').strip()
    text = re.split(r'[.!?\n;:]', text, maxsplit=1)[0].strip()
    text = text.strip('"\'`\u201c\u201d\u2018\u2019,. -').strip()
    text = ' '.join(text.split(' ')[:TITLE_MAX_WORDS])
    return text[:TITLE_MAX_CHARS].rstrip(' ,;:-')


def short_error_reason(raw: str) -> str:
    """Extract a short, single-line reason from a raw error string."""
    text = raw.strip()[:8192]
    if match := re.search(r'\{.*\}', text, flags=re.DOTALL):
        try:
            data = json.loads(match.group(0))
        except ValueError:
            data = None
        if isinstance(data, dict):
            error = data.get('error')
            if isinstance(error, dict) and error.get('message'):
                text = error['message']
            elif data.get('message'):
                text = data['message']
    text = ' '.join(text.split())
    if len(text) > ERROR_MAX_CHARS:
        return text[: ERROR_MAX_CHARS - 3] + '...'
    return text


def cap_log_payload(payload: dict) -> dict:
    """Return a copy of an event payload with its large fields cut for the bus."""
    capped = dict(payload)
    for key in ('result', 'arguments'):
        if (value := capped.get(key)) is None:
            continue
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(text) > LOG_FIELD_MAX_CHARS:
            capped[key] = text[:LOG_FIELD_MAX_CHARS] + '...'
            capped['truncated'] = True
    return capped
