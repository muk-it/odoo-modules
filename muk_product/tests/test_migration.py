from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from odoo.tools.sql import column_exists

from odoo.addons.muk_product.tests.common import ProductCommon


def load_post_migrate() -> ModuleType:
    """Import the post-migration script, whose path is not a Python package."""
    path = (
        Path(__file__).resolve().parents[1]
        / 'migrations'
        / '20.0.1.5.0'
        / 'post-migrate.py'
    )
    spec = importlib.util.spec_from_file_location('muk_product_post_migrate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestProductMigration(ProductCommon):
    """Cover the migration of fixed variant prices into the core sales price."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_fixed_variant_prices_become_the_sales_price(self):
        template = self.create_variant_template('Lamp', ['Brass', 'Steel'])
        template.list_price = 100.0
        brass, steel = template.product_variant_ids
        self.env.flush_all()
        self.env.cr.execute(
            'ALTER TABLE product_product ADD COLUMN fixed_price numeric DEFAULT 0'
        )
        self.env.cr.execute(
            'UPDATE product_product SET fixed_price = 150 WHERE id = %s', [brass.id]
        )
        load_post_migrate().migrate(self.env.cr, '19.0.1.4.11')
        template.product_variant_ids.invalidate_recordset(['lst_price'])
        self.assertAlmostEqual(brass.lst_price, 150.0)
        self.assertAlmostEqual(steel.lst_price, 100.0)
        self.assertFalse(column_exists(self.env.cr, 'product_product', 'fixed_price'))
