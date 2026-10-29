from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import SQL


def load_migration(version: str, name: str) -> object:
    """Load the migration script ``name`` of ``version`` as a module."""
    path = Path(__file__).parents[1] / 'migrations' / version / f'{name}.py'
    spec = spec_from_file_location(f'muk_ai_schedule_{name}', path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration(TransactionCase):
    """An upgrade from 1.x drops the views that still show the schedules."""

    def test_the_old_session_views_are_dropped(self):
        bases = ('search', 'list', 'form')
        views = self.env['ir.ui.view'].create(
            [
                {
                    'name': f'old.{kind}',
                    'model': 'muk_ai.session',
                    'inherit_id': self.env.ref(f'muk_ai.view_ai_session_{kind}').id,
                    'arch': '<xpath expr="/*" position="inside">'
                    '<field name="user_id"/></xpath>',
                }
                for kind in bases
            ]
        )
        self.env['ir.model.data'].create(
            [
                {
                    'module': 'muk_ai_schedule',
                    'name': f'view_ai_session_{kind}_inherit_schedule',
                    'model': 'ir.ui.view',
                    'res_id': view.id,
                }
                for kind, view in zip(bases, views)
            ]
        )
        self.env.cr.execute(
            SQL(
                "UPDATE ir_ui_view SET arch_db = replace(arch_db::text, 'user_id', "
                "'schedule_id')::jsonb WHERE id IN %s",
                tuple(views.ids),
            )
        )
        self.env.invalidate_all()
        for kind in bases:
            with self.assertRaises(ValidationError):
                self.env.ref(f'muk_ai.view_ai_session_{kind}')._check_xml()
        load_migration('19.0.2.0.4', 'post-migrate').migrate(self.env.cr, '19.0.2.0.1')
        self.assertFalse(views.exists())
        for kind in bases:
            self.env.ref(f'muk_ai.view_ai_session_{kind}')._check_xml()
