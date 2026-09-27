from lxml import etree

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestTreeListView(TransactionCase):
    """Register and validate treelist views."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_create_valid_view(self):
        view = self.env['ir.ui.view'].create(
            {
                'name': 'partner treelist',
                'model': 'res.partner',
                'type': 'treelist',
                'arch': '<treelist editable="bottom"><field name="name"/></treelist>',
            }
        )
        result = self.env['res.partner'].get_views([(view.id, 'treelist')])
        arch = etree.fromstring(result['views']['treelist']['arch'])
        self.assertEqual(arch.tag, 'treelist')
        self.assertIn('name', result['models']['res.partner']['fields'])

    def test_invalid_parent_field(self):
        with (
            mute_logger('odoo.addons.base.models.ir_ui_view'),
            self.assertRaises(ValidationError),
        ):
            self.env['ir.ui.view'].create(
                {
                    'name': 'partner treelist',
                    'model': 'res.partner',
                    'type': 'treelist',
                    'arch': '<treelist parent_field="country_id"><field name="name"/></treelist>',
                }
            )

    def test_invalid_child_tag(self):
        with (
            mute_logger('odoo.addons.base.models.ir_ui_view'),
            self.assertRaises(ValidationError),
        ):
            self.env['ir.ui.view'].create(
                {
                    'name': 'partner treelist',
                    'model': 'res.partner',
                    'type': 'treelist',
                    'arch': '<treelist><field name="name"/><div/></treelist>',
                }
            )

    def test_missing_fields_are_column_invisible(self):
        view = self.env['ir.ui.view'].create(
            {
                'name': 'partner treelist',
                'model': 'res.partner',
                'type': 'treelist',
                'arch': '<treelist><field name="name" readonly="is_company"/></treelist>',
            }
        )
        result = self.env['res.partner'].get_views([(view.id, 'treelist')])
        arch = etree.fromstring(result['views']['treelist']['arch'])
        added = arch.xpath('//field[@name="is_company"]')
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].get('column_invisible'), 'True')
        self.assertIsNone(added[0].get('invisible'))

    def test_action_opens_a_treelist_view(self):
        action = self.env['ir.actions.act_window'].create(
            {
                'name': 'Partners',
                'res_model': 'res.partner',
                'view_mode': 'list,form',
                'view_ids': [Command.create({'view_mode': 'treelist'})],
            }
        )
        self.assertEqual(
            [mode for _view, mode in action.views], ['treelist', 'list', 'form']
        )
