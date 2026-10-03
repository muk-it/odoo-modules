from __future__ import annotations

import logging

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)


def migrate(cr: Cursor, version: str | None) -> None:
    """Map the policy link to a policy page and drop the Consent Mode that is gone."""
    cr.execute(
        "UPDATE website SET cookie_consent_mode = 'basic' "
        "WHERE cookie_consent_mode = 'off'"
    )
    cr.execute(
        """
        SELECT id, cookie_policy_url
          FROM website
         WHERE COALESCE(cookie_policy_url, '') NOT IN ('', '/cookie-policy')
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    for website_id, url in cr.fetchall():
        page = env['website.page'].search(
            [('url', '=', url), ('website_id', 'in', [website_id, False])],
            order='website_id',
            limit=1,
        )
        if page:
            env['website'].browse(website_id).cookie_policy_id = page
        else:
            _logger.warning(
                'Website %s links its cookie policy to "%s", which is no page of '
                'the website. Choose the policy page in the website settings.',
                website_id,
                url,
            )
