from __future__ import annotations

from urllib.parse import urlsplit

from odoo import api, models


class BrowserCard(models.AbstractModel):
    """Match the site open in the browser to the company in Odoo behind it."""

    _name = 'muk_ai_browser.card'
    _description = 'Browser Page Card'
    _explanation = (
        'The card the browser extension shows above its side panel chat: the '
        'company in Odoo whose website or email is on the site open in the '
        'browser, or the prompts that create one.'
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _card_site(self, host: str) -> str:
        """Return the registered domain of a host, ``acme.co.uk`` of ``shop.acme.co.uk``."""
        labels = host.split('.')
        size = 3 if len(labels) > 2 and len(labels[-2]) <= 3 else 2
        return '.'.join(labels[-size:])

    @api.model
    def _card_hosts(self, partner: models.BaseModel) -> set[str]:
        """Return the host of a company's website, and of its email for a company."""
        website = partner.website or ''
        hosts = {urlsplit(website if '//' in website else f'//{website}').hostname}
        if partner.is_company or partner.child_ids:
            hosts.add(partner.email.rpartition('@')[2] if partner.email else '')
        return {(host or '').strip().lower().removeprefix('www.') for host in hosts} - {
            ''
        }

    @api.model
    def _card_partner(self, host: str) -> models.BaseModel:
        """Return the top-level contact whose website or company email is on the host."""
        site = self._card_site(host)
        candidates = self.env['res.partner'].search(
            [
                ('parent_id', '=', False),
                '|',
                ('website', 'ilike', site),
                '&',
                ('email', 'ilike', site),
                '|',
                ('is_company', '=', True),
                ('child_ids', '!=', False),
            ],
            limit=50,
        )
        return candidates.filtered(
            lambda partner: any(
                host == known or host.endswith(f'.{known}')
                for known in self._card_hosts(partner)
            )
        )[:1]

    @api.model
    def _card_details(self, partner: models.BaseModel) -> list[str]:
        """Return the short facts the card names about a company."""
        return [partner.city] if partner.city else []

    @api.model
    def _card_actions(self, host: str, partner: models.BaseModel) -> list[dict]:
        """Return the prompts the card offers for the page's site."""
        if partner:
            return []
        return [
            {
                'label': self.env._('Contact'),
                'prompt': self.env._(
                    'Create a company contact in Odoo for the site on this page '
                    '(%s) with its name, address, email and phone from the page. '
                    'Ask me before saving.',
                    host,
                ),
            }
        ]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _lookup(self, url: str) -> dict:
        """Return the card of the page at ``url``, or ``{}`` for no web page or Odoo."""
        session = self.env['muk_ai.session']
        origin = session._browser_origin_of(url)
        host = (urlsplit(origin).hostname or '').removeprefix('www.')
        if not host or origin == session._browser_origin_of(self.get_base_url()):
            return {}
        partner = self._card_partner(host)
        return {
            'host': host,
            'partner': {
                'name': partner.display_name,
                'path': f'/odoo/res.partner/{partner.id}',
                'details': self._card_details(partner),
            }
            if partner
            else None,
            'actions': self._card_actions(host, partner),
        }
