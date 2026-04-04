import json

from odoo.tools import config


class LogEncoder(json.JSONEncoder):

    def iterencode(self, o, _one_shot=False):
        markers = {} if self.check_circular else None
        limit = int(config.get('mcp_logging_attribute_limit', 150))

        def limit_str(o):
            text = json.encoder.encode_basestring(o)
            if limit and len(text) > limit:
                return '{}...'.format(text[:limit])
            return text

        if (
            _one_shot
            and json.encoder.c_make_encoder is not None
            and self.indent is None
        ):
            _iterencode = json.encoder.c_make_encoder(
                markers, self.default, limit_str, self.indent,
                self.key_separator, self.item_separator, self.sort_keys,
                self.skipkeys, self.allow_nan,
            )
        else:
            _iterencode = json.encoder._make_iterencode(
                markers, self.default, limit_str, self.indent, json.dumps,
                self.key_separator, self.item_separator, self.sort_keys,
                self.skipkeys, _one_shot,
            )
        return _iterencode(o, 0)


def limit_text_size(text):
    limit = int(config.get('mcp_logging_content_limit', 25000))
    if limit and len(text) > limit:
        return '{}\n\n...'.format(text[:limit])
    return text


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
