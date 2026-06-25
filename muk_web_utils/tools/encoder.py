from __future__ import annotations

import datetime
import json

from odoo import fields, models
from odoo.tools import config
from odoo.tools.json import json_default


def ustr_sql(value: bytes) -> str:
    """Decode bytes to text, replacing errors and NUL bytes."""
    return str(value, errors='replace').replace('\x00', '�')


def limit_text_size(text: str, default: int = 25000) -> str:
    """Truncate text to the configured logging content limit."""
    value = config.get('muk_logging_content_limit')
    limit = int(value) if value is not None else default
    if limit and len(text) > limit:
        return f'{text[:limit]}\n\n...'
    return text


class RequestEncoder(json.JSONEncoder):
    """Serialize dates, bytes and recordsets for request logging."""

    def default(self, obj) -> object:
        if isinstance(obj, datetime.date):
            if isinstance(obj, datetime.datetime):
                return fields.Datetime.to_string(obj)
            return fields.Date.to_string(obj)
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode()
        if isinstance(obj, models.BaseModel):
            return [(record.id, record.display_name) for record in obj]
        return str(obj)


class ResponseEncoder(json.JSONEncoder):
    """Serialize bytes and Odoo values for response logging."""

    def default(self, obj) -> object:
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode()
        return json_default(obj)


class RecordEncoder(ResponseEncoder):
    """Extend the response encoder to render recordsets as id/name pairs."""

    def default(self, obj) -> object:
        if isinstance(obj, models.BaseModel):
            return [(record.id, record.display_name) for record in obj]
        return ResponseEncoder.default(self, obj)


class LogEncoder(json.JSONEncoder):
    """Encode JSON while truncating overly long string values."""

    def iterencode(self, o, _one_shot: bool = False):
        markers = {} if self.check_circular else None
        if self.indent is None or isinstance(self.indent, str):
            indent = self.indent
        else:
            indent = ' ' * int(self.indent)

        def limit_str(o) -> str:
            text = json.encoder.encode_basestring(o)
            value = config.get('muk_logging_attribute_limit')
            limit = int(value) if value is not None else 150
            return f'{text[:limit]}...' if limit and len(text) > limit else text

        if _one_shot and json.encoder.c_make_encoder is not None and indent is None:
            encode = json.encoder.c_make_encoder(
                markers,
                self.default,
                limit_str,
                indent,
                self.key_separator,
                self.item_separator,
                self.sort_keys,
                self.skipkeys,
                self.allow_nan,
            )
        else:
            encode = json.encoder._make_iterencode(
                markers,
                self.default,
                limit_str,
                indent,
                float.__repr__,
                self.key_separator,
                self.item_separator,
                self.sort_keys,
                self.skipkeys,
                _one_shot,
            )
        return encode(o, 0)
