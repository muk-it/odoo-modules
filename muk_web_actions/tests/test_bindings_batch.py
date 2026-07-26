from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBindingsBatch(TransactionCase):
    """Cover the batch execution values added to the action bindings."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.server_action = cls.env['ir.actions.server'].create(
            {
                'name': 'Batch Server Action',
                'model_id': cls.partner_model.id,
                'binding_model_id': cls.partner_model.id,
                'state': 'code',
                'code': 'pass',
                'execute_in_batch': True,
                'execution_batch_size': 25,
            }
        )
        cls.plain_action = cls.env['ir.actions.server'].create(
            {
                'name': 'Plain Server Action',
                'model_id': cls.partner_model.id,
                'binding_model_id': cls.partner_model.id,
                'state': 'code',
                'code': 'pass',
            }
        )
        cls.report = cls.env['ir.actions.report'].create(
            {
                'name': 'Batch Report',
                'model': 'res.partner',
                'binding_model_id': cls.partner_model.id,
                'report_name': 'muk_web_actions.batch_report',
                'report_type': 'qweb-pdf',
                'execute_in_batch': True,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_binding(self, key: str, action_id: int) -> dict:
        """Return the binding values of one action for ``res.partner``."""
        bindings = self.env['ir.actions.actions'].get_bindings('res.partner')
        return next(
            values for values in bindings.get(key, []) if values['id'] == action_id
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_server_action_binding_carries_its_batch_size(self):
        binding = self._get_binding('action', self.server_action.id)
        self.assertTrue(binding['execute_in_batch'])
        self.assertEqual(binding['execution_batch_size'], 25)

    def test_plain_server_action_binding_has_no_batch_values(self):
        binding = self._get_binding('action', self.plain_action.id)
        self.assertNotIn('execute_in_batch', binding)
        self.assertNotIn('execution_batch_size', binding)

    def test_report_binding_is_always_batched_one_by_one(self):
        binding = self._get_binding('report', self.report.id)
        self.assertTrue(binding['execute_in_batch'])
        self.assertEqual(binding['execution_batch_size'], 1)

    def test_enabling_the_flag_invalidates_the_bindings_cache(self):
        binding = self._get_binding('action', self.plain_action.id)
        self.assertNotIn('execute_in_batch', binding)
        self.plain_action.write({'execute_in_batch': True, 'execution_batch_size': 7})
        binding = self._get_binding('action', self.plain_action.id)
        self.assertTrue(binding['execute_in_batch'])
        self.assertEqual(binding['execution_batch_size'], 7)

    def test_disabling_the_flag_invalidates_the_bindings_cache(self):
        self.assertTrue(
            self._get_binding('action', self.server_action.id)['execute_in_batch']
        )
        self.server_action.write({'execute_in_batch': False})
        binding = self._get_binding('action', self.server_action.id)
        self.assertNotIn('execute_in_batch', binding)

    def test_creating_a_bound_action_invalidates_the_bindings_cache(self):
        before = self.env['ir.actions.actions'].get_bindings('res.partner')['action']
        created = self.env['ir.actions.server'].create(
            {
                'name': 'Late Server Action',
                'model_id': self.partner_model.id,
                'binding_model_id': self.partner_model.id,
                'state': 'code',
                'code': 'pass',
                'execute_in_batch': True,
                'execution_batch_size': 3,
            }
        )
        after = self.env['ir.actions.actions'].get_bindings('res.partner')['action']
        self.assertEqual(len(after), len(before) + 1)
        binding = self._get_binding('action', created.id)
        self.assertEqual(binding['execution_batch_size'], 3)

    def test_cached_binding_values_stay_immutable(self):
        cached = self.env['ir.actions.actions']._get_bindings('res.partner')
        values = next(
            entry for entry in cached['action'] if entry['id'] == self.server_action.id
        )
        with self.assertRaises(NotImplementedError):
            values['execution_batch_size'] = 99
