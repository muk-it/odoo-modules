from __future__ import annotations

from odoo.tests import TransactionCase

CORE_DO_NOT_TRACK = (
    'We do not currently support Do Not Track signals, as there is no industry '
    'standard for compliance.'
)
GERMAN_DO_NOT_TRACK = 'Wir unterstützen derzeit keine Do-Not-Track-Signale.'


class TestPolicy(TransactionCase):
    """The policy extension applies in every language, not only in English."""

    def test_the_signal_paragraph_is_replaced_in_a_translated_policy(self):
        self.env['res.lang']._activate_lang('de_DE')
        view = self.env.ref('website.cookie_policy')
        view.update_field_translations(
            'arch_db', {'de_DE': {CORE_DO_NOT_TRACK: GERMAN_DO_NOT_TRACK}}
        )
        for lang, core in (
            ('en_US', CORE_DO_NOT_TRACK),
            ('de_DE', GERMAN_DO_NOT_TRACK),
        ):
            arch = view.with_context(lang=lang)._get_combined_arch()
            self.assertIn('Global Privacy Control', arch.xpath('string(.)'), lang)
            self.assertNotIn(core, arch.xpath('string(.)'), lang)
