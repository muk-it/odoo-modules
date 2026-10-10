from __future__ import annotations

import base64
from typing import Any

from odoo.addons.muk_mcp.tools.protocol import make_media_content, make_text_content

TEXT_MIMETYPE_PREFIXES = ('text/',)
TEXT_MIMETYPE_EXACT = frozenset(
    {
        'application/json',
        'application/xml',
        'application/yaml',
        'application/x-yaml',
        'application/javascript',
        'application/ecmascript',
        'application/x-sh',
        'application/x-python',
        'image/svg+xml',
    },
)


def normalize_mimetype(mimetype: str | None) -> str:
    """Return the MIME type lowercased and stripped of any parameters."""
    if not mimetype:
        return ''
    return mimetype.lower().split(';', 1)[0].strip()


def is_textual_mimetype(normalized: str) -> bool:
    """Return whether a normalized MIME type denotes textual content."""
    if normalized in TEXT_MIMETYPE_EXACT:
        return True
    return any(normalized.startswith(prefix) for prefix in TEXT_MIMETYPE_PREFIXES)


def is_inline_mimetype(normalized: str) -> bool:
    """Return whether a normalized MIME type travels as its own content block."""
    return is_textual_mimetype(normalized) or normalized.startswith(
        ('image/', 'audio/')
    )


def make_resource_entry(
    uri: str, mime_type: str | None, raw: bytes, name: str | None = None
) -> dict[str, Any]:
    """Build a resource entry: UTF-8 ``text`` for textual types, else a base64 ``blob``."""
    normalized = normalize_mimetype(mime_type)
    entry = {'uri': uri}
    if normalized:
        entry['mimeType'] = normalized
    if name:
        entry['name'] = name
    if is_textual_mimetype(normalized):
        try:
            return {**entry, 'text': raw.decode('utf-8')}
        except UnicodeDecodeError:
            pass
    return {**entry, 'blob': base64.b64encode(raw).decode('ascii')}


def make_content_for_bytes(
    uri: str,
    mime_type: str | None,
    *,
    raw_bytes: bytes,
    name: str | None = None,
) -> dict[str, Any]:
    """Build the MCP content block best matching the MIME type of given bytes."""
    entry = make_resource_entry(uri, mime_type, raw_bytes, name)
    if 'text' in entry:
        return make_text_content(entry['text'])
    if (mime_type := entry.get('mimeType', '')).startswith(('image/', 'audio/')):
        return make_media_content(entry['blob'], mime_type)
    return {'type': 'resource', 'resource': entry}
