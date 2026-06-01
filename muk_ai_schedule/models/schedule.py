from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai_schedule.tools.constants import (
    DEFAULT_MAX_COST_EUR,
    DEFAULT_MAX_LIFETIME_HOURS,
    DEFAULT_MAX_RESUMES,
    DEFAULT_MAX_TOTAL_TOKENS,
    SCHEDULE_LOCK_NAMESPACE,
    SCHEDULE_SWEEP_LIMIT,
)
from odoo.addons.muk_ai_schedule.tools.dispatch import fire_schedule
from odoo.addons.muk_ai_schedule.tools.recurrence import compute_next_call


class AISchedule(models.Model):

    _name = 'muk_ai.schedule'
    _description = "AI Schedule"
    _inherit = [
        'mail.thread',
        'muk_ai.revision.mixin',
        'muk_ai.prompt.mixin',
    ]
    _order = 'name'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def RECURRENCE_KEYS(self):
        return {
            'interval_type',
            'interval_number',
            'weekday',
            'monthday',
            'cron_expression'
        }


    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        copy=False,
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string="Agent",
        required=True,
        ondelete='restrict',
    )

    prompt = fields.Text(
        string="Prompt",
        help=(
            "Initial prompt sent to the agent on each fire. "
            "Rendered as an inline template with the schedule's "
            "evaluation context."
        ),
        required=True,
        translate=True,
    )

    interval_type = fields.Selection(
        selection=[
            ('minutes', "Minutes"),
            ('hours', "Hours"),
            ('days', "Days"),
            ('weeks', "Weeks"),
            ('months', "Months"),
            ('cron', "Cron Expression"),
        ],
        string="Interval Type",
        required=True,
        default='days',
    )

    interval_number = fields.Integer(
        string="Interval Number",
        required=True,
        default=1,
    )

    weekday = fields.Selection(
        selection=[
            ('mon', "Monday"),
            ('tue', "Tuesday"),
            ('wed', "Wednesday"),
            ('thu', "Thursday"),
            ('fri', "Friday"),
            ('sat', "Saturday"),
            ('sun', "Sunday"),
        ],
        string="Weekday",
        help="Day of week (only for weeks interval).",
    )

    monthday = fields.Integer(
        string="Day of Month",
        help="Day of month, 1-31 (only for months interval).",
    )

    cron_expression = fields.Char(
        string="Cron Expression",
        help="Standard 5-field cron expression (only for cron interval).",
    )

    dispatch_mode = fields.Selection(
        selection=[
            ('single', "Single"),
            ('per_record', "Per Record"),
        ],
        string="Dispatch Mode",
        required=True,
        default='single',
    )

    model_id = fields.Many2one(
        comodel_name='ir.model',
        string="Target Model",
        help=(
            "Target model used to resolve `records` for the prompt template "
            "(single mode) or the dispatched recordset (per-record mode)."
        ),
        ondelete='set null',
    )

    model_name = fields.Char(
        related='model_id.model',
        string="Target Model Name",
        readonly=True,
    )

    record_source = fields.Selection(
        selection=[
            ('domain', "Domain"),
            ('code', "Python"),
        ],
        string="Record Source",
        help=(
            "Domain: simple Odoo domain on the target model. "
            "Python: safe-evaluated code that must assign a recordset to the "
            "`records` variable. Available context: env, now, today."
        ),
        required=True,
        default='domain',
    )

    domain = fields.Char(
        string="Domain",
        help="Domain on the target model. Used when Record Source is Domain.",
        default='[]',
    )

    record_code = fields.Text(
        string="Record Code",
        help=(
            "Python code (safe-evaluated) that must assign a recordset to the "
            "`records` variable. Used when Record Source is Python. "
            "Example: records = env['res.partner'].search([], limit=10)"
        ),
    )

    max_records_per_fire = fields.Integer(
        string="Max Records Per Fire",
        help="Per-record dispatch caps the number of sessions spawned per cron tick.",
        default=100,
    )

    next_call = fields.Datetime(
        string="Next Call",
        help="Computed next firing time.",
    )

    last_call = fields.Datetime(
        string="Last Call",
        readonly=True,
    )

    max_resumes = fields.Integer(
        string="Max Resumes",
        help="Override for the per-session resume cap. 0 uses the module default.",
        default=0,
    )

    max_lifetime_hours = fields.Integer(
        string="Max Lifetime (hours)",
        help="Override for the per-session wall-clock lifetime cap. 0 uses the module default.",
        default=0,
    )

    max_total_tokens = fields.Integer(
        string="Max Total Tokens",
        help="Override for the per-session total token cap. 0 uses the module default.",
        default=0,
    )

    max_cost_eur = fields.Float(
        string="Max Cost (EUR)",
        help="Override for the per-session cost cap. 0 uses the module default.",
        default=0.0,
    )

    session_count = fields.Integer(
        compute='_compute_session_count',
        string="Sessions",
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="Owner",
        required=True,
        default=lambda self: self.env.user,
        ondelete='restrict',
    )

    note = fields.Html(
        string="Notes",
        help="Internal notes for administrators.",
        sanitize=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_prompt_fields(self):
        return ['prompt']

    def _recompute_next_call(self, base=None):
        for record in self:
            try:
                record.next_call = compute_next_call(
                    record.interval_type,
                    record.interval_number,
                    weekday=record.weekday,
                    monthday=record.monthday or None,
                    cron_expression=record.cron_expression,
                    base=base,
                )
            except Exception:
                record.next_call = False

    @api.model
    def _prompt_eval_context(self):
        ctx = super()._prompt_eval_context()
        ctx['now'] = fields.Datetime.now()
        return ctx

    def _build_prompt(self, **add_context):
        return self._render_prompt_safe(self.prompt or '', **add_context)

    def _effective_caps(self):
        return {
            'max_resumes': self.max_resumes or DEFAULT_MAX_RESUMES,
            'max_lifetime_hours': (
                self.max_lifetime_hours or DEFAULT_MAX_LIFETIME_HOURS
            ),
            'max_total_tokens': (
                self.max_total_tokens or DEFAULT_MAX_TOTAL_TOKENS
            ),
            'max_cost_eur': self.max_cost_eur or DEFAULT_MAX_COST_EUR,
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_fire_now(self):
        self.ensure_one()
        sessions = fire_schedule(self)
        if not sessions:
            raise UserError(_(
                "Schedule produced no sessions (empty domain or invalid agent)."
            ))
        if len(sessions) == 1:
            return sessions.action_open()
        return self.action_open_sessions()

    def action_open_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Sessions"),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('schedule_id', '=', self.id)],
            'context': {'default_schedule_id': self.id},
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_session_count(self):
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
    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_next_call()
        return records

    def write(self, vals):
        result = super().write(vals)
        if self.RECURRENCE_KEYS & set(vals):
            self._recompute_next_call()
        return result

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_fire_due_schedules(self):
        candidates = self.sudo().search(
            [
                ('active', '=', True),
                ('next_call', '!=', False),
                ('next_call', '<=', fields.Datetime.now()),
            ],
            limit=SCHEDULE_SWEEP_LIMIT,
        )
        for schedule in candidates:
            if not self._claim_schedule_lock(schedule.id):
                continue
            try:
                with self.env.cr.savepoint():
                    fire_schedule(schedule)
            except Exception as exc:
                schedule.sudo().message_post(
                    body=(
                        Markup('<p><strong>%s</strong></p><pre class="mb-0">%s</pre>') % (
                            _("Cron fire failed"),
                            str(exc) or _("Unknown error."),
                        ),
                    ),
                    subtype_xmlid='mail.mt_note',
                )

    @api.model
    def _claim_schedule_lock(self, schedule_id):
        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            [SCHEDULE_LOCK_NAMESPACE, schedule_id],
        )
        return self.env.cr.fetchone()[0]
