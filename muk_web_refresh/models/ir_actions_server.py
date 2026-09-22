from __future__ import annotations

from odoo import fields, models


class IrActionsServer(models.Model):
    """Add a server action type that broadcasts view reload requests."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[
            ('refresh', 'Reload Views'),
        ],
        ondelete={'refresh': 'cascade'},
    )

    refresh_view_types = fields.Char(
        string='View Types',
        help=(
            'Comma-separated list of view types to reload (e.g. list, kanban). '
            'Leave empty to reload all view types.'
        ),
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def _run_action_refresh_multi(self, eval_context: dict | None = None) -> None:
        """Send a view reload request to internal users over the bus."""
        records = eval_context.get('records') or eval_context.get('record')
        message = {
            'model': self.model_id.model,
            'view_types': [
                vt.strip()
                for vt in (self.refresh_view_types or '').split(',')
                if vt.strip()
            ],
            'rec_ids': records.ids if records else [],
        }
        self.env['bus.bus']._sendone(
            self.env.ref('base.group_user'), 'muk_web_refresh.reload', message
        )
