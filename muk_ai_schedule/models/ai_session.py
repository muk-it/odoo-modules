from __future__ import annotations

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.tools import config

from odoo.addons.muk_ai_schedule.tools.constants import (
    SCHEDULE_PICKUP_LIMIT,
    SCHEDULE_TERMINATING_TOOLS,
)


class AISession(models.Model):
    """Add scheduled resume, recurrence, and chain navigation to sessions."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    schedule_id = fields.Many2one(
        comodel_name='muk_ai.schedule',
        string='Schedule',
        help='Schedule that spawned this session (null for interactive sessions).',
        index=True,
        copy=False,
        ondelete='set null',
    )

    resume_at = fields.Datetime(
        string='Resume At',
        help='Wall-clock time at which the session is due to resume.',
        readonly=True,
        index=True,
        copy=False,
    )

    recur_config = fields.Json(
        string='Recurrence Config',
        help='Persisted schedule_recurring args: {every, until, max_runs}.',
        readonly=True,
        copy=False,
    )

    recur_runs_done = fields.Integer(
        string='Recurrence Runs Done',
        help='How many recur fires this session has executed.',
        readonly=True,
        default=0,
        copy=False,
    )

    resume_prompt = fields.Text(
        string='Resume Prompt',
        help='Synthetic user message injected on next resume.',
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        selection_add=[
            ('schedule', 'Scheduled'),
        ],
        ondelete={'schedule': 'set default'},
    )

    chain_session_count = fields.Integer(
        compute='_compute_chain_session_count',
        string='Chain Sessions',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _chain_session_ids(self) -> set[int]:
        """Return the ids of every session linked to this one, both directions."""
        if not self.id:
            return set()
        Session = self.sudo()
        visited, stack = set(), [self.id]
        while stack:
            sid = stack.pop()
            if sid in visited:
                continue
            record = Session.browse(sid)
            if not record.exists():
                continue
            visited.add(sid)
            if (
                record.previous_session_id
                and record.previous_session_id.id not in visited
            ):
                stack.append(record.previous_session_id.id)
            stack.extend(
                child.id
                for child in Session.search([('previous_session_id', '=', sid)])
                if child.id not in visited
            )
        return visited

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_chain(self) -> dict:
        """Return a window action listing every session in this chain."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Session Chain'),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('id', 'in', sorted(self._chain_session_ids()))],
            'context': {},
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _get_terminating_tools(self) -> set[str]:
        """Add the schedule tools to the set that ends an agent turn."""
        return super()._get_terminating_tools() | SCHEDULE_TERMINATING_TOOLS

    def _available_client_kinds(self) -> set[str]:
        """Drop the webclient kind for schedule-spawned sessions.

        A scheduled session runs headless — no tab hosts its chat window, so
        webclient-served tools would only pend until the stale-action sweep.
        """
        kinds = super()._available_client_kinds()
        if self.id and self.schedule_id:
            kinds.discard('webclient')
        return kinds

    def _run_to_completion(self, has_terminating: bool = False) -> None:
        """Run to completion, then re-defer any recurring sessions."""
        super()._run_to_completion(has_terminating=has_terminating)
        for record in self:
            record._auto_redefer_recurring()

    def _auto_redefer_recurring(self) -> None:
        """Re-arm a recurring session for its next fire when still within bounds."""
        self.ensure_one()
        if self.state != 'done':
            return
        cfg = self.recur_config or {}
        try:
            every_seconds = int(cfg.get('every') or 0)
            max_runs = int(cfg['max_runs']) if cfg.get('max_runs') else None
            until_dt = (
                fields.Datetime.from_string(cfg['until']) if cfg.get('until') else None
            )
        except (TypeError, ValueError):
            return
        runs_done = self.recur_runs_done or 0
        if every_seconds <= 0 or (max_runs and runs_done >= max_runs):
            return
        now = fields.Datetime.now()
        new_resume_at = now + timedelta(seconds=every_seconds)
        if until_dt and (now >= until_dt or new_resume_at > until_dt):
            return
        next_runs = runs_done + 1
        self.write(
            {
                'state': 'schedule',
                'resume_at': new_resume_at,
                'recur_runs_done': next_runs,
            }
        )
        self._publish_event(
            'state',
            {
                'state': 'schedule',
                'resume_at': fields.Datetime.to_string(new_resume_at),
                'recur_runs_done': next_runs,
            },
        )

    def _resolve_resume_prompt(self) -> str:
        """Return the prompt to inject on resume, rendering recurrence placeholders."""
        self.ensure_one()
        if self.resume_prompt:
            return self.resume_prompt
        cfg = self.recur_config or {}
        if not (recur_prompt := cfg.get('prompt') or ''):
            return ''
        try:
            total = str(int(cfg['max_runs'])) if cfg.get('max_runs') else '∞'
        except (TypeError, ValueError):
            total = '∞'
        run = str(self.recur_runs_done or 1)
        return recur_prompt.replace('{run}', run).replace('{total}', total)

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_chain_session_count(self) -> None:
        """Count every session reachable in each record's chain."""
        for record in self:
            record.chain_session_count = len(record._chain_session_ids())

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> AISession:
        """Cross-link sessions to their schedule and inherited owned action."""
        Schedule = self.env['muk_ai.schedule'].sudo()
        for vals in vals_list:
            if vals.get('schedule_id') and not vals.get('action_server_id'):
                schedule = Schedule.browse(vals['schedule_id'])
                if schedule.action_server_id:
                    vals['action_server_id'] = schedule.action_server_id.id
                continue
            if vals.get('schedule_id') or not vals.get('action_server_id'):
                continue
            schedule = Schedule.search(
                [('action_server_id', '=', vals['action_server_id'])],
                limit=1,
            )
            if schedule:
                vals['schedule_id'] = schedule.id
        return super().create(vals_list)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_run_pending_sessions(self) -> None:
        """Reactivate due scheduled sessions before the base cron sweep."""
        self._reactivate_due_schedules()
        return super()._cron_run_pending_sessions()

    @api.model
    def _reactivate_due_schedules(self) -> None:
        """Wake every scheduled session whose resume time has elapsed."""
        due = self.sudo().search(
            [
                ('state', '=', 'schedule'),
                ('resume_at', '!=', False),
                ('resume_at', '<=', fields.Datetime.now()),
            ]
        )
        for session in due:
            prompt = session._resolve_resume_prompt()
            session.write(
                {'resume_at': False, 'claimed_at': False, 'resume_prompt': False}
            )
            if prompt:
                session._enqueue_user_turn(prompt, [])
            else:
                session.write(session._turn_start_values())
                session._publish_event('state', {'state': 'running'})
        if due and not config['test_enable']:
            self.env.cr.commit()

    @api.model
    def _find_pending_session_ids(self, limit: int | None = None) -> list[int]:
        """Extend the pending pickup set with due scheduled sessions."""
        super_kwargs = {} if limit is None else {'limit': limit}
        ids = list(super()._find_pending_session_ids(**super_kwargs))
        due = self.sudo().search(
            [
                ('state', '=', 'schedule'),
                ('resume_at', '!=', False),
                ('resume_at', '<=', fields.Datetime.now()),
            ],
            order='resume_at',
            limit=SCHEDULE_PICKUP_LIMIT,
        )
        for sid in due.ids:
            if sid not in ids:
                ids.append(sid)
        return ids
