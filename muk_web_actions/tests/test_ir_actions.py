from __future__ import annotations

from odoo.tests import TransactionCase


class TestBatchBindings(TransactionCase):
    """Check the batch settings that the action bindings hand to the web client."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a batch and a plain server action and a batch report."""
        super().setUpClass()
        partner_model = cls.env['ir.model']._get('res.partner')
        server_values = {
            'model_id': partner_model.id,
            'binding_model_id': partner_model.id,
            'state': 'code',
            'code': 'pass',
        }
        cls.batch_action, cls.plain_action = cls.env['ir.actions.server'].create(
            [
                {
                    **server_values,
                    'name': 'Approve',
                    'execute_in_batch': True,
                    'execution_batch_size': 25,
                },
                {**server_values, 'name': 'Archive'},
            ]
        )
        cls.report = cls.env['ir.actions.report'].create(
            {
                'name': 'Badge',
                'model': 'res.partner',
                'binding_model_id': partner_model.id,
                'report_name': 'muk_web_actions.report_badge',
                'report_type': 'qweb-pdf',
                'execute_in_batch': True,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_binding(self, record: object, lang: str = 'en_US') -> dict:
        """Return the binding values of an action as the web client gets them."""
        bindings = (
            self.env['ir.actions.actions']
            .with_context(lang=lang)
            .get_bindings('res.partner')
        )
        return next(
            values
            for values in bindings['report' if record == self.report else 'action']
            if values['id'] == record.id
        )

    def _get_batch_values(self, record: object) -> tuple:
        """Return the batch flag and batch size of an action binding."""
        binding = self._get_binding(record)
        return binding.get('execute_in_batch'), binding.get('execution_batch_size')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_bindings_follow_the_batch_settings(self):
        self.assertEqual(self._get_batch_values(self.batch_action), (True, 25))
        self.assertEqual(self._get_batch_values(self.plain_action), (None, None))
        self.assertEqual(self._get_batch_values(self.report), (True, 1))
        self.plain_action.write({'execute_in_batch': True, 'execution_batch_size': 7})
        self.batch_action.execute_in_batch = False
        self.report.report_type = 'qweb-html'
        self.assertEqual(self._get_batch_values(self.plain_action), (True, 7))
        self.assertEqual(self._get_batch_values(self.batch_action), (None, None))
        self.assertEqual(self._get_batch_values(self.report), (None, None))

    def test_html_reports_are_never_batched(self):
        self.report.report_type = 'qweb-html'
        self.assertFalse(self.report.execute_in_batch)
        self.report.report_type = 'qweb-pdf'
        self.assertFalse(self.report.execute_in_batch)
        self.report.execute_in_batch = True
        self.assertTrue(self.report.execute_in_batch)

    def test_binding_labels_stay_per_language(self):
        self.env['res.lang']._activate_lang('fr_FR')
        self.batch_action.with_context(lang='fr_FR').name = 'Approuver'
        self.assertEqual(self._get_binding(self.batch_action)['name'], 'Approve')
        self.assertEqual(
            self._get_binding(self.batch_action, 'fr_FR')['name'], 'Approuver'
        )
