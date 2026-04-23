DEFAULT_TEXT_INLINE_LIMIT_KB = 256
DEFAULT_MAX_UPLOAD_BYTES = 128 * 1024 * 1024

IMAGE_MIMETYPES = frozenset({
    'image/png', 'image/jpeg', 'image/webp', 'image/gif',
})
TEXT_MIMETYPES = frozenset({
    'text/plain', 'text/csv', 'text/markdown',
})
PDF_MIMETYPE = 'application/pdf'
ALLOWED_MIMETYPES = IMAGE_MIMETYPES | TEXT_MIMETYPES | {PDF_MIMETYPE}


def is_unmaterialized_attachment(block):
    return (
        isinstance(block, dict)
        and block.get('type') == 'muk_ai_attachment'
        and 'data_b64' not in block
        and 'inline_text' not in block
    )
