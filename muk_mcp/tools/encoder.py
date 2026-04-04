import json


class LogEncoder(json.JSONEncoder):
    def __init__(self, *args, attribute_limit=150, **kwargs):
        super().__init__(*args, **kwargs)
        self.attribute_limit = attribute_limit

    def iterencode(self, o, _one_shot=False):
        markers = {} if self.check_circular else None
        attribute_limit = self.attribute_limit

        def limit_str(o):
            text = json.encoder.encode_basestring(o)
            if attribute_limit and len(text) > attribute_limit:
                return '{}...'.format(text[:attribute_limit])
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


def _get_limits(env):
    get = env['ir.config_parameter'].sudo().get_param
    content_limit = int(get('muk_mcp.log_content_limit', 25000))
    attribute_limit = int(get('muk_mcp.log_attribute_limit', 150))
    return content_limit, attribute_limit


def _limit_text(text, limit):
    if limit and len(text) > limit:
        return '{}\n\n...'.format(text[:limit])
    return text


def encode_request(arguments, content_limit=25000, attribute_limit=150):
    if arguments is None:
        return None
    text = json.dumps(
        arguments, indent=4, cls=LogEncoder,
        attribute_limit=attribute_limit, default=str,
    )
    return _limit_text(text, content_limit)


def encode_response(result, content_limit=25000, attribute_limit=150):
    if result is None:
        return None
    text = json.dumps(
        result, indent=4, cls=LogEncoder,
        attribute_limit=attribute_limit, default=str,
    )
    return _limit_text(text, content_limit)
