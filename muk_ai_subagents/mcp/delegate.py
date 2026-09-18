from __future__ import annotations

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai_subagents.tools import (
    BRIEF_LABELS,
    DELEGATE_TOOL,
    MAX_CHILDREN,
    MAX_TASKS,
)
from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIDelegateTools(models.AbstractModel):
    """Expose the ``delegate`` MCP tool that fans work out to subagent sessions."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Subagent
    # ----------------------------------------------------------

    def _resolve_delegating_session(self) -> models.Model:
        """Return the AI session bound to the current MCP context.

        :raise UserError: when invoked outside an AI session, through
            ``tool_load``, or from a session that may not delegate
        """
        session = self._resolve_mcp_session(
            _('The delegate tool can only be invoked from inside an AI session.')
        ).sudo()
        if not self.env.context.get('muk_ai_delegate_call_id'):
            raise UserError(
                _(
                    'Call delegate directly from your tools array, never through '
                    'tool_load.'
                )
            )
        if not session:
            raise UserError(_('This session no longer exists.'))
        if not session._can_delegate():
            raise UserError(_('This session may not delegate tasks to other agents.'))
        return session

    def _resolve_delegate_target(
        self, session: models.Model, agent: int | str
    ) -> models.Model:
        """Return the whitelisted agent identified by id or exact name.

        :raise UserError: when no active agent of the whitelist matches
        """
        allowed = session.agent_id.delegate_agent_ids.filtered('active')
        if isinstance(agent, int) or (isinstance(agent, str) and agent.isdigit()):
            target = allowed.filtered(lambda a: a.id == int(agent))
        elif isinstance(agent, str) and agent.strip():
            target = allowed.filtered(lambda a: a.name == agent.strip())
        else:
            target = allowed.browse()
        if not target:
            raise UserError(
                _(
                    'No agent named %(agent)r may be delegated to; pick one of '
                    '%(names)s.',
                    agent=agent,
                    names=', '.join(allowed.mapped('name')) or '-',
                )
            )
        return target[:1]

    def _clean_task(self, session: models.Model, task) -> dict:
        """Return the validated brief of one task, with the agent resolved.

        :raise UserError: when the task is not an object with an objective
        """
        if not isinstance(task, dict):
            raise UserError(_('Each task must be an object with agent and objective.'))
        brief = {
            key: str(task.get(key) or '').strip()
            for key, _label in BRIEF_LABELS
            if task.get(key)
        }
        if not brief.get('objective'):
            raise UserError(_('Each task needs a non-empty objective.'))
        brief['agent_id'] = self._resolve_delegate_target(session, task.get('agent')).id
        return brief

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name=DELEGATE_TOOL,
        description=(
            'Hand focused tasks to subagent agents that run in parallel, each in '
            'a session of its own with its own tools. Pass one to five tasks; '
            'each names an agent from <delegates> and states the objective, '
            'how success is judged, the shape of the report, the scope and the '
            'exclusions. The call returns at once and your session pauses '
            'until every subagent has reported; the result of this call then '
            'carries each report. Delegate independent, well-bounded work — '
            'research across several sources, parallel look-ups, drafts in '
            'different styles — and keep the synthesis for yourself. Do not '
            'delegate what a single tool call answers.'
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
                                'description': (
                                    'Exact name of an agent listed in <delegates>.'
                                ),
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
                                    'The form of the final report, e.g. "a table '
                                    'of name, amount and date" or "three bullet '
                                    'points".'
                                ),
                            },
                            'scope': {
                                'type': 'string',
                                'description': (
                                    'Records, models or sources the subagent should '
                                    'confine itself to.'
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
            },
            'required': ['tasks'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_delegate(self, tasks: list) -> dict:
        """Start one subagent session per task and report their ids.

        :param tasks: one to five task objects, each naming an agent
        :return: the started subagents and a note on how their reports arrive
        :raise UserError: when a task is invalid or a run cap would be exceeded
        """
        session = self._resolve_delegating_session()
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
            raise UserError(
                _('Pass between 1 and %(max)s tasks.', max=MAX_TASKS),
            )
        briefs = [self._clean_task(session, task) for task in tasks]
        live = session._run_children()._live()
        if len(live) + len(briefs) > MAX_CHILDREN:
            raise UserError(
                _(
                    'At most %(max)s subagents may run at once; %(live)s are still '
                    'running.',
                    max=MAX_CHILDREN,
                    live=len(live),
                )
            )
        if (limit := session._run_cost_limit()) and session._run_cost() >= limit:
            raise UserError(
                _(
                    'The run has reached its cost limit of %(limit).2f; report '
                    'with what you have.',
                    limit=limit,
                )
            )
        children = session.with_user(session.user_id)._spawn_children(briefs)
        return {
            'status': 'delegated',
            'children': [
                {'id': child.id, 'name': child.name, 'agent': child.agent_id.name}
                for child in children
            ],
            'note': (
                'The subagents run in parallel. Their reports arrive as the result '
                'of this call once all of them have finished.'
            ),
        }
