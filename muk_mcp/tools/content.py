from __future__ import annotations

import base64

from odoo.addons.muk_mcp.tools.protocol import (
    make_audio_content,
    make_image_content,
    make_resource_content,
    make_text_content,
)

TEXT_MIMETYPES = frozenset({
    'application/json',
    'application/xml',
    'application/yaml',
    'application/x-yaml',
    'application/javascript',
    'application/ecmascript',
    'application/x-sh',
    'application/x-python',
    'image/svg+xml',
})


def normalize_mimetype(mimetype: str | None) -> str:
    """Return the MIME type lowercased and stripped of any parameters."""
    if not mimetype:
        return ''
    return mimetype.lower().split(';', 1)[0].strip()


def is_textual_mimetype(normalized: str) -> bool:
    """Return whether a normalized MIME type carries text."""
    return normalized.startswith('text/') or normalized in TEXT_MIMETYPES


def make_content_for_bytes(
    uri: str, mimetype: str | None, raw: bytes, name: str | None = None
) -> dict:
    """Return the MCP content block for a file: text, image, audio or a resource."""
    normalized = normalize_mimetype(mimetype)
    if is_textual_mimetype(normalized):
        try:
            return make_text_content(raw.decode('utf-8'))
        except UnicodeDecodeError:
            pass
    blob = base64.b64encode(raw).decode('ascii')
    if normalized.startswith('image/'):
        return make_image_content(blob, normalized)
    if normalized.startswith('audio/'):
        return make_audio_content(blob, normalized)
    return make_resource_content(uri, normalized or None, blob=blob, name=name)
