from __future__ import annotations

from odoo import api, fields, models
from odoo.tools import SQL


class BrowserEvent(models.Model):
    """Per-session queue of events streamed to the browser extension."""

    _name = 'muk_ai_browser.event'
    _description = 'MuK AI Browser Event'
    _order = 'seq asc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    browser_session_id = fields.Many2one(
        comodel_name='muk_ai_browser.session',
        string='Browser Session',
        required=True,
        index=True,
        ondelete='cascade',
    )

    seq = fields.Integer(
        string='Sequence',
        required=True,
        index=True,
    )

    type = fields.Selection(
        selection=[
            ('state', 'State'),
            ('event', 'Event'),
            ('action_request', 'Action Request'),
            ('ask', 'Ask'),
        ],
        string='Type',
        required=True,
    )

    payload = fields.Json(
        string='Payload',
    )

    delivered = fields.Boolean(
        string='Delivered',
        default=False,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _claim(
        self,
        browser_session: models.BaseModel,
        after_seq: int = 0,
        limit: int = 50,
    ) -> list[tuple[int, str, dict]]:
        """Atomically claim up to ``limit`` undelivered events for a session.

        Uses ``FOR UPDATE SKIP LOCKED`` so concurrent SSE readers never claim the
        same rows, marks the selected rows delivered and returns them ordered by
        sequence.

        :param after_seq: only claim events with a higher sequence (resume support).
        :return: a list of ``(seq, type, payload)`` tuples ordered by sequence
        """
        self.env.cr.execute(
            SQL(
                """
            UPDATE %s SET delivered = true
             WHERE id IN (
                SELECT id FROM %s
                 WHERE browser_session_id = %s AND delivered = false AND seq > %s
                 ORDER BY seq ASC LIMIT %s
                   FOR UPDATE SKIP LOCKED
             ) RETURNING seq, type, payload
            """,
                SQL.identifier(self._table),
                SQL.identifier(self._table),
                browser_session.id,
                after_seq,
                limit,
            ),
        )
        rows = sorted(self.env.cr.fetchall(), key=lambda row: row[0])
        self.invalidate_model(['delivered'])
        return rows

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_events(self) -> None:
        """Delete delivered events past their retention window."""
        delivered_limit = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        stale_limit = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        domain = [
            '|',
            '&',
            ('delivered', '=', True),
            ('create_date', '<', delivered_limit),
            '&',
            ('delivered', '=', False),
            ('create_date', '<', stale_limit),
        ]
        while batch := self.search(domain, limit=5000):
            batch.unlink()
            self.env.cr.commit()
