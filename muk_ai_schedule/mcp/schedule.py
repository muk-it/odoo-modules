from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool

from odoo.addons.muk_ai_schedule.tools.constants import (
    DEFAULT_MAX_COST_EUR,
    DEFAULT_MAX_LIFETIME_HOURS,
    DEFAULT_MAX_RESUMES,
    DEFAULT_MAX_TOTAL_TOKENS,
    MAX_DELAY_SECONDS,
    MAX_PROMPT_CHARS,
    MIN_DELAY_SECONDS,
)
from odoo.addons.muk_ai_schedule.tools.dispatch import post_session_event


class ScheduleToolsMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_schedule_session(self):
        if not (session_id := self.env.context.get('muk_mcp_session_id')):
            raise UserError(_("Schedule tools can only be invoked from inside an AI session."))
        session = self.env['muk_ai.session'].sudo().browse(session_id)
        if not session.exists():
            raise UserError(_("Session %(sid)s no longer exists.", sid=session_id))
        return session

    def _schedule_effective_caps(self, session):
        if session.schedule_id:
            return session.schedule_id._effective_caps()
        return {
            'max_resumes': DEFAULT_MAX_RESUMES,
            'max_lifetime_hours': DEFAULT_MAX_LIFETIME_HOURS,
            'max_total_tokens': DEFAULT_MAX_TOTAL_TOKENS,
            'max_cost_eur': DEFAULT_MAX_COST_EUR,
        }

    def _schedule_abort_with_cap(self, session, cap, limit, observed):
        post_session_event(session, 'cap_exceeded', {
            'cap': cap, 'limit': limit, 'observed': observed,
        })
        session.write({
            'state': 'error',
            'error_message': _(
                "Cap exceeded (%(cap)s: %(observed)s/%(limit)s).",
                cap=cap, observed=observed, limit=limit,
            ),
        })

    def _schedule_check_resume_cap(self, session, runs_done):
        caps = self._schedule_effective_caps(session)
        elapsed = (
            (fields.Datetime.now() - session.create_date).total_seconds() / 3600.0
            if session.create_date else 0.0
        )
        used_tokens = (session.total_input_tokens or 0) + (session.total_output_tokens or 0)
        used_cost = session.total_cost or 0.0
        checks = [
            ('max_resumes', DEFAULT_MAX_RESUMES, runs_done, runs_done),
            ('max_lifetime_hours', DEFAULT_MAX_LIFETIME_HOURS, elapsed, round(elapsed, 2)),
            ('max_total_tokens', DEFAULT_MAX_TOTAL_TOKENS, used_tokens, used_tokens),
            ('max_cost_eur', DEFAULT_MAX_COST_EUR, used_cost, round(used_cost, 4)),
        ]
        for cap, default, observed, reported in checks:
            limit = caps.get(cap) or default
            if observed >= limit:
                self._schedule_abort_with_cap(session, cap, limit, reported)
                return False
        return True

    def _schedule_validate_prompt(self, prompt):
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise UserError(_("'prompt' is required and must be non-empty."))
        if len(prompt) > MAX_PROMPT_CHARS:
            raise UserError(_(
                "'prompt' is too long (%(got)s chars, max %(max)s).",
                got=len(prompt), max=MAX_PROMPT_CHARS,
            ))

    def _schedule_validate_delay(self, seconds):
        if seconds < MIN_DELAY_SECONDS:
            raise UserError(_(
                "Delay must be at least %(min)s seconds (got %(got)s).",
                min=MIN_DELAY_SECONDS, got=int(seconds),
            ))
        if seconds > MAX_DELAY_SECONDS:
            raise UserError(_(
                "Delay must be at most %(max)s seconds (got %(got)s).",
                max=MAX_DELAY_SECONDS, got=int(seconds),
            ))

    def _schedule_resolve_resume_at(self, at, seconds_from_now):
        if (at is None) == (seconds_from_now is None):
            raise UserError(_("Provide exactly one of 'at' or 'seconds_from_now'."))
        now = fields.Datetime.now()
        if seconds_from_now is not None:
            try:
                seconds = int(seconds_from_now)
            except (TypeError, ValueError):
                raise UserError(_("'seconds_from_now' must be an integer."))
            self._schedule_validate_delay(seconds)
            return now + timedelta(seconds=seconds)
        try:
            resume_at = fields.Datetime.from_string(at)
        except (TypeError, ValueError):
            resume_at = None
        if resume_at is None:
            raise UserError(_("'at' must be an ISO 8601 datetime (got %(value)r).", value=at))
        self._schedule_validate_delay((resume_at - now).total_seconds())
        return resume_at

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='schedule_resume',
        description=(
            "Pause the current AI session and resume it later at a specific "
            "wall-clock time. Use this when you have to wait for an external "
            "event, a human reply, or a future date. The session enters the "
            "'schedule' state and a cron worker picks it up once the resume "
            "time elapses. Provide exactly one of 'at' (ISO 8601 datetime) "
            "or 'seconds_from_now' (integer, 60..2592000)."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'at': {
                    'type': 'string',
                    'description': "ISO 8601 datetime to resume at. 60s to 30 days in the future.",
                },
                'seconds_from_now': {
                    'type': 'integer',
                    'description': "Seconds from now until resume. 60 to 2592000.",
                },
                'prompt': {
                    'type': 'string',
                    'description': (
                        "Instruction injected as a synthetic user message on resume. "
                        "Required. Tell yourself what to do on wake-up so you don't "
                        "resume to stale context."
                    ),
                },
            },
            'required': ['prompt'],
        },
        category='write',
        registry='odoo',
    )
    def _mcp_schedule_resume(self, at=None, seconds_from_now=None, prompt=None):
        session = self._resolve_schedule_session()
        self._schedule_validate_prompt(prompt)
        runs_done = (session.recur_runs_done or 0) + 1
        if not self._schedule_check_resume_cap(session, runs_done - 1):
            return {'ok': False, 'error': 'cap_exceeded', 'cap': 'max_resumes'}
        resume_at = self._schedule_resolve_resume_at(at, seconds_from_now)
        session.write({
            'resume_at': resume_at,
            'state': 'schedule',
            'recur_runs_done': runs_done,
            'resume_prompt': prompt,
        })
        session._publish_event('state', {
            'state': 'schedule',
            'resume_at': fields.Datetime.to_string(resume_at),
        })
        return {'ok': True, 'resume_at': fields.Datetime.to_string(resume_at)}

    @api.model
    @mcp_tool(
        name='schedule_recurring',
        description=(
            "Pause the current AI session and have it run again on a fixed "
            "cadence. Use this for recurring digests or watch loops. The "
            "session enters the 'schedule' state and the cron worker fires "
            "it every 'every' seconds (60..2592000). Provide exactly one of "
            "'until' (ISO 8601 stop time) or 'max_runs' (positive integer). "
            "The first call counts as run 1."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'every': {
                    'type': 'integer',
                    'description': "Seconds between fires. 60 to 2592000.",
                },
                'until': {
                    'type': 'string',
                    'description': "ISO 8601 datetime after which no further fires occur.",
                },
                'max_runs': {
                    'type': 'integer',
                    'description': "Maximum total fires (initial call counts as 1).",
                },
                'prompt': {
                    'type': 'string',
                    'description': (
                        "Instruction injected on every fire. Required. Use {run} "
                        "and {total} for the current fire number and total "
                        "(or '∞' if unbounded). Stray braces are preserved."
                    ),
                },
            },
            'required': ['every', 'prompt'],
        },
        category='write',
        registry='odoo',
    )
    def _mcp_schedule_recurring(self, every=None, until=None, max_runs=None, prompt=None):
        session = self._resolve_schedule_session()
        self._schedule_validate_prompt(prompt)
        if every is None:
            raise UserError(_("'every' is required."))
        try:
            every_seconds = int(every)
        except (TypeError, ValueError):
            raise UserError(_("'every' must be an integer."))
        self._schedule_validate_delay(every_seconds)
        if (until is None) == (max_runs is None):
            raise UserError(_("Provide exactly one of 'until' or 'max_runs'."))
        now = fields.Datetime.now()
        until_dt = None
        if until is not None:
            try:
                until_dt = fields.Datetime.from_string(until)
            except (TypeError, ValueError):
                raise UserError(_("'until' must be an ISO 8601 datetime (got %(value)r).", value=until))
            if until_dt is None or until_dt <= now:
                raise UserError(_("'until' must be in the future."))
        max_runs_int = None
        if max_runs is not None:
            try:
                max_runs_int = int(max_runs)
            except (TypeError, ValueError):
                raise UserError(_("'max_runs' must be an integer."))
            if max_runs_int <= 0:
                raise UserError(_("'max_runs' must be positive."))
        existing_config = session.recur_config or {}
        existing_max_runs = existing_config.get('max_runs')
        runs_done = (session.recur_runs_done or 0) + 1
        if existing_max_runs and runs_done > int(existing_max_runs):
            self._schedule_abort_with_cap(
                session, 'recur_max_runs', int(existing_max_runs), runs_done - 1,
            )
            return {'ok': False, 'error': 'cap_exceeded', 'cap': 'recur_max_runs'}
        if not self._schedule_check_resume_cap(session, runs_done - 1):
            return {'ok': False, 'error': 'cap_exceeded', 'cap': 'max_resumes'}
        resume_at = now + timedelta(seconds=every_seconds)
        session.write({
            'resume_at': resume_at,
            'state': 'schedule',
            'recur_config': {
                'every': every_seconds,
                'until': fields.Datetime.to_string(until_dt) if until_dt else None,
                'max_runs': max_runs_int or existing_max_runs,
                'started_at': existing_config.get('started_at') or fields.Datetime.to_string(now),
                'prompt': prompt,
            },
            'recur_runs_done': runs_done,
        })
        session._publish_event('state', {
            'state': 'schedule',
            'resume_at': fields.Datetime.to_string(resume_at),
            'recur_runs_done': runs_done,
        })
        return {
            'ok': True,
            'resume_at': fields.Datetime.to_string(resume_at),
            'runs_done': runs_done,
        }
