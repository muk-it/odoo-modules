from __future__ import annotations

import uuid

from odoo import api, fields, models
from odoo.tools import SQL


class BrowserSession(models.Model):
    """Browser actuator session attached to a MuK AI agent session."""

    _name = 'muk_ai_browser.session'
    _description = 'MuK AI Browser Session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    session_id = fields.Char(
        string='Session ID',
        required=True,
        index=True,
        copy=False,
        default=lambda self: str(uuid.uuid4()),
    )

    ai_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='AI Session',
        ondelete='cascade',
    )

    key_id = fields.Many2one(
        comodel_name='muk_mcp.key',
        string='Device Key',
        ondelete='set null',
    )

    device_label = fields.Char(
        string='Device Label',
    )

    last_activity = fields.Datetime(
        string='Last Activity',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    last_event_seq = fields.Integer(
        string='Last Event Sequence',
        default=0,
    )

    last_origin = fields.Char(
        string='Last Page Origin',
        help='Origin of the page the extension last acted on, used for '
        'per-site permission gating.',
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _set_origin(self, origin: str | None) -> models.BaseModel:
        """Record the active page origin reported by the extension and return self."""
        if origin:
            self.sudo().write({'last_origin': origin})
        return self

    @api.model
    def _attach(
        self,
        ai_session: models.BaseModel,
        key: models.BaseModel,
        device_label: str | None = None,
    ) -> models.BaseModel:
        """Find or create the active browser session for an AI session and key.

        :return: the attached browser session, with its activity stamped
        """
        session = self.sudo().search(
            [
                ('ai_session_id', '=', ai_session.id),
                ('key_id', '=', key.id),
                ('active', '=', True),
            ],
            limit=1,
        )
        if not session:
            session = self.sudo().create(
                {
                    'ai_session_id': ai_session.id,
                    'key_id': key.id,
                    'device_label': device_label,
                },
            )
        return session._touch()

    def _touch(self) -> models.BaseModel:
        """Stamp the last-activity time on this session and return it."""
        self.sudo().write({'last_activity': fields.Datetime.now()})
        return self

    def _enqueue_event(self, event_type: str, payload: dict) -> models.BaseModel:
        """Append an event for the extension, allocating the next sequence atomically.

        :return: the created ``muk_ai_browser.event`` record
        """
        self.ensure_one()
        self.env.cr.execute(
            SQL(
                """
            UPDATE %s SET last_event_seq = last_event_seq + 1
             WHERE id = %s
            RETURNING last_event_seq
            """,
                SQL.identifier(self._table),
                self.id,
            ),
        )
        seq = self.env.cr.fetchone()[0]
        self.invalidate_recordset(['last_event_seq'])
        return (
            self.env['muk_ai_browser.event']
            .sudo()
            .create(
                {
                    'browser_session_id': self.id,
                    'seq': seq,
                    'type': event_type,
                    'payload': payload,
                },
            )
        )
