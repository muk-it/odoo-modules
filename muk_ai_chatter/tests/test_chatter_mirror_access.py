from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_chatter')
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

    def test_session_survives_a_failing_mirror_post(self):
        partner = self.env['res.partner'].create({'name': 'Unpostable Target'})
        before = self._count_messages(partner.id)
        message = 'chatter is down'

        def fake(self_arg, *args, **kwargs):
            raise RuntimeError(message)

        with patch.object(
            type(partner),
            'message_post',
            autospec=True,
            side_effect=fake,
        ):
            session = self.env['muk_ai.session'].create(
                {
                    'name': 'Resilient Session',
                    'res_model': 'res.partner',
                    'res_id': partner.id,
                }
            )
        self.assertTrue(session.exists())
        self.assertEqual(self._count_messages(partner.id), before)
