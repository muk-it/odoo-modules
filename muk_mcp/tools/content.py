from __future__ import annotations

import base64
from typing import Any

from odoo.addons.muk_mcp.tools.protocol import (
    make_audio_content,
    make_image_content,
    make_resource_content,
    make_text_content,
)

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


def make_content_for_bytes(
    uri: str,
    mime_type: str | None,
    *,
    raw_bytes: bytes,
    name: str | None = None,
) -> dict[str, Any]:
    """Build the MCP content block best matching the MIME type of given bytes."""
    normalized = normalize_mimetype(mime_type)
    if is_textual_mimetype(normalized):
        try:
            return make_text_content(raw_bytes.decode('utf-8'))
        except UnicodeDecodeError:
            pass
    blob = base64.b64encode(raw_bytes).decode('ascii')
    if normalized.startswith('image/'):
        return make_image_content(blob, normalized)
    if normalized.startswith('audio/'):
        return make_audio_content(blob, normalized)
    return make_resource_content(
        uri,
        mime_type=normalized or None,
        blob=blob,
        name=name,
    )
