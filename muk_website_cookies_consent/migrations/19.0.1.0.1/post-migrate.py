from __future__ import annotations

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

WITHDRAWN = ('muk_website_cookies_consent.cookie_visitor_uuid',)

CORRECTED = {
    'muk_website_cookies_consent.cookie_session_id': {
        'duration': '7 days of inactivity',
    },
    'muk_website_cookies_consent.cookie_muk_cookie_consent': {
        'duration': '6 to 24 months, depending on your region',
    },
    'muk_website_cookies_consent.cookie_website_cookies_bar': {
        'duration': '6 to 24 months, depending on your region',
    },
    'muk_website_cookies_consent.cookie_odoo_color_scheme': {
        'duration': '1 year',
    },
    'muk_website_cookies_consent.cookie_odoo_presence': {
        'duration': 'Until the browser storage is cleared',
    },
    'muk_website_cookies_consent.cookie_odoo_multi_tab': {
        'duration': 'Until the browser storage is cleared',
    },
}


def migrate(cr, version: str) -> None:
    """Correct declarations that ``noupdate`` would otherwise leave standing.

    The seed data is ``noupdate="1"``, so a database installed before these
    corrections keeps publishing them on its cookie policy. That is the one
    document a regulator reads, so it cannot be left saying that a cookie
    exists which Odoo has not set since 17.0, that a session lasts a year, or
    that a convenience is strictly necessary.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id in WITHDRAWN:
        record = env.ref(xml_id, raise_if_not_found=False)
        if record:
            _logger.info('Withdrawing the %s declaration: it is not set.', record.name)
            record.unlink()
    for xml_id, values in CORRECTED.items():
        record = env.ref(xml_id, raise_if_not_found=False)
        if record:
            record.write(values)
    env['website'].search([])._clear_cookie_registry_cache()
