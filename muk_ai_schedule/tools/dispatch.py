from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, fields
from odoo.exceptions import UserError
from odoo.tools import safe_eval


class PreviousProxy:

    __slots__ = ('_session',)

    def __init__(self, session):
        self._session = session

    @property
    def last_text(self):
        return (self._session.last_text or '') if self._session else ''

    @property
    def tool_log(self):
        if not self._session:
            return []
        return [
            {
                'name': log.name or '',
                'arguments': log.arguments or {},
                'output': log.output or {},
            }
            for log in self._session.log_ids
        ]


def post_session_event(session, kind, payload):
    Event = session.env['muk_ai.session.event'].sudo()
    last = Event.search(
        [('session_id', '=', session.id)], order='sequence desc', limit=1,
    )
    Event.create({
        'session_id': session.id,
        'sequence': (last.sequence + 1) if last else 0,
        'kind': kind,
        'payload': payload,
    })


def _resolve_records(schedule):
    if not schedule.model_id or schedule.model_id.model not in schedule.env:
        return schedule.env['base'].browse([])
    Model = schedule.env[schedule.model_id.model].sudo()
    if schedule.record_source == 'code':
        code = (schedule.record_code or '').strip()
        if not code:
            return Model.browse([])
        eval_ctx = {
            'env': schedule.env,
            'now': fields.Datetime.now(),
            'today': fields.Date.context_today(schedule),
            'datetime': datetime, 'date': date, 'time': time,
            'timedelta': timedelta, 'relativedelta': relativedelta,
        }
        try:
            # nocopy=True so the `records = ...` assignment lands back in
            # eval_ctx (Odoo 18 safe_eval copies globals_dict by default,
            # which would otherwise discard the result). Also the recommended
            # mode when passing a live `env` in the context.
            safe_eval.safe_eval(code, eval_ctx, mode='exec', nocopy=True)
        except Exception:
            return Model.browse([])
        result = eval_ctx.get('records')
        if isinstance(result, type(Model)):
            return result.sudo()
        return Model.browse([])
    try:
        domain = safe_eval.safe_eval(schedule.domain or '[]', {'env': schedule.env}) or []
    except Exception:
        return Model.browse([])
    return Model.search(domain)


def _resolve_previous_session(schedule, res_model=None, res_id=None):
    Session = schedule.env['muk_ai.session'].sudo()
    domain = [('schedule_id', '=', schedule.id)]
    if res_model and res_id:
        domain += [('res_model', '=', res_model), ('res_id', '=', res_id)]
    else:
        domain += [('res_model', '=', False)]
    return Session.search(domain, order='create_date desc', limit=1)


def _create_session(schedule, prompt_text, render_err, res_model=None, res_id=None, previous_session=None):
    vals = {
        'name': schedule.name,
        'agent_id': schedule.agent_id.id,
        'schedule_id': schedule.id,
        'previous_session_id': previous_session.id if previous_session else False,
    }
    if res_model and res_id:
        vals['res_model'] = res_model
        vals['res_id'] = res_id
    session = schedule.env['muk_ai.session'].sudo().with_user(schedule.user_id).create(vals)
    if render_err:
        post_session_event(session, 'prompt_render_error', {'error': render_err})
    try:
        session.start(prompt_text or '')
    except Exception as exc:
        session.write({
            'state': 'error',
            'error_message': str(exc) or _("Session start failed."),
        })
    return session


def fire_schedule(schedule):
    schedule.ensure_one()
    if not schedule.agent_id or not schedule.agent_id.active:
        raise UserError(_(
            "Schedule %(name)s has no active agent.",
            name=schedule.display_name,
        ))
    Session = schedule.env['muk_ai.session']
    empty = schedule.env['base'].browse([])
    if schedule.dispatch_mode == 'per_record':
        records = _resolve_records(schedule)
        cap = max(int(schedule.max_records_per_fire or 0), 0)
        if cap:
            records = records[:cap]
        targets = [(record, empty, record._name, record.id) for record in records]
    else:
        targets = [(empty, _resolve_records(schedule), None, None)]
    spawned = Session.browse([])
    for record, records, res_model, res_id in targets:
        previous = _resolve_previous_session(
            schedule, res_model=res_model, res_id=res_id,
        )
        prompt_text, render_err = schedule._build_prompt(
            record=record,
            records=records,
            previous_session=PreviousProxy(previous or None),
        )
        spawned |= _create_session(
            schedule, prompt_text, render_err,
            res_model=res_model, res_id=res_id, previous_session=previous,
        )
    now = fields.Datetime.now()
    schedule.sudo().write({'last_call': now})
    schedule.sudo()._recompute_next_call(base=now)
    return spawned
