from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCard(TransactionCase):
    """Match the site open in the browser to the companies in Odoo."""

    def test_the_card_shows_the_companies_of_the_site(self):
        partners = self.env['res.partner'].create(
            [
                {'name': 'Acme', 'website': 'https://www.acme.com'},
                {
                    'name': 'Beta',
                    'email': 'info@beta.co.uk',
                    'child_ids': [Command.create({'name': 'Ben'})],
                },
                {'name': 'Notacme', 'website': 'notacme.com'},
                {'name': 'Jane', 'email': 'jane@gmail.com'},
            ]
        )
        acme, beta, notacme = partners[:3]
        card = self.env['muk_ai_browser.card']
        for url, expected in (
            ('https://shop.acme.com/products/1', acme),
            ('https://www.acme.com/', acme),
            ('https://beta.co.uk/contact', beta),
            ('https://notacme.com', notacme),
            ('https://mail.gmail.com/', None),
        ):
            with self.subTest(url):
                found = card._lookup(url)
                self.assertEqual(
                    found['partner'] and found['partner']['path'],
                    expected and f'/odoo/res.partner/{expected.id}',
                )
                self.assertEqual(
                    'Contact' in [a['label'] for a in found['actions']],
                    not expected,
                )
        self.assertEqual(card._lookup(card.get_base_url() + '/odoo'), {})
        self.assertEqual(card._lookup('chrome://extensions'), {})
