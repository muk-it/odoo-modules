from __future__ import annotations

from odoo.api import Environment

from . import models


def _restore_mobile_from_upgrade_notes(env: Environment) -> int:
    """Restore mobile numbers logged as chatter notes by the version upgrade.

    The Odoo 19 upgrade removed ``mobile`` from partners, moved the value
    to ``phone`` when that was empty and otherwise logged it as a
    "Previous Mobile:" note. Fill the reintroduced field from the latest
    note of each partner unless the number already lives on the partner.
    """
    env.flush_all()
    env.cr.execute(
        """
        WITH notes AS (
            SELECT DISTINCT ON (message.res_id)
                   message.res_id,
                   BTRIM(
                       SUBSTRING(message.body FROM '^Previous Mobile:(.*)$')
                   ) AS mobile
            FROM mail_message message
            WHERE message.model = 'res.partner'
              AND message.body LIKE 'Previous Mobile:%'
            ORDER BY message.res_id, message.id DESC
        )
        SELECT partner.id, notes.mobile
        FROM notes
        JOIN res_partner partner ON partner.id = notes.res_id
        WHERE notes.mobile <> ''
          AND (partner.mobile IS NULL OR partner.mobile = '')
          AND partner.phone IS DISTINCT FROM notes.mobile
          AND partner.phone2 IS DISTINCT FROM notes.mobile
        """
    )
    rows = env.cr.fetchall()
    partners = env['res.partner'].with_context(active_test=False)
    for partner_id, mobile in rows:
        partners.browse(partner_id).write({'mobile': mobile})
    return len(rows)


def _setup_module(env: Environment) -> None:
    """Split unnamed partners and restore upgrade-logged mobile numbers untracked."""
    env = env(context={**env.context, 'tracking_disable': True})
    _restore_mobile_from_upgrade_notes(env)
    records = (
        env['res.partner']
        .with_context(active_test=False)
        .search(
            [
                ('firstname', '=', False),
                ('lastname', '=', False),
            ]
        )
    )
    records._inverse_name()
