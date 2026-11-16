from __future__ import annotations

from typing import Any

CLIENT_META = {'execute': 'client', 'client': 'browser'}

TARGET = {
    'ref': {
        'type': 'string',
        'description': 'Element ref from the latest browser_read_page snapshot.',
    },
    'element': {
        'type': 'string',
        'description': (
            'Short human description of the element, shown to the user when '
            'the action needs approval.'
        ),
    },
}

TAB = {
    'tab_id': {
        'type': 'integer',
        'description': (
            'Another tab of the "MuK AI" group to read, by its id from '
            "browser_tabs, without switching to it. By default the agent's tab."
        ),
    },
}

TRUSTED = {
    'trusted': {
        'type': 'boolean',
        'description': (
            'Send trusted input through the browser debugger. Use only when the '
            'same action without it had no effect.'
        ),
        'default': False,
    },
}


def schema(required: list[str] | None = None, **properties: Any) -> dict:
    """Return an object input schema with the given properties."""
    return {
        'type': 'object',
        'properties': properties,
        'required': required or [],
    }
