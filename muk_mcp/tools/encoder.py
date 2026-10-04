from __future__ import annotations

import json
from typing import Any

from odoo.addons.muk_web_utils.tools.encoder import (
    LogEncoder,
    limit_text_size,
)


def encode_request(arguments: Any) -> str | None:
    """Serialize request arguments to a size-limited JSON log string, or None if empty."""
    if arguments is None:
        return None
    return limit_text_size(
        json.dumps(
            arguments,
            indent=4,
            cls=LogEncoder,
            default=str,
        ),
    )


def encode_response(result: Any) -> str | None:
    """Serialize a result to a size-limited JSON log string, or None if empty."""
    if result is None:
        return None
    return limit_text_size(
        json.dumps(
            result,
            indent=4,
            cls=LogEncoder,
            default=str,
        ),
    )
