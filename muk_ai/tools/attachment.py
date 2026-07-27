from __future__ import annotations

import re

from odoo.addons.muk_mcp.tools.content import normalize_mimetype

# ----------------------------------------------------------
# Size Limits
# ----------------------------------------------------------

DEFAULT_TEXT_INLINE_LIMIT_KB = 256
DEFAULT_MAX_UPLOAD_BYTES = 128 * 1024 * 1024
ATTACHMENT_REF_MAX_BYTES = 4 * 1024 * 1024

# ----------------------------------------------------------
# Tool Vision Limits
# ----------------------------------------------------------

TOOL_VISION_MAX_IMAGES = 4
TOOL_VISION_MAX_BYTES = 4 * 1024 * 1024
TOOL_VISION_MAX_B64_CHARS = (TOOL_VISION_MAX_BYTES * 4) // 3 + 4

# ----------------------------------------------------------
# Allowed Mimetypes
# ----------------------------------------------------------

IMAGE_MIMETYPES = frozenset(
    {
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/gif',
    }
)
TEXT_MIMETYPES = frozenset(
    {
        'text/plain',
        'text/csv',
        'text/markdown',
    }
)
PDF_MIMETYPE = 'application/pdf'
ALLOWED_MIMETYPES = IMAGE_MIMETYPES | TEXT_MIMETYPES | {PDF_MIMETYPE}

# ----------------------------------------------------------
# Reference Patterns
# ----------------------------------------------------------

INLINE_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\(data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)\)'
)
ATTACHMENT_REF_RE = re.compile(r'^@attachment:(\d+)$')
URL_REF_RE = re.compile(r'^@url:(https://\S+)$')


def tool_file_payload(result) -> dict | None:
    """Return the file payload a tool result carries, or ``None``.

    File-producing tools (``export_records``, ``print_report``) answer with
    ``content_base64`` plus its filename and mimetype, the shape MCP clients
    consume. The chat client cannot, so the payload is stored instead.

    The mimetype is normalized because tools report a transport content type
    (``text/csv;charset=utf8``); stored verbatim it would fail the ingest
    allow-list and make the file unreadable to the model afterwards.
    """
    if not isinstance(result, dict):
        return None
    if not (data := result.get('content_base64')) or not isinstance(data, str):
        return None
    return {
        'filename': str(result.get('filename') or 'download'),
        'mimetype': normalize_mimetype(result.get('mimetype'))
        or 'application/octet-stream',
        'data_b64': data,
    }


def is_unmaterialized_attachment(block) -> bool:
    """Return whether a content block is an attachment placeholder lacking its data."""
    return (
        isinstance(block, dict)
        and block.get('type') == 'muk_ai_attachment'
        and 'data_b64' not in block
        and 'inline_text' not in block
    )
