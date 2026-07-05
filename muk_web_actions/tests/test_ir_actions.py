from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestActionBindingsLang(TransactionCase):
    """Check that action binding labels are served per language."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.server_action = cls.env['ir.actions.server'].create(
            {
                'name': 'Approve',
                'model_id': cls.partner_model.id,
                'binding_model_id': cls.partner_model.id,
                'state': 'code',
                'code': 'pass',
            }
        )
        cls.server_action.with_context(lang='fr_FR').write({'name': 'Approuver'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_binding_name(self, lang: str) -> str:
        """Return the bound server action label as rendered in the given language."""
        bindings = (
            self.env['ir.actions.actions']
            .with_context(lang=lang)
            .get_bindings('res.partner')
        )
        return next(
            values['name']
            for values in bindings['action']
            if values['id'] == self.server_action.id
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_binding_label_is_per_language(self):
        self.assertEqual(self._get_binding_name('en_US'), 'Approve')
        self.assertEqual(self._get_binding_name('fr_FR'), 'Approuver')
