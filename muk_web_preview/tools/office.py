from __future__ import annotations

import binascii
import datetime
from urllib.parse import urlencode

from odoo.api import Environment
from odoo.tools.misc import hash_sign, verify_hash_signed

TOKEN_SCOPE = 'muk_web_preview.office'
TOKEN_LIFETIME = datetime.timedelta(minutes=5)

VIEWER_URL = 'https://view.officeapps.live.com/op/embed.aspx'


def sign_attachment(env: Environment, attachment_id: int) -> str:
    """Return a short-lived token that grants access to one attachment."""
    return hash_sign(
        env(su=True), TOKEN_SCOPE, attachment_id, expiration=TOKEN_LIFETIME
    )


def verify_attachment(env: Environment, token: str) -> int | None:
    """Return the attachment id of a valid, unexpired token."""
    try:
        return verify_hash_signed(env(su=True), TOKEN_SCOPE, token)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def viewer_url(file_url: str) -> str:
    """Return the Office Online viewer URL that displays ``file_url``."""
    return f'{VIEWER_URL}?{urlencode({"src": file_url})}'
