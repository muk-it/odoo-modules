from odoo.tests import TransactionCase

from odoo.addons.bus.tests.common import BusCase, BusResult


class TestReloadViews(TransactionCase, BusCase):
    """Test that the reload-views server action broadcasts to internal users."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the records the tests run against."""
        super().setUpClass()
        cls.action = cls.env['ir.actions.server'].create(
            {
                'name': 'Test Reload Views',
                'model_id': cls.env.ref('base.model_res_partner_category').id,
                'state': 'refresh',
            }
        )
        cls.tag = cls.env['res.partner.category'].create({'name': 'Test Tag'})
        cls.internal_users = cls.env.ref('base.group_user')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_run_broadcasts_the_selected_records_and_view_types(self):
        for view_types, expected in [
            (False, []),
            ('list, kanban', ['list', 'kanban']),
            (' form ,, ', ['form']),
        ]:
            with self.subTest(view_types=view_types):
                self.action.refresh_view_types = view_types
                payload = {
                    'model': 'res.partner.category',
                    'view_types': expected,
                    'rec_ids': self.tag.ids,
                }
                with self.assertBus(
                    BusResult(self.internal_users, 'muk_web_refresh.reload', payload)
                ):
                    self.action.with_context(
                        active_model='res.partner.category', active_ids=self.tag.ids
                    ).run()

    def test_run_without_records_reloads_every_record(self):
        payload = {'model': 'res.partner.category', 'view_types': [], 'rec_ids': []}
        with self.assertBus(
            BusResult(self.internal_users, 'muk_web_refresh.reload', payload)
        ):
            self.action.run()

    def test_an_automation_rule_broadcasts_the_changed_record(self):
        self.env['base.automation'].create(
            {
                'name': 'Reload Tags',
                'model_id': self.env.ref('base.model_res_partner_category').id,
                'trigger': 'on_write',
                'action_server_ids': [(4, self.action.id)],
            }
        )
        payload = {
            'model': 'res.partner.category',
            'view_types': [],
            'rec_ids': self.tag.ids,
        }
        with self.assertBus(
            BusResult(self.internal_users, 'muk_web_refresh.reload', payload)
        ):
            self.tag.write({'name': 'Renamed Tag'})
