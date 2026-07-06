from __future__ import annotations

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestEeInitContextAccess(TransactionCase):
    """Test access enforcement of the EE init context enrichment."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env,
            login='ee_ctx_user_a',
            groups='base.group_user',
        )
        cls.user_b = new_test_user(
            cls.env,
            login='ee_ctx_user_b',
            groups='base.group_user',
        )
        cls.session_a = (
            cls.env['muk_ai.session'].with_user(cls.user_a).create({'name': 'SECRET-A'})
        )
        cls.session_b = (
            cls.env['muk_ai.session']
            .with_user(cls.user_b)
            .create({'name': 'Session B'})
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_no_cross_user_record_leak(self):
        self.session_b.with_user(self.user_b).set_view_context(
            {
                'kind': 'record',
                'model': 'muk_ai.session',
                'id': self.session_a.id,
            }
        )
        vc = self.session_b.view_context or {}
        self.assertNotIn(
            'SECRET-A',
            str(vc.get('ee_init_context') or ''),
            'Inaccessible record data must not leak into ee_init_context.',
        )
        self.assertNotIn(
            'ee_init_context',
            vc,
            'No EE context may be built for a record the user cannot read.',
        )

    def test_owner_record_context_allowed(self):
        self.session_b.with_user(self.user_b).set_view_context(
            {
                'kind': 'record',
                'model': 'muk_ai.session',
                'id': self.session_b.id,
            }
        )
        vc = self.session_b.view_context or {}
        self.assertEqual(vc.get('kind'), 'record')
        self.assertEqual(vc.get('id'), self.session_b.id)
