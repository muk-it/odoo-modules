from __future__ import annotations

import contextlib
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai_schedule.tools.constants import (
    DEFAULT_MAX_COST_EUR,
    DEFAULT_MAX_LIFETIME_HOURS,
    DEFAULT_MAX_RESUMES,
    DEFAULT_MAX_TOTAL_TOKENS,
)
from odoo.addons.muk_ai_schedule.tools.recurrence import compute_next_call


class AISchedule(models.Model):
    """Fire AI agent sessions on a cron cadence through an owned action."""

    _name = 'muk_ai.schedule'
    _description = 'AI Schedule'
    _inherit = [
        'mail.thread',
        'muk_ai.revision.mixin',
        'muk_ai.prompt.mixin',
    ]
    _order = 'name'

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    RECURRENCE_KEYS = {
        'interval_type',
        'interval_number',
        'weekday',
        'monthday',
        'cron_expression',
    }

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        copy=False,
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Agent',
        required=True,
        ondelete='restrict',
    )

    prompt = fields.Text(
        string='Prompt',
        help=(
            'Initial prompt sent to the agent on each fire. '
            "Rendered as an inline template with the schedule's "
            'evaluation context.'
        ),
        required=True,
        translate=True,
    )

    interval_type = fields.Selection(
        selection=[
            ('minutes', 'Minutes'),
            ('hours', 'Hours'),
            ('days', 'Days'),
            ('weeks', 'Weeks'),
            ('months', 'Months'),
            ('cron', 'Cron Expression'),
        ],
        string='Interval Type',
        required=True,
        default='days',
    )

    interval_number = fields.Integer(
        string='Interval Number',
        required=True,
        default=1,
    )

    weekday = fields.Selection(
        selection=[
            ('mon', 'Monday'),
            ('tue', 'Tuesday'),
            ('wed', 'Wednesday'),
            ('thu', 'Thursday'),
            ('fri', 'Friday'),
            ('sat', 'Saturday'),
            ('sun', 'Sunday'),
        ],
        string='Weekday',
        help='Day of week (only for weeks interval).',
    )

    monthday = fields.Integer(
        string='Day of Month',
        help='Day of month, 1-31 (only for months interval).',
    )

    cron_expression = fields.Char(
        string='Cron Expression',
        help='Standard 5-field cron expression (only for cron interval).',
    )

    dispatch_mode = fields.Selection(
        selection=[
            ('single', 'Single'),
            ('per_record', 'Per Record'),
        ],
        string='Dispatch Mode',
        required=True,
        default='single',
    )

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Target Model',
        help=(
            'Target model used to resolve `records` for the prompt template '
            '(single mode) or the dispatched recordset (per-record mode).'
        ),
        ondelete='set null',
    )

    model_name = fields.Char(
        related='model_id.model',
        string='Target Model Name',
        readonly=True,
    )

    record_source = fields.Selection(
        selection=[
            ('domain', 'Domain'),
            ('code', 'Python'),
        ],
        string='Record Source',
        help=(
            'Domain: simple Odoo domain on the target model. '
            'Python: safe-evaluated code that must assign a recordset to the '
            '`records` variable. Available context: env, now, today.'
        ),
        required=True,
        default='domain',
    )

    domain = fields.Char(
        string='Domain',
        help='Domain on the target model. Used when Record Source is Domain.',
        default='[]',
    )

    record_code = fields.Text(
        string='Record Code',
        help=(
            'Python code (safe-evaluated) that must assign a recordset to the '
            '`records` variable. Used when Record Source is Python. '
            "Example: records = env['res.partner'].search([], limit=10)"
        ),
    )

    max_records_per_fire = fields.Integer(
        string='Max Records Per Fire',
        help='Per-record dispatch caps the number of sessions spawned per cron tick.',
        default=100,
    )

    action_server_id = fields.Many2one(
        comodel_name='ir.actions.server',
        string='Owned Server Action',
        readonly=True,
        copy=False,
        ondelete='restrict',
    )

    cron_id = fields.Many2one(
        comodel_name='ir.cron',
        string='Owned Cron',
        readonly=True,
        copy=False,
        ondelete='restrict',
    )

    next_call = fields.Datetime(
        related='cron_id.nextcall',
        string='Next Call',
        readonly=False,
        store=False,
    )

    last_call = fields.Datetime(
        related='cron_id.lastcall',
        string='Last Call',
        readonly=True,
        store=False,
    )

    max_resumes = fields.Integer(
        string='Max Resumes',
        help='Override for the per-session resume cap. 0 uses the module default.',
        default=0,
    )

    max_lifetime_hours = fields.Integer(
        string='Max Lifetime (hours)',
        help='Override for the per-session wall-clock lifetime cap. 0 uses the module default.',
        default=0,
    )

    max_total_tokens = fields.Integer(
        string='Max Total Tokens',
        help='Override for the per-session total token cap. 0 uses the module default.',
        default=0,
    )

    max_cost_eur = fields.Float(
        string='Max Cost (EUR)',
        help='Override for the per-session cost cap. 0 uses the module default.',
        default=0.0,
    )

    session_count = fields.Integer(
        compute='_compute_session_count',
        string='Sessions',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Owner',
        required=True,
        default=lambda self: self.env.user,
        ondelete='restrict',
    )

    note = fields.Html(
        string='Notes',
        help='Internal notes for administrators.',
        sanitize=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_prompt_fields(self) -> list[str]:
        """Return the field names that hold renderable prompt templates."""
        return ['prompt']

    @api.model
    def _prompt_eval_context(self) -> dict:
        """Extend the prompt evaluation context with the current time."""
        ctx = super()._prompt_eval_context()
        ctx['now'] = fields.Datetime.now()
        return ctx

    def _build_prompt(self, **add_context) -> tuple[str, str | None]:
        """Render the schedule prompt safely with the evaluation context."""
        return self._render_prompt_safe(self.prompt or '', **add_context)

    def _effective_caps(self) -> dict:
        """Return the resolved per-session caps for this schedule."""
        self.ensure_one()
        if self.action_server_id and hasattr(
            self.action_server_id, '_agent_effective_caps'
        ):
            return self.action_server_id._agent_effective_caps()
        return {
            'max_resumes': self.max_resumes or DEFAULT_MAX_RESUMES,
            'max_lifetime_hours': (
                self.max_lifetime_hours or DEFAULT_MAX_LIFETIME_HOURS
            ),
            'max_total_tokens': (self.max_total_tokens or DEFAULT_MAX_TOTAL_TOKENS),
            'max_cost_eur': self.max_cost_eur or DEFAULT_MAX_COST_EUR,
        }

    def _default_model_id(self) -> int:
        """Return the target model id, defaulting to the AI session model."""
        if self.model_id:
            return self.model_id.id
        return self.env.ref('muk_ai.model_muk_ai_session').id

    def _build_action_vals(self) -> dict:
        """Build the create/write values for the owned server action."""
        self.ensure_one()
        return {
            'name': self.name,
            'model_id': self._default_model_id(),
            'state': 'ai_agent',
            'agent_id': self.agent_id.id,
            'agent_prompt': self.prompt or '',
            'agent_dispatch_mode': self.dispatch_mode,
            'agent_record_source': self.record_source,
            'agent_record_domain': self.domain or '[]',
            'agent_record_code': self.record_code or '',
            'agent_max_records_per_fire': self.max_records_per_fire or 0,
            'agent_max_resumes': self.max_resumes or 0,
            'agent_max_lifetime_hours': self.max_lifetime_hours or 0,
            'agent_max_total_tokens': self.max_total_tokens or 0,
            'agent_max_cost_eur': self.max_cost_eur or 0.0,
            'agent_chain_strategy': (
                'per_record' if self.dispatch_mode == 'per_record' else 'none'
            ),
        }

    def _compute_initial_nextcall(self) -> datetime:
        """Compute the first cron fire time, falling back to now on error."""
        self.ensure_one()
        try:
            nc = compute_next_call(
                self.interval_type,
                self.interval_number,
                weekday=self.weekday,
                monthday=self.monthday or None,
                cron_expression=self.cron_expression,
            )
        except ValidationError:
            nc = False
        return nc or fields.Datetime.now()

    def _build_cron_vals(self, action: models.BaseModel) -> dict:
        """Build the create values for the owned cron tied to ``action``."""
        self.ensure_one()
        return {
            'name': 'AI Schedule: %s' % self.name,
            'active': self.active,
            'ir_actions_server_id': action.id,
            'interval_type': (
                self.interval_type if self.interval_type != 'cron' else 'minutes'
            ),
            'interval_number': self.interval_number,
            'user_id': self.user_id.id,
            'nextcall': self._compute_initial_nextcall(),
        }

    def _provision_owned_action(self) -> None:
        """Create the owned server action and cron once, idempotently."""
        self.ensure_one()
        if self.action_server_id and self.cron_id:
            return
        Action = self.env['ir.actions.server'].sudo()
        Cron = self.env['ir.cron'].sudo()
        action = Action.create(self._build_action_vals())
        cron = Cron.create(self._build_cron_vals(action))
        self.sudo().write({'action_server_id': action.id, 'cron_id': cron.id})

    def _sync_to_owned(self) -> None:
        """Propagate schedule changes onto the owned action and cron."""
        self.ensure_one()
        if not self.action_server_id or not self.cron_id:
            return
        self.action_server_id.sudo().write(self._build_action_vals())
        self.cron_id.sudo().write(
            {
                'name': 'AI Schedule: %s' % self.name,
                'active': self.active,
                'interval_type': (
                    self.interval_type if self.interval_type != 'cron' else 'minutes'
                ),
                'interval_number': self.interval_number,
                'user_id': self.user_id.id,
            }
        )
        self._recompute_next_call_on_cron()

    def _recompute_next_call_on_cron(self, base: datetime | None = None) -> None:
        """Recompute and write the owned cron's next fire time."""
        self.ensure_one()
        if not self.cron_id:
            return
        try:
            nc = compute_next_call(
                self.interval_type,
                self.interval_number,
                weekday=self.weekday,
                monthday=self.monthday or None,
                cron_expression=self.cron_expression,
                base=base,
            )
        except ValidationError:
            nc = False
        self.cron_id.sudo().write({'nextcall': nc or fields.Datetime.now()})

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_fire_now(self) -> dict:
        """Provision if needed, fire the schedule now, and open the result."""
        self.ensure_one()
        if not self.action_server_id:
            self._provision_owned_action()
        ctx = {}
        if self.model_id:
            ctx['active_model'] = self.model_id.model
        spawned = self.action_server_id.sudo().with_context(**ctx).run()
        now = fields.Datetime.now()
        self.cron_id.sudo().write({'lastcall': now})
        self._recompute_next_call_on_cron(base=now)
        Session = self.env['muk_ai.session']
        if (
            isinstance(spawned, type(Session))
            and len(spawned) == 1
            and spawned.user_id.id == self.env.uid
        ):
            return spawned.action_open()
        return self.action_open_sessions()

    def action_open_sessions(self) -> dict:
        """Return a window action listing the sessions of this schedule."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sessions'),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('schedule_id', '=', self.id)],
            'context': {'default_schedule_id': self.id},
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_session_count(self) -> None:
        """Count the sessions spawned by each schedule."""
        grouped = self.env['muk_ai.session']._read_group(
            domain=[('schedule_id', 'in', self.ids)],
            groupby=['schedule_id'],
            aggregates=['__count'],
        )
        counts = {schedule.id: count for schedule, count in grouped}
        for record in self:
            record.session_count = counts.get(record.id, 0)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISchedule:
        """Create schedules and provision their owned action and cron."""
        records = super().create(vals_list)
        for record in records:
            record._provision_owned_action()
        return records

    def write(self, vals: dict) -> bool:
        """Write schedules and sync mutated cadence/config onto the owned cron."""
        result = super().write(vals)
        sync_keys = {
            'name',
            'agent_id',
            'prompt',
            'dispatch_mode',
            'record_source',
            'domain',
            'record_code',
            'max_records_per_fire',
            'max_resumes',
            'max_lifetime_hours',
            'max_total_tokens',
            'max_cost_eur',
            'active',
            'user_id',
            'model_id',
        } | self.RECURRENCE_KEYS
        if sync_keys & set(vals):
            for record in self:
                record._sync_to_owned()
        return result

    def unlink(self) -> bool:
        """Unlink schedules and best-effort clean up their owned action and cron."""
        actions = self.mapped('action_server_id')
        crons = self.mapped('cron_id')
        result = super().unlink()
        with contextlib.suppress(Exception):
            crons.sudo().unlink()
        with contextlib.suppress(Exception):
            actions.sudo().unlink()
        return result
