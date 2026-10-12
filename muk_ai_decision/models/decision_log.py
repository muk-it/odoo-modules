from __future__ import annotations

from odoo import api, fields, models


class AIDecisionLog(models.Model):
    """One answered or failed decision: its questions, answers, model and cost."""

    _name = 'muk_ai.decision.log'
    _description = 'AI Decision Log'
    _order = 'id desc'
    _rec_name = 'origin'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    action_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Server Action',
        readonly=True,
        index=True,
        ondelete='set null',
    )

    applied = fields.Json(
        string='Written Values',
        help='Field values the decision wrote, with the answers they came from.',
        readonly=True,
    )

    model_id = fields.Many2one(
        comodel_name='muk_ai.model',
        string='Model',
        readonly=True,
        index=True,
        ondelete='set null',
    )

    served_model = fields.Char(
        string='Served Version',
        help='Exact model version the provider reported for this decision.',
        readonly=True,
    )

    origin = fields.Char(
        string='Origin',
        help='Caller that asked for the decision.',
        readonly=True,
        index=True,
    )

    res_model = fields.Char(
        string='Record Model',
        readonly=True,
    )

    res_id = fields.Many2oneReference(
        string='Record ID',
        readonly=True,
        model_field='res_model',
    )

    res_name = fields.Char(
        compute='_compute_res_name',
        string='Record',
    )

    questions = fields.Json(
        string='Questions',
        readonly=True,
    )

    answers = fields.Json(
        string='Answers',
        readonly=True,
    )

    state_payload = fields.Json(
        string='State',
        help='Text or record the decision was about.',
        readonly=True,
    )

    confident = fields.Boolean(
        string='Confident',
        help='Every answer reached the confidence the caller asked for.',
        readonly=True,
    )

    duration = fields.Integer(
        string='Duration (ms)',
        readonly=True,
        aggregator='avg',
    )

    input_tokens = fields.Integer(
        string='Input Tokens',
        readonly=True,
    )

    output_tokens = fields.Integer(
        string='Output Tokens',
        readonly=True,
    )

    total_cost = fields.Float(
        string='Cost',
        readonly=True,
        digits=(12, 6),
    )

    currency = fields.Char(
        string='Currency',
        readonly=True,
    )

    error = fields.Text(
        string='Error',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self) -> None:
        """Name the record the decision was about, empty once it is deleted."""
        for log in self:
            record = (
                log.res_model in self.env
                and self.env[log.res_model].browse(log.res_id).exists()
            )
            log.res_name = record.display_name if record else False

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_logs(self) -> None:
        """Delete the decisions older than the audit log retention."""
        limit = self.env['muk_mcp.log']._retention_limit()
        self.search([('create_date', '<', limit)]).unlink()
