from __future__ import annotations

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestChatterMirrorAccess(TransactionCase):
    """Test the owner access gate on the linked-record chatter mirror."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up an internal user and a partner hidden by a record rule."""
        super().setUpClass()
        cls.attacker = new_test_user(
            cls.env,
            login='mirror_attacker',
            groups='base.group_user',
        )
        cls.target = cls.env['res.partner'].create({'name': 'Hidden Target'})
        cls.env['ir.rule'].create(
            {
                'name': 'Hide the mirror target from internal users',
                'model_id': cls.env['ir.model']._get_id('res.partner'),
                'domain_force': "[('id', '!=', %d)]" % cls.target.id,
                'groups': [(4, cls.env.ref('base.group_user').id)],
            }
        )

    def _count_messages(self, partner_id: int) -> int:
        """Count chatter messages posted on the given partner."""
        return self.env['mail.message'].search_count(
            [('model', '=', 'res.partner'), ('res_id', '=', partner_id)]
        )

    def test_no_mirror_on_inaccessible_record(self):
        self.assertFalse(self.target.with_user(self.attacker).has_access('read'))
        before = self._count_messages(self.target.id)
        self.env['muk_ai.session'].with_user(self.attacker).create(
            {
                'name': 'Mirror Probe',
                'res_model': 'res.partner',
                'res_id': self.target.id,
            }
        )
        self.assertEqual(self._count_messages(self.target.id), before)

    def test_mirror_on_accessible_record(self):
        partner = self.env['res.partner'].create({'name': 'Visible Target'})
        self.assertTrue(partner.with_user(self.attacker).has_access('read'))
        before = self._count_messages(partner.id)
        self.env['muk_ai.session'].with_user(self.attacker).create(
            {
                'name': 'Mirror Note',
                'res_model': 'res.partner',
                'res_id': partner.id,
            }
        )
        self.assertEqual(self._count_messages(partner.id), before + 1)
