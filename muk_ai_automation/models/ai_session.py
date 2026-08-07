from __future__ import annotations

from odoo import fields, models

from odoo.addons.muk_ai_automation.tools.dispatch import (
    PreviousProxy,
    _resolve_records,
)


class AISession(models.Model):
    """Link AI sessions to the server action that spawned them."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    action_server_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Server Action',
        help='Server action that spawned this session.',
        index=True,
        copy=False,
        ondelete='set null',
    )

    base_automation_id = fields.Many2one(
        comodel_name='base.automation',
        related='action_server_id.base_automation_id',
        string='Automation Rule',
        readonly=True,
        store=False,
    )

    previous_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Previous Session',
        help='Prior session in the per-record chain.',
        copy=False,
        ondelete='set null',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _available_client_kinds(self) -> set[str]:
        """Drop the webclient kind for action-spawned sessions.

        A session fired by a server action or automation rule runs headless
        — no tab hosts its chat window, so webclient-served tools would only
        pend until the stale-action sweep.
        """
        kinds = super()._available_client_kinds()
        if self.id and self.action_server_id:
            kinds.discard('webclient')
        return kinds

    def _session_prompt_extras(self) -> dict:
        """Add record, records, previous-session, and now to the prompt scope."""
        extras = super()._session_prompt_extras()
        empty = self.env['base'].browse([])
        record, records, previous = empty, empty, PreviousProxy(None)
        if self and self.id:
            linked = self._linked_record()
            if linked is not None and self._owner_can_read(linked):
                record = linked.with_user(self.user_id or self.env.user)
            previous = PreviousProxy(self.previous_session_id or None)
            action = self.action_server_id
            if action and action.agent_dispatch_mode == 'single':
                records = _resolve_records(action, {})
        extras.update(
            {
                'now': fields.Datetime.now(),
                'record': record,
                'records': records,
                'previous_session': previous,
            }
        )
        return extras
