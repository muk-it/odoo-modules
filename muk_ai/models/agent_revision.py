import difflib

from odoo import _, api, fields, models


class AIAgentRevision(models.Model):

    _name = 'muk_ai.agent.revision'
    _description = "AI Agent Revision"
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    display_name = fields.Char(
        compute='_compute_display_name',
        string="Display Name",
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string="Agent",
        required=True,
        index=True,
        ondelete='cascade',
    )

    body = fields.Text(
        string="System Prompt",
        readonly=True,
        required=True,
    )

    preview = fields.Char(
        compute='_compute_preview',
        string="Preview",
        store=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _unified_diff(self):
        old = (self.body or '').splitlines(keepends=False)
        new = (self.agent_id.system_prompt or '').splitlines(
            keepends=False
        )
        return '\n'.join(difflib.unified_diff(
            old, new,
            fromfile=self.display_name,
            tofile=_("Current"),
            lineterm='',
        ))

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_restore(self):
        self.ensure_one()
        self.agent_id.system_prompt = self.body
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("System prompt restored from %s.", self.display_name),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_compare(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'muk_ai.revision_dialog',
            'name': _("Compare to Current"),
            'params': {
                'old_label': self.display_name,
                'new_label': _("Current"),
                'diff': self._unified_diff(),
            },
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('create_date', 'agent_id.name')
    def _compute_display_name(self):
        for record in self:
            when = (
                fields.Datetime.to_string(record.create_date)
                if record.create_date else _("draft")
            )
            record.display_name = _("Revision %s", when)

    @api.depends('body')
    def _compute_preview(self):
        for record in self:
            text = (record.body or '').strip().replace('\n', ' ')
            record.preview = text[:120] + ('…' if len(text) > 120 else '')
