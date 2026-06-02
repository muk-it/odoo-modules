from collections import defaultdict
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import MissingError
from odoo.tools import OrderedSet, config

from odoo.addons.muk_ai.tools import with_record_ctx
from odoo.addons.muk_ai_schedule.tools.constants import (
    SCHEDULE_PICKUP_LIMIT,
    SCHEDULE_TERMINATING_TOOLS,
)
from odoo.addons.muk_ai_schedule.tools.dispatch import PreviousProxy, _resolve_records


class AISession(models.Model):

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    schedule_id = fields.Many2one(
        comodel_name='muk_ai.schedule',
        string="Schedule",
        help="Schedule that spawned this session (null for interactive sessions).",
        index=True,
        copy=False,
        ondelete='set null',
    )

    previous_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string="Previous Session",
        help="Prior session in the schedule's chain.",
        copy=False,
        ondelete='set null',
    )

    res_model = fields.Char(
        string="Linked Model",
        help="Model of the business record this session is linked to.",
        index=True,
        copy=False,
    )

    res_id = fields.Many2oneReference(
        model_field='res_model',
        string="Linked Record",
        help="Identifier of the linked business record.",
        copy=False,
    )

    resume_at = fields.Datetime(
        string="Resume At",
        help="Wall-clock time at which the session is due to resume.",
        readonly=True,
        index=True,
        copy=False,
    )

    recur_config = fields.Json(
        string="Recurrence Config",
        help="Persisted schedule_recurring args: {every, until, max_runs}.",
        readonly=True,
        copy=False,
    )

    recur_runs_done = fields.Integer(
        string="Recurrence Runs Done",
        help="How many recur fires this session has executed.",
        readonly=True,
        default=0,
        copy=False,
    )

    resume_prompt = fields.Text(
        string="Resume Prompt",
        help="Synthetic user message injected on next resume.",
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        selection_add=[
            ('schedule', "Scheduled"),
        ],
        ondelete={'schedule': 'set default'},
    )

    chain_session_count = fields.Integer(
        compute='_compute_chain_session_count',
        string="Chain Sessions",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _linked_record(self):
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return None
        record = self.env[self.res_model].sudo().browse(self.res_id)
        return record if record.exists() else None

    def _build_request_inputs(self):
        inputs = super()._build_request_inputs()
        if record := self._linked_record():
            inputs = with_record_ctx(inputs, {
                'kind': 'record',
                'model': record._name,
                'id': record.id,
                'display_name': record.display_name,
            })
        return inputs

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        # Note: Odoo 18 BaseModel._search() has no active_test/bypass_access
        # keyword arguments (added in 19). active_test is taken from context;
        # rules are bypassed by searching as superuser (sudo).
        if self.env.su or self.env.is_admin():
            return super()._search(domain, offset=offset, limit=limit, order=order)
        candidate_query = super(AISession, self.sudo())._search(domain, order=order)
        candidate_ids = list(candidate_query)
        if not candidate_ids:
            return candidate_query
        accessible = self.browse(candidate_ids)._filtered_access('read')
        return super(AISession, self.sudo())._search(
            [('id', 'in', list(accessible._ids))],
            offset=offset, limit=limit, order=order,
        )

    def _check_access(self, operation):
        res = super()._check_access(operation)
        if operation != 'read' or self.env.su or self.env.is_admin() or not self:
            return res
        if not res:
            return res
        forbidden, error_func = res
        forbidden_ids = OrderedSet(forbidden._ids)
        sudo_self = self.sudo().browse(forbidden_ids)
        sudo_self.fetch(['user_id', 'res_model', 'res_id'])
        uid = self.env.uid
        by_model = defaultdict(set)
        session_links = {}
        for session in sudo_self:
            if session.user_id.id == uid:
                forbidden_ids.discard(session.id)
                continue
            if session.res_model and session.res_id and session.res_model in self.env:
                by_model[session.res_model].add(session.res_id)
                session_links[session.id] = (session.res_model, session.res_id)
        granted_pairs = set()
        for res_model, res_ids in by_model.items():
            records = self.env[res_model].browse(list(res_ids))
            try:
                allowed = records._filtered_access('read')
            except MissingError:
                allowed = records.exists()._filtered_access('read')
            for rec_id in allowed._ids:
                granted_pairs.add((res_model, rec_id))
        for sid, key in session_links.items():
            if key in granted_pairs:
                forbidden_ids.discard(sid)
        if forbidden_ids:
            return self.browse(forbidden_ids), error_func
        return None

    def _chain_session_ids(self):
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
            if record.previous_session_id and record.previous_session_id.id not in visited:
                stack.append(record.previous_session_id.id)
            stack.extend(
                child.id
                for child in Session.search([('previous_session_id', '=', sid)])
                if child.id not in visited
            )
        return visited

    def _session_prompt_extras(self):
        extras = super()._session_prompt_extras()
        empty = self.env['base'].browse([])
        record, records, previous = empty, empty, PreviousProxy(None)
        if self and self.id:
            linked = self._linked_record()
            if linked is not None:
                record = linked
            previous = PreviousProxy(self.previous_session_id or None)
            schedule = self.schedule_id
            if schedule and schedule.dispatch_mode == 'single':
                records = _resolve_records(schedule)
        extras.update({
            'now': fields.Datetime.now(),
            'record': record,
            'records': records,
            'previous_session': previous,
        })
        return extras

    def _post_chatter_mirror(self):
        record = self._linked_record()
        if record is None or not hasattr(record, 'message_post'):
            return
        link = Markup(
            '<a href="/odoo/action-muk_ai.action_ai_session/{sid}">{label}</a>'
        ).format(sid=self.id, label=self.display_name or _('AI Session'))
        body = Markup('<p>%s</p>') % _(
            "AI session %(link)s started for this record.", link=link,
        )
        try:
            record.message_post(body=body, subtype_xmlid='mail.mt_note')
        except Exception:
            pass

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_chain(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Session Chain"),
            'res_model': 'muk_ai.session',
            'view_mode': 'list,form',
            'domain': [('id', 'in', sorted(self._chain_session_ids()))],
            'context': {},
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _get_terminating_tools(self):
        return super()._get_terminating_tools() | SCHEDULE_TERMINATING_TOOLS

    def _run_to_completion(self, has_terminating=False):
        super()._run_to_completion(has_terminating=has_terminating)
        for record in self:
            record._auto_redefer_recurring()

    def _auto_redefer_recurring(self):
        self.ensure_one()
        if self.state != 'done':
            return
        cfg = self.recur_config or {}
        try:
            every_seconds = int(cfg.get('every') or 0)
            max_runs = int(cfg['max_runs']) if cfg.get('max_runs') else None
            until_dt = fields.Datetime.from_string(cfg['until']) if cfg.get('until') else None
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
        self.write({
            'state': 'schedule',
            'resume_at': new_resume_at,
            'recur_runs_done': next_runs,
        })
        self._publish_event('state', {
            'state': 'schedule',
            'resume_at': fields.Datetime.to_string(new_resume_at),
            'recur_runs_done': next_runs,
        })

    def _resolve_resume_prompt(self):
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

    def _compute_chain_session_count(self):
        for record in self:
            record.chain_session_count = len(record._chain_session_ids())

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.res_model and record.res_id:
                record._post_chatter_mirror()
        return records

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_run_pending_sessions(self):
        self._reactivate_due_schedules()
        return super()._cron_run_pending_sessions()

    @api.model
    def _reactivate_due_schedules(self):
        due = self.sudo().search([
            ('state', '=', 'schedule'),
            ('resume_at', '!=', False),
            ('resume_at', '<=', fields.Datetime.now()),
        ])
        for session in due:
            prompt = session._resolve_resume_prompt()
            session.write({'resume_at': False, 'claimed_at': False, 'resume_prompt': False})
            if prompt:
                session._enqueue_user_turn(prompt, [])
            else:
                session.write({'state': 'running'})
                session._publish_event('state', {'state': 'running'})
        if due and not config['test_enable']:
            self.env.cr.commit()

    @api.model
    def _find_pending_session_ids(self, limit=None):
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
