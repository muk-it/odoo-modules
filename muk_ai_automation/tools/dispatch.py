from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import safe_eval

from odoo.addons.muk_ai_automation.tools.constants import MAX_PROMPT_CHARS


class PreviousProxy:
    """Read-only view of a prior session for inline prompt rendering."""

    __slots__ = ('_session',)

    def __init__(self, session: models.BaseModel | None) -> None:
        """Wrap a prior session recordset, or ``None`` when there is none."""
        self._session = session

    @property
    def last_text(self) -> str:
        """Return the last assistant text of the wrapped session."""
        return (self._session.last_text or '') if self._session else ''

    @property
    def tool_log(self) -> list[dict]:
        """Return the wrapped session tool log as plain dictionaries."""
        if not self._session:
            return []
        return [
            {
                'name': log.tool_name or '',
                'arguments': self._decode(log.request_data),
                'output': self._decode(log.response_data),
            }
            for log in self._session.log_ids
        ]

    @staticmethod
    def _decode(value: str | None) -> object:
        """Return ``value`` parsed as JSON, or the raw text when not JSON."""
        if not value:
            return ''
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value


def post_session_event(session: models.BaseModel, kind: str, payload: dict) -> None:
    """Append a sequenced event of ``kind`` to ``session``."""
    Event = session.env['muk_ai.session.event'].sudo()
    last = Event.search(
        [('session_id', '=', session.id)],
        order='sequence desc',
        limit=1,
    )
    Event.create(
        {
            'session_id': session.id,
            'sequence': (last.sequence + 1) if last else 0,
            'kind': kind,
            'payload': payload,
        }
    )


def _resolve_target_model(
    action: models.BaseModel, eval_context: dict | None
) -> models.BaseModel | None:
    """Return the sudo target model from the action context or model_id."""
    eval_context = eval_context or {}
    env_ctx = action.env.context
    active_model = env_ctx.get('active_model')
    if active_model and active_model in action.env:
        return action.env[active_model].sudo()
    if action.model_id and action.model_id.model in action.env:
        return action.env[action.model_id.model].sudo()
    return None


def _resolve_records_from_context(
    action: models.BaseModel, eval_context: dict | None
) -> models.BaseModel | None:
    """Resolve target records from the eval context or the active ids."""
    eval_context = eval_context or {}
    records_ctx = eval_context.get('records')
    if records_ctx:
        return records_ctx.sudo()
    record_ctx = eval_context.get('record')
    if record_ctx:
        return record_ctx.sudo()
    Model = _resolve_target_model(action, eval_context)
    if Model is None:
        return None
    env_ctx = action.env.context
    active_ids = env_ctx.get('active_ids')
    if active_ids:
        return Model.browse(active_ids).exists()
    active_id = env_ctx.get('active_id')
    if active_id:
        return Model.browse([active_id]).exists()
    return None


def _resolve_records(
    action: models.BaseModel, eval_context: dict | None = None
) -> models.BaseModel:
    """Resolve the recordset the action targets via context, code, or domain."""
    eval_context = eval_context or {}
    from_ctx = _resolve_records_from_context(action, eval_context)
    if from_ctx is not None:
        return from_ctx
    Model = _resolve_target_model(action, eval_context)
    if Model is None:
        return action.env['base'].browse([])
    if action.agent_record_source == 'code':
        code = (action.agent_record_code or '').strip()
        if not code:
            return Model.browse([])
        eval_ctx = {
            'env': action.env,
            'now': fields.Datetime.now(),
            'today': fields.Date.context_today(action),
            'datetime': datetime,
            'date': date,
            'time': time,
            'timedelta': timedelta,
            'relativedelta': relativedelta,
        }
        try:
            safe_eval.safe_eval(code, eval_ctx, mode='exec')
        except Exception:  # noqa: BLE001 — invalid user code yields no records
            return Model.browse([])
        result = eval_ctx.get('records')
        if isinstance(result, type(Model)):
            return result.sudo()
        return Model.browse([])
    try:
        domain = (
            safe_eval.safe_eval(
                action.agent_record_domain or '[]',
                {'env': action.env},
            )
            or []
        )
    except Exception:  # noqa: BLE001 — invalid user domain yields no records
        return Model.browse([])
    return Model.search(domain)


def _resolve_previous_session(
    action: models.BaseModel,
    res_model: str | None = None,
    res_id: int | None = None,
) -> models.BaseModel:
    """Return the prior chained session for a record, or an empty recordset."""
    if action.agent_chain_strategy != 'per_record':
        return action.env['muk_ai.session'].sudo().browse([])
    Session = action.env['muk_ai.session'].sudo()
    if not (res_model and res_id):
        return Session.browse([])
    return Session.search(
        [
            ('action_server_id', '=', action.id),
            ('res_model', '=', res_model),
            ('res_id', '=', res_id),
        ],
        order='create_date desc',
        limit=1,
    )


def _build_prompt(
    action: models.BaseModel,
    record: models.BaseModel,
    records: models.BaseModel,
    previous_session: models.BaseModel | None,
) -> tuple[str, str | None]:
    """Render the action prompt template against the dispatch scope.

    The rendered prompt is truncated to ``MAX_PROMPT_CHARS`` to bound the
    token cost of an unbounded template against a large recordset.
    """
    raw = action.agent_prompt or ''
    Mixin = action.env['muk_ai.prompt.mixin']
    prompt, render_err = Mixin._render_prompt_safe(
        raw,
        record=record,
        records=records,
        previous_session=PreviousProxy(previous_session or None),
    )
    if prompt and len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS] + ' …[truncated]'
    return prompt, render_err


def _spawn_user(action: models.BaseModel) -> models.BaseModel:
    """Return the user the session runs as, falling back to the admin user."""
    user = action.create_uid
    if not user or not user.active:
        return action.env.ref('base.user_admin')
    return user


def _create_session(
    action: models.BaseModel,
    prompt_text: str,
    render_err: str | None,
    res_model: str | None = None,
    res_id: int | None = None,
    previous_session: models.BaseModel | None = None,
) -> models.BaseModel:
    """Create and start a session for the action, recording render errors."""
    vals = {
        'name': action.name,
        'agent_id': action.agent_id.id,
        'action_server_id': action.id,
        'previous_session_id': previous_session.id if previous_session else False,
    }
    if res_model and res_id:
        vals['res_model'] = res_model
        vals['res_id'] = res_id
    user = _spawn_user(action)
    session = action.env['muk_ai.session'].sudo().with_user(user).create(vals)
    if render_err:
        post_session_event(session, 'prompt_render_error', {'error': render_err})
    try:
        session.start(prompt_text or '')
    except Exception as exc:  # noqa: BLE001 — surface start failures on the session
        session.write(
            {
                'state': 'error',
                'error_message': str(exc) or _('Session start failed.'),
            }
        )
    return session


def fire_action(action: models.BaseModel, eval_context: dict) -> models.BaseModel:
    """Spawn agent sessions for the action across its dispatch targets."""
    action.ensure_one()
    if not action.agent_id or not action.agent_id.active:
        raise UserError(
            _(
                'Server action %(name)s has no active agent.',
                name=action.display_name,
            )
        )
    Session = action.env['muk_ai.session']
    empty = action.env['base'].browse([])
    eval_context = eval_context or {}
    if action.agent_dispatch_mode == 'per_record':
        records = _resolve_records(action, eval_context)
        cap = max(int(action.agent_max_records_per_fire or 0), 0)
        if cap:
            records = records[:cap]
        targets = [(record, empty, record._name, record.id) for record in records]
    else:
        records = _resolve_records(action, eval_context)
        targets = [(empty, records, None, None)]
    spawned = Session.browse([])
    for record, records, res_model, res_id in targets:
        previous = _resolve_previous_session(
            action,
            res_model=res_model,
            res_id=res_id,
        )
        prompt_text, render_err = _build_prompt(
            action,
            record=record,
            records=records,
            previous_session=previous,
        )
        spawned |= _create_session(
            action,
            prompt_text,
            render_err,
            res_model=res_model,
            res_id=res_id,
            previous_session=previous,
        )
    eval_context['__agent_spawned__'] = spawned.ids
    return spawned
