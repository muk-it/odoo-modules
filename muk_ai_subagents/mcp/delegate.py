from __future__ import annotations

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai_subagents.tools.constants import (
    BRIEF_LABELS,
    DELEGATE_TOOL,
    MAX_CHILDREN,
    MAX_TASKS,
    MESSAGE_TOOL,
    STATUS_MAX_MESSAGES,
    STATUS_MESSAGES,
    TERMINAL_STATES,
)
from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIDelegateTools(models.AbstractModel):
    """Expose the MCP tools a lead uses to start, follow, direct and stop subagents."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_delegating_session(self) -> models.Model:
        """Return the AI session a lead tool call runs in.

        :raise UserError: when called outside a session, or from a session that
            may not delegate
        """
        session = self._resolve_mcp_session(
            self.env._('The subagent tools can only be called inside an AI session.')
        )
        if not session or not session._delegates():
            raise UserError(
                self.env._('This session may not delegate tasks to other agents.')
            )
        return session

    def _waiting_call_id(self) -> str:
        """Return the id of the tool call that waits for subagents.

        :raise UserError: when the tool was called through ``tool_load``
        """
        if call_id := self.env.context.get('muk_ai_delegate_call_id'):
            return call_id
        raise UserError(
            self.env._(
                'Call the subagent tools directly from your tools array, '
                'never through tool_load.'
            )
        )

    def _resolve_subagent(self, session: models.Model, subagent) -> models.Model:
        """Return the subagent of the session's run with the given id.

        :raise UserError: when the run has no such subagent
        """
        found = session._run_children().filtered(
            lambda child: str(child.id) == str(subagent)
        )
        if not found:
            raise UserError(
                self.env._('No subagent %s belongs to this chat.', subagent)
            )
        return found

    def _clean_task(self, delegates: models.Model, task) -> dict:
        """Return the brief of one task, with its agent resolved among ``delegates``.

        :raise UserError: when the task is no object, has no objective, or
            names an agent that is not a delegate
        """
        if not isinstance(task, dict):
            raise UserError(
                self.env._('Each task must be an object with agent and objective.')
            )
        brief = {
            key: str(task[key]).strip()
            for key, _label in BRIEF_LABELS
            if str(task.get(key) or '').strip()
        }
        if not brief.get('objective'):
            raise UserError(self.env._('Each task needs a non-empty objective.'))
        name = str(task.get('agent') or '').strip()
        agent = delegates.filtered(lambda delegate: delegate.name == name)[:1]
        if not agent:
            raise UserError(
                self.env._(
                    'No agent named %(agent)r may be delegated to; pick one of '
                    '%(names)s.',
                    agent=name,
                    names=', '.join(delegates.mapped('name')),
                )
            )
        return {**brief, 'agent_id': agent.id}

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name=DELEGATE_TOOL,
        description=(
            'Hand focused tasks to other agents that run in parallel, each in a '
            'chat of its own with its own tools. Pass one to five tasks; each '
            'names an agent from <delegates> and briefs it fully, as it sees '
            'nothing else: the objective, how success is judged, the shape of '
            'the report, the scope and the exclusions. A subagent asks the '
            'user for approval itself where a write needs one. The call '
            'returns at once: tell the user what you started and keep helping '
            'them. Each report reaches you as a <subagent_report> when its '
            'subagent ends; work it in and tell the user what it means. With '
            'background false your turn pauses until every subagent has '
            'reported, and the result of this call carries the reports; use it '
            'only when you cannot answer without them.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'tasks': {
                    'type': 'array',
                    'minItems': 1,
                    'maxItems': MAX_TASKS,
                    'description': 'One entry per subagent to start.',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'agent': {
                                'type': 'string',
                                'description': 'Exact name of an agent in <delegates>.',
                            },
                            'objective': {
                                'type': 'string',
                                'description': (
                                    'What the subagent must achieve, in one or two '
                                    'sentences.'
                                ),
                            },
                            'success_criteria': {
                                'type': 'string',
                                'description': 'How the subagent knows it is done.',
                            },
                            'output_shape': {
                                'type': 'string',
                                'description': (
                                    'The form of the report, e.g. "a table of '
                                    'name, amount and date" or "three bullet '
                                    'points".'
                                ),
                            },
                            'scope': {
                                'type': 'string',
                                'description': (
                                    'Records, models or sources to stay within.'
                                ),
                            },
                            'exclusions': {
                                'type': 'string',
                                'description': 'What the subagent must not do or touch.',
                            },
                        },
                        'required': ['agent', 'objective'],
                    },
                },
                'background': {
                    'type': 'boolean',
                    'description': (
                        'Return at once and let the reports arrive later. '
                        'Default true; false waits for them.'
                    ),
                },
            },
            'required': ['tasks'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_delegate(self, tasks: list, background: bool = True) -> dict:
        """Start one subagent per task and say how their reports arrive.

        :raise UserError: when a task is invalid or a run limit is reached
        """
        session = self._resolve_delegating_session()
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
            raise UserError(self.env._('Pass between 1 and %s tasks.', MAX_TASKS))
        delegates = session._delegates()
        briefs = [self._clean_task(delegates, task) for task in tasks]
        live = session._run_children()._live()
        if len(live) + len(briefs) > MAX_CHILDREN:
            raise UserError(
                self.env._(
                    'At most %(max)s subagents may run at once; %(live)s are '
                    'still running.',
                    max=MAX_CHILDREN,
                    live=len(live),
                )
            )
        children = session._spawn_children(
            briefs, self._waiting_call_id(), bool(background)
        )
        return {
            'status': 'delegated',
            'wait': not background,
            'subagent_ids': children.ids,
            'subagents': [
                {'id': child.id, 'name': child.name, 'agent': child.agent_id.name}
                for child in children
            ],
        }

    @api.model
    @mcp_tool(
        name='subagent_status',
        description=(
            'Check on the subagents of this chat: the state of each, why it '
            'ended, and its last messages and tool calls. Use it to follow '
            'background subagents or to find out why one failed.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'subagent': {
                    'type': 'integer',
                    'description': 'The subagent to look at; all of them when left out.',
                },
                'messages': {
                    'type': 'integer',
                    'description': f'How many of its last messages to return, at most '
                    f'{STATUS_MAX_MESSAGES}.',
                },
            },
        },
        category='read',
        registry='odoo',
    )
    def _mcp_subagent_status(
        self, subagent: int | None = None, messages: int = STATUS_MESSAGES
    ) -> list[dict]:
        """Return the state and last messages of the subagents of the run."""
        session = self._resolve_delegating_session()
        children = (
            self._resolve_subagent(session, subagent)
            if subagent
            else session._run_children()
        )
        limit = max(0, min(int(messages or 0), STATUS_MAX_MESSAGES))
        return [
            {**child._report(), 'messages': child._recent_messages(limit)}
            for child in children
        ]

    @api.model
    @mcp_tool(
        name=MESSAGE_TOOL,
        description=(
            'Send a subagent of this chat a message. A running subagent takes it '
            'after its current step, as new direction; one that ended, failed or '
            'was stopped carries on from where it was, with everything it did so '
            'far, so you can fix what went wrong and let it continue. Its report '
            'arrives later as a <subagent_report>; with wait true your turn '
            'pauses until it reports again.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'subagent': {'type': 'integer', 'description': 'The subagent.'},
                'message': {'type': 'string', 'description': 'What to tell it.'},
                'wait': {
                    'type': 'boolean',
                    'description': 'Wait for its report. Default false.',
                },
            },
            'required': ['subagent', 'message'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_subagent_message(
        self, subagent: int, message: str, wait: bool = False
    ) -> dict:
        """Direct a running subagent, or let one that ended carry on.

        :raise UserError: when the message is empty or the subagent unknown
        """
        session = self._resolve_delegating_session()
        child = self._resolve_subagent(session, subagent)
        if not (text := str(message or '').strip()):
            raise UserError(self.env._('The message is empty.'))
        if wait:
            self._waiting_call_id()
        child.delegation_brief = {**child.delegation_brief, 'notify': not wait}
        child.send_message(text)
        return {
            'status': 'sent',
            'wait': bool(wait),
            'subagent_ids': child.ids,
            'state': child.state,
        }

    @api.model
    @mcp_tool(
        name='subagent_stop',
        description='Stop a subagent of this chat that is still running.',
        input_schema={
            'type': 'object',
            'properties': {
                'subagent': {'type': 'integer', 'description': 'The subagent.'},
            },
            'required': ['subagent'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_subagent_stop(self, subagent: int) -> dict:
        """Stop a running subagent and return what it reported so far."""
        child = self._resolve_subagent(self._resolve_delegating_session(), subagent)
        if child.state not in TERMINAL_STATES:
            child.action_stop()
        return child._report()
