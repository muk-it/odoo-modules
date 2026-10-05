from __future__ import annotations

import codecs
import csv
import io

PREVIEW_TYPES = {
    'table': (
        {'text/csv', 'text/tab-separated-values', 'application/csv'},
        ('.csv', '.tsv'),
    ),
    'mail': ({'message/rfc822'}, ('.eml',)),
    'outlook': ({'application/vnd.ms-outlook'}, ('.msg',)),
}

TEXT_MIMETYPES = (
    'application/sql',
    'application/x-sh',
    'application/x-yaml',
    'text/x-python',
    'text/x-rst',
    'text/x-yaml',
)

MAX_ROWS = 500
MAX_THUMBNAIL_ROWS = 20
MAX_COLUMNS = 50

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; img-src 'self' data:{remote}; "
    "style-src 'self' 'unsafe-inline'; font-src 'self'; sandbox;"
)


def preview_type(name: str | None, mimetype: str | None) -> str | None:
    """Return the preview type of a file by its mimetype or its extension."""
    name = (name or '').lower()
    for kind, (mimetypes, extensions) in PREVIEW_TYPES.items():
        if mimetype in mimetypes or name.endswith(extensions):
            return kind
    return None


def content_security_policy(allow_remote: bool) -> str:
    """Return the policy of a preview, allowing remote images on request."""
    return CONTENT_SECURITY_POLICY.format(
        remote=' https: http:' if allow_remote else ''
    )


def decode_text(raw: bytes, final: bool) -> str:
    """Decode UTF-8, Windows-1252 or Latin-1 text, whichever reads it.

    :param final: whether ``raw`` is the whole file and not only its start
    """
    try:
        return codecs.getincrementaldecoder('utf-8-sig')().decode(raw, final)
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode('cp1252')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def read_table(text: str, limit: int) -> tuple[list[list[str]], bool]:
    """Split delimited text into at most ``limit`` rows of capped width.

    :return: the rows and whether rows were left out
    """
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    rows = []
    for row in csv.reader(io.StringIO(text), dialect):
        if len(rows) == limit:
            return rows, True
        rows.append(row[:MAX_COLUMNS])
    return rows, False
