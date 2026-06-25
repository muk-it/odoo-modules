from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def attachment_uri(attachment_id: int) -> str:
    """Build the ``odoo://`` URI for an attachment."""
    return f'odoo://attachment/{attachment_id}'


def record_field_uri(model: str, record_id: int, field: str) -> str:
    """Build the ``odoo://`` URI for a single record field."""
    return f'odoo://record/{model}/{record_id}/{field}'


def parse_uri(uri: str | None) -> tuple[str, dict[str, Any]] | None:
    """Parse an ``odoo://`` URI into a ``(kind, params)`` pair.

    :return: ``('attachment', ...)`` or ``('record_field', ...)``, or ``None``
        if the URI is missing, not an ``odoo`` scheme, or malformed.
    """
    if uri and (parsed := urlparse(uri)).scheme == 'odoo':
        parts = [p for p in parsed.path.split('/') if p]
        if parsed.netloc == 'attachment' and len(parts) == 1:
            try:
                return (
                    'attachment',
                    {'attachment_id': int(parts[0])},
                )
            except ValueError:
                return None
        if parsed.netloc == 'record' and len(parts) == 3:
            try:
                return (
                    'record_field',
                    {
                        'model': parts[0],
                        'record_id': int(parts[1]),
                        'field': parts[2],
                    },
                )
            except ValueError:
                return None
    return None
