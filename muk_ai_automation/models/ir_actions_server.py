from __future__ import annotations

from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import clean_context
from odoo.tools.safe_eval import safe_eval, test_python_expr

from odoo.addons.muk_ai_automation.tools.prompt import MAX_PROMPT_CHARS, PreviousProxy


class IrActionsServer(models.Model):
    """Add the ``ai_agent`` server-action state firing an AI agent."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    def _default_agent_id(self) -> models.BaseModel:
        """Return the default agent for an action created as an agent action."""
        if self.env.context.get('default_state') == 'ai_agent':
            return self.env['muk_ai.agent']._get_default()
        return self.env['muk_ai.agent']

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[('ai_agent', 'Run AI Agent')],
        ondelete={'ai_agent': lambda actions: actions._unlink_agent_actions()},
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Agent',
        default=lambda self: self._default_agent_id(),
        ondelete='restrict',
    )

    agent_prompt = fields.Text(
        string='Prompt',
        help=(
            'Message sent to the agent on each run, rendered as an inline '
            'template with record, records, previous_session, env, user and '
            'today.'
        ),
        translate=True,
    )

    agent_dispatch_mode = fields.Selection(
        selection=[
            ('single', 'One Chat'),
            ('per_record', 'One Chat per Record'),
        ],
        string='Dispatch',
        help=(
            'One Chat hands all target records to a single chat; One Chat per '
            'Record starts a chat for each record, linked to it.'
        ),
        default='single',
    )

    agent_record_source = fields.Selection(
        selection=[
            ('domain', 'Domain'),
            ('code', 'Python Code'),
        ],
        string='Records',
        help=(
            'Where the target records come from when the trigger provides '
            'none, as on a scheduled or manual run.'
        ),
        default='domain',
    )

    agent_record_domain = fields.Char(
        string='Record Domain',
        help='Filter selecting the target records of the action model.',
        default='[]',
    )

    agent_record_code = fields.Text(
        string='Record Code',
        help=(
            'Python code assigning the target recordset to "records", with '
            'env, now, today, datetime, date, time, timedelta and relativedelta.'
        ),
    )

    agent_max_records_per_fire = fields.Integer(
        string='Record Limit',
        help='Most records one run starts a chat for. Zero means no limit.',
        default=100,
    )

    agent_chain_strategy = fields.Selection(
        selection=[
            ('none', 'Start Fresh'),
            ('per_record', 'Continue per Record'),
        ],
        string='Memory',
        help=(
            'Continue per Record hands each chat the previous chat of this '
            'action for the same record, as previous_session in the prompt.'
        ),
        default='none',
    )

    agent_space_id = fields.Many2one(
        comodel_name='muk_ai.space',
        string='Space',
        help=(
            'System space that lists the chats of this action. Leave empty to '
            'list them under Automation, or under Scheduled for a scheduled action.'
        ),
        domain=[('user_id', '=', False)],
        ondelete='set null',
    )

    agent_session_count = fields.Integer(
        compute='_compute_agent_session_count',
        string='AI Chats',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _unlink_agent_actions(self) -> None:
        """Delete agent actions together with the scheduled actions that run them."""
        self.env['ir.cron'].with_context(active_test=False).search(
            [('ir_actions_server_id', 'in', self.ids)]
        ).unlink()
        self.exists().unlink()

    def _agent_user(self) -> models.BaseModel:
        """Return the user the chats run as: the user of its rule, else the runner.

        The administrator stands in for the superuser.

        :raise UserError: when that user is archived or not set
        """
        rule = self.sudo().base_automation_id
        user = rule.agent_user_id if rule else self.env.user
        if user.id == SUPERUSER_ID:
            return self.env.ref('base.user_admin')
        if not user.active:
            raise UserError(
                self.env._(
                    'Server action %(name)s cannot run: the user it runs as is '
                    'archived or not set.',
                    name=self.display_name,
                )
            )
        return user

    def _agent_records(self, eval_context: dict) -> models.BaseModel:
        """Return the records of the trigger, else those of the domain or code."""
        if records := eval_context['records'] or eval_context['record']:
            return records.sudo()
        model = eval_context['model'].sudo()
        if self.agent_record_source == 'domain':
            return model.search(
                safe_eval(self.agent_record_domain or '[]', {'env': self.env})
            )
        scope = {
            'env': self.env,
            'now': fields.Datetime.now(),
            'today': fields.Date.context_today(self),
            'datetime': datetime,
            'date': date,
            'time': time,
            'timedelta': timedelta,
            'relativedelta': relativedelta,
        }
        safe_eval(self.agent_record_code or '', scope, mode='exec', nocopy=True)
        records = scope.get('records')
        if isinstance(records, models.BaseModel):
            return records.sudo()
        return model.browse()

    def _agent_previous_session(self, record: models.BaseModel) -> models.BaseModel:
        """Return the last chat this action ran for ``record`` when it chains."""
        sessions = self.env['muk_ai.session'].sudo()
        if self.agent_chain_strategy != 'per_record' or not record:
            return sessions
        return sessions.search(
            [
                ('action_server_id', '=', self.id),
                ('res_model', '=', record._name),
                ('res_id', '=', record.id),
            ],
            order='id desc',
            limit=1,
        )

    def _agent_start_session(
        self, record: models.BaseModel, records: models.BaseModel
    ) -> models.BaseModel:
        """Create a chat for one run and send it the rendered prompt.

        A prompt that does not render fails the chat instead of sending it.
        """
        previous = self._agent_previous_session(record)
        prompt, error = self.env['muk_ai.prompt.mixin']._render_prompt_safe(
            self.agent_prompt or '',
            record=record,
            records=records,
            previous_session=PreviousProxy(previous),
        )
        if len(prompt) > MAX_PROMPT_CHARS:
            prompt = (
                f'{prompt[:MAX_PROMPT_CHARS]}... [prompt truncated at '
                f'{MAX_PROMPT_CHARS} characters, shorten the template]'
            )
        session = (
            self.env['muk_ai.session']
            .with_user(self._agent_user())
            .with_context(clean_context(self.env.context))
            .create(
                {
                    'name': (
                        f'{self.name} - {record.display_name}' if record else self.name
                    ),
                    'agent_id': self.agent_id.id,
                    'action_server_id': self.id,
                    'previous_session_id': previous.id,
                    'res_model': record._name if record else False,
                    'res_id': record.id if record else False,
                }
            )
        )
        if error:
            session._transition_state(
                'error',
                error=self.env._('The prompt could not be rendered: %s', error),
            )
        else:
            session.start(prompt)
        return session

    def _run_action_ai_agent_multi(self, eval_context: dict) -> dict | bool:
        """Start one chat for the target records, or one per record.

        :raise UserError: when the action has no active agent
        :return: a notification of the chats started, if any
        """
        if not self.agent_id.active:
            raise UserError(
                self.env._(
                    'Server action %(name)s has no active agent.',
                    name=self.display_name,
                )
            )
        empty = self.env['base']
        records = self._agent_records(eval_context)
        if self.agent_dispatch_mode == 'single':
            sessions = self._agent_start_session(empty, records)
        else:
            if self.agent_max_records_per_fire > 0:
                records = records[: self.agent_max_records_per_fire]
            sessions = self.env['muk_ai.session'].concat(
                *(self._agent_start_session(record, empty) for record in records)
            )
        if not sessions:
            return False
        if len(sessions) == 1:
            message = self.env._('%(name)s started an AI chat.', name=self.name)
        else:
            message = self.env._(
                '%(name)s started %(count)s AI chats.',
                name=self.name,
                count=len(sessions),
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': message,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_agent_sessions(self) -> dict:
        """Open the chats this action started."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'muk_ai.action_ai_session'
        )
        return {
            **action,
            'domain': [('action_server_id', '=', self.id)],
            'context': {},
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_agent_session_count(self) -> None:
        """Count the chats each action started."""
        counts = dict(
            self.env['muk_ai.session']
            .sudo()
            ._read_group(
                [('action_server_id', 'in', self.ids)],
                ['action_server_id'],
                ['__count'],
            )
        )
        for action in self:
            action.agent_session_count = counts.get(action, 0)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('agent_record_code')
    def _check_agent_record_code(self) -> None:
        """Refuse record code that is not valid Python.

        :raise ValidationError: when the code does not compile
        """
        for action in self.sudo().filtered('agent_record_code'):
            if message := test_python_expr(
                expr=action.agent_record_code.strip(), mode='exec'
            ):
                raise ValidationError(message)
