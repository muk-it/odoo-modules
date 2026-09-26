from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

from odoo.addons.muk_contacts_vcard import _setup_module


def migrate(cr: Cursor, version: str | None) -> None:
    """Split unnamed partners and restore upgrade-logged mobile numbers."""
    _setup_module(api.Environment(cr, SUPERUSER_ID, {}))
