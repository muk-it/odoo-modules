from __future__ import annotations

import base64
import email
import email.policy
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
        'application/javascript',
        'application/json',
        'application/sql',
        'application/toml',
        'application/x-sh',
        'application/x-yaml',
        'application/xml',
        'application/yaml',
        'message/rfc822',
    }
)
OFFICE_MIMETYPES = frozenset(
    {
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.oasis.opendocument.text',
        'application/vnd.oasis.opendocument.spreadsheet',
        'application/vnd.oasis.opendocument.presentation',
    }
)
PDF_MIMETYPE = 'application/pdf'

# ----------------------------------------------------------
# Reference Patterns
# ----------------------------------------------------------

INLINE_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\(data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)\)'
)
SCRIPT_RE = re.compile(r'<script\b.*?</script\s*>', re.IGNORECASE | re.DOTALL)
ATTACHMENT_REF_RE = re.compile(r'^@attachment:(\d+)$')
URL_REF_RE = re.compile(r'^@url:(https://\S+)$')


def email_parts(raw: bytes) -> tuple[str, str]:
    """Return the subject and sender lines of an email and its body, HTML first."""
    message = email.message_from_bytes(raw, policy=email.policy.default)
    body = message.get_body(('html', 'plain'))
    head = f'Subject: {message["subject"] or ""}\nFrom: {message["from"] or ""}'
    return head, body.get_content() if body else ''


def is_text(mimetype: str) -> bool:
    """Return whether a mimetype names a text format the model reads as text."""
    return (
        mimetype.startswith('text/')
        or mimetype in TEXT_MIMETYPES
        or mimetype.endswith(('+json', '+xml'))
    )


def looks_like_text(data_b64: str) -> bool:
    """Return whether a base64 payload is text: not empty, without NUL bytes."""
    try:
        head = base64.b64decode(data_b64 or '', validate=True)[:65536]
    except ValueError:
        return False
    return bool(head) and b'\0' not in head


def readable_text(raw: bytes, mimetype: str) -> str:
    """Return the text a model reads of a text attachment, scripts left out.

    An email reads as its subject, its sender and its body.
    """
    if mimetype == 'message/rfc822':
        head, body = email_parts(raw)
        return f'{head}\n\n{SCRIPT_RE.sub("", body)}'
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('cp1252', errors='replace')
    return SCRIPT_RE.sub('', text) if mimetype == 'text/html' else text


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
