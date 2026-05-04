import re


DEFAULT_TEXT_INLINE_LIMIT_KB = 256
DEFAULT_MAX_UPLOAD_BYTES = 128 * 1024 * 1024
ATTACHMENT_REF_MAX_BYTES = 4 * 1024 * 1024

IMAGE_MIMETYPES = frozenset({
    'image/png', 'image/jpeg', 'image/webp', 'image/gif',
})
TEXT_MIMETYPES = frozenset({
    'text/plain', 'text/csv', 'text/markdown',
})
PDF_MIMETYPE = 'application/pdf'
ALLOWED_MIMETYPES = IMAGE_MIMETYPES | TEXT_MIMETYPES | {PDF_MIMETYPE}

INLINE_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\(data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)\)'
)
ATTACHMENT_REF_RE = re.compile(r'^@attachment:(\d+)$')
URL_REF_RE = re.compile(r'^@url:(https://\S+)$')


def is_unmaterialized_attachment(block):
    return (
        isinstance(block, dict)
        and block.get('type') == 'muk_ai_attachment'
        and 'data_b64' not in block
        and 'inline_text' not in block
    )
