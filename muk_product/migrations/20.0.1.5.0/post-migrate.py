from __future__ import annotations


def migrate(cr, version: str | None) -> None:
    """Move the fixed variant prices into the stored core sales price."""
    cr.execute(
        """
        UPDATE product_product
           SET lst_price = fixed_price
         WHERE fixed_price != 0
        """
    )
    cr.execute('ALTER TABLE product_product DROP COLUMN fixed_price')
