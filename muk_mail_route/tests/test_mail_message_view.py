from __future__ import annotations

from lxml import etree

from odoo.tests import TransactionCase, new_test_user


class TestFailedListViewCache(TransactionCase):
    """Test that the failed-list view cache respects user-dependent buttons."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a routing rule, a plain user and a manager."""
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

    def test_non_manager_gets_no_routing_buttons(self):
        arch = (
            self.env['mail.message']
            .with_user(self.user_plain)
            .get_view(self.view.id, 'list')['arch']
        )
        self.assertNotIn('default_configuration_id', arch)
        self.assertNotIn('Cache Partner', arch)

    def test_one_button_is_injected_per_configuration(self):
        second = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Cache Partner Two',
                'model_id': self.model_res_partner.id,
                'route_type': 'search',
            }
        )
        arch = etree.fromstring(
            self.env['mail.message']
            .with_user(self.user_manager)
            .get_view(self.view.id, 'list')['arch']
        )
        contexts = [
            node.get('context')
            for node in arch.xpath(".//button[@name='action_route_message']")
            if node.get('context')
        ]
        for configuration in self.configuration + second:
            self.assertEqual(
                sum(str(configuration.id) in context for context in contexts),
                2,
            )

    def test_configurations_of_unreadable_models_are_skipped(self):
        self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Blacklist Rule',
                'model_id': self.env.ref('mail.model_mail_blacklist').id,
                'route_type': 'search',
            }
        )
        arch = (
            self.env['mail.message']
            .with_user(self.user_manager)
            .get_view(self.view.id, 'list')['arch']
        )
        self.assertIn('Cache Partner', arch)
        self.assertNotIn('Blacklist Rule', arch)
