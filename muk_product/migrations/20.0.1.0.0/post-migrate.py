from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str | None) -> None:
    """Move the fixed variant prices into the stored core sales price."""
    cr.execute(
        """
        UPDATE product_product
           SET lst_price = fixed_price
         WHERE fixed_price != 0
        """
    )
