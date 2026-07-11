from __future__ import annotations

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestFailedListViewCache(TransactionCase):
    """Test that the failed-list view cache respects user-dependent buttons."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.model_res_partner = cls.env.ref('base.model_res_partner')
        cls.view = cls.env.ref('muk_mail_route.view_mail_message_failed_list')

        cls.configuration = cls.env['muk_mail_route.configuration'].create(
            {
                'name': 'Cache Partner',
                'model_id': cls.model_res_partner.id,
                'route_type': 'new',
            }
        )

        cls.user_plain = new_test_user(cls.env, 'plain_user', groups='base.group_user')
        cls.user_manager = new_test_user(
            cls.env,
            'mgr_user',
            groups='base.group_user,base.group_erp_manager',
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_view_cache_not_seeded_by_non_manager(self):
        self.env['mail.message'].with_user(self.user_plain).get_view(
            self.view.id, 'list'
        )
        arch = (
            self.env['mail.message']
            .with_user(self.user_manager)
            .get_view(self.view.id, 'list')['arch']
        )
        self.assertIn('default_configuration_id', arch)
