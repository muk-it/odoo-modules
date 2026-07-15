from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.muk_contacts_vcard import _restore_mobile_from_upgrade_notes


def migrate(cr: Cursor, version: str) -> None:
    """Restore mobile numbers that the version upgrade logged as chatter notes."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    _restore_mobile_from_upgrade_notes(env)
