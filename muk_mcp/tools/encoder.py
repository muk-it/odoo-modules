import datetime
import json

from odoo import fields, models
from odoo.tools import config
from odoo.tools.date_utils import json_default


def limit_text_size(text, default=25000):
    value = config.get('muk_logging_content_limit')
    limit = int(value) if value is not None else default
    if limit and len(text) > limit:
        return '{}\n\n...'.format(text[:limit])
    return text


class RequestEncoder(json.JSONEncoder):
    def default(self, obj):
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
    def default(self, obj):
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode()
        return json_default(obj)


class RecordEncoder(ResponseEncoder):
    def default(self, obj):
        if isinstance(obj, models.BaseModel):
            return [
                (record.id, record.display_name)
                for record in obj
            ]
        return ResponseEncoder.default(self, obj)


class LogEncoder(json.JSONEncoder):
    def iterencode(self, o, _one_shot=False):
        markers = {} if self.check_circular else None
        if self.indent is None or isinstance(self.indent, str):
            indent = self.indent
        else:
            indent = ' ' * int(self.indent)

        def limit_str(o):
            text = json.encoder.encode_basestring(o)
            value = config.get('muk_logging_attribute_limit')
            limit = int(value) if value is not None else 150
            return (
                '{}...'.format(text[:limit])
                if limit and len(text) > limit else text
            )

        if (
            _one_shot
            and json.encoder.c_make_encoder is not None
            and indent is None
        ):
            _iterencode = json.encoder.c_make_encoder(
                markers, self.default, limit_str, indent,
                self.key_separator, self.item_separator, self.sort_keys,
                self.skipkeys, self.allow_nan,
            )
        else:
            _iterencode = json.encoder._make_iterencode(
                markers, self.default, limit_str, indent, float.__repr__,
                self.key_separator, self.item_separator, self.sort_keys,
                self.skipkeys, _one_shot,
            )
        return _iterencode(o, 0)


def encode_request(arguments):
    if arguments is None:
        return None
    return limit_text_size(json.dumps(
        arguments, indent=4, cls=LogEncoder, default=str,
    ))


def encode_response(result):
    if result is None:
        return None
    return limit_text_size(json.dumps(
        result, indent=4, cls=LogEncoder, default=str,
    ))
