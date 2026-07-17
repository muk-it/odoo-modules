from __future__ import annotations

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIAgentHandoffTools(models.AbstractModel):
    """Expose the agent-handoff MCP tools (``list_agents`` and ``switch_agent``)."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_handoff_session(self) -> models.Model:
        """Return the AI session bound to the current MCP context.

        :raise UserError: when invoked outside an AI session or when the
            referenced session no longer exists
        """
        if not (session_id := self.env.context.get('muk_mcp_session_id')):
            raise UserError(
                _('The handoff tools can only be invoked from inside an AI session.')
            )
        session = self.env['muk_ai.session'].sudo().browse(session_id)
        if not session.exists():
            raise UserError(_('Session %(sid)s no longer exists.', sid=session_id))
        return session

    def _resolve_handoff_target(self, agent: int | str) -> models.Model:
        """Return the handoff-eligible agent identified by id or exact name.

        :param agent: an agent id (int or digit string) or its exact name
        :raise UserError: when no active, handoff-enabled agent matches
        """
        agents = self.env['muk_ai.agent'].sudo()
        if isinstance(agent, int) or (isinstance(agent, str) and agent.isdigit()):
            target = agents.browse(int(agent)).exists()
        elif isinstance(agent, str) and agent.strip():
            target = agents.search([('name', '=', agent.strip())], limit=1)
        else:
            target = agents.browse()
        if not target or not target.active or not target.allow_handoff:
            raise UserError(
                _(
                    'No handoff-enabled agent matches %(agent)r; call list_agents '
                    'to see the available targets.',
                    agent=agent,
                )
            )
        return target

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='list_agents',
        description=(
            'List the specialist agents you can hand the conversation to via '
            'switch_agent. Returns one entry per agent with its id, name and '
            'description. Call this first to discover which specialist best '
            'fits the user request, then call switch_agent with its id.'
        ),
        input_schema={'type': 'object', 'properties': {}, 'required': []},
        category='read',
        registry='odoo',
    )
    def _mcp_list_agents(self) -> list[dict]:
        """Return the handoff-eligible agents, excluding the current one.

        :return: dicts with id, name and description
        """
        session = self._resolve_handoff_session()
        agents = (
            self.env['muk_ai.agent']
            .sudo()
            .search(
                [
                    ('active', '=', True),
                    ('allow_handoff', '=', True),
                    ('id', '!=', session.agent_id.id),
                ],
                order='sequence, name',
            )
        )
        return [
            {'id': agent.id, 'name': agent.name, 'description': agent.description or ''}
            for agent in agents
        ]

    @api.model
    @mcp_tool(
        name='switch_agent',
        description=(
            'Hand the conversation over to another agent. From the next turn '
            'the chosen agent takes over: its instructions, tools and model '
            'apply in the same session. Pass the agent id from list_agents. '
            'Use this to route the user to the right specialist, or to hand '
            'back when the topic changes.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'agent': {
                    'type': 'integer',
                    'description': 'The target agent id, as returned by list_agents.',
                },
            },
            'required': ['agent'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_switch_agent(self, agent: int | str) -> dict:
        """Switch the session's agent and report the new agent.

        :param agent: the target agent id, or its exact name as a fallback
        :return: a confirmation with the new agent id and name
        :raise UserError: when no handoff-enabled agent matches
        """
        session = self._resolve_handoff_session()
        target = self._resolve_handoff_target(agent)
        if target == session.agent_id:
            return {
                'switched_to': target.name,
                'agent_id': target.id,
                'note': 'already active',
            }
        session.write({'agent_id': target.id, 'expanded_tool_names': []})
        return {'switched_to': target.name, 'agent_id': target.id}
