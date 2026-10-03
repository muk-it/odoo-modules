from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Keep the name of every address that is no company whole in its last name."""
    cr.execute(
        """
        UPDATE res_partner
           SET lastname = name,
               firstname = NULL,
               middlename = NULL,
               vcard_modified = (now() AT TIME ZONE 'UTC')
         WHERE type != 'contact'
           AND is_company IS NOT TRUE
           AND (firstname IS NOT NULL OR middlename IS NOT NULL)
        """
    )
