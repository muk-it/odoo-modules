from __future__ import annotations

import json
from typing import Any

from odoo.addons.muk_web_utils.tools.encoder import (
    LogEncoder,
    limit_text_size,
)


def encode_log(value: Any) -> str | None:
    """Serialize a value to a size-limited JSON log string, or None if it is None."""
    if value is None:
        return None
    return limit_text_size(json.dumps(value, indent=4, cls=LogEncoder, default=str))
