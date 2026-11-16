from odoo import Command
from odoo.tests import TransactionCase


class TestCard(TransactionCase):
    """Match the site open in the browser to the companies in Odoo."""

    def test_the_card_shows_the_companies_of_the_site(self):
        partners = self.env['res.partner'].create(
            [
                {'name': 'Acme', 'website': 'https://www.acmecardtest.com'},
                {
                    'name': 'Beta',
                    'email': 'info@betacardtest.co.uk',
                    'child_ids': [Command.create({'name': 'Ben'})],
                },
                {'name': 'Notacme', 'website': 'notacmecardtest.com'},
                {'name': 'Jane', 'email': 'jane@gmailcardtest.com'},
            ]
        )
        acme, beta, notacme = partners[:3]
        card = self.env['muk_ai_browser.card']
        for url, expected in (
            ('https://shop.acmecardtest.com/products/1', acme),
            ('https://www.acmecardtest.com/', acme),
            ('https://betacardtest.co.uk/contact', beta),
            ('https://notacmecardtest.com', notacme),
            ('https://mail.gmailcardtest.com/', None),
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
