import json

from odoo.addons.muk_web_utils.tools.encoder import (
    LogEncoder,
    limit_text_size,
)


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
