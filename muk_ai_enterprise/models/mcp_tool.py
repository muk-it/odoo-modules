from __future__ import annotations

import psycopg2

from odoo import _, api, models
from odoo.api import Environment
from odoo.exceptions import UserError

from odoo.addons.muk_ai_enterprise.tools import adapter


class MCPTool(models.Model):
    """Expose Enterprise server actions as MuK MCP ``ee_action_*`` tools."""

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_ee_action(self, tool_name: str) -> models.BaseModel:
        """Resolve an ``ee_action_*`` tool name to its server action.

        :return: the matching ``ir.actions.server`` recordset, or an empty
            recordset when the name does not map to an AI-enabled action
        """
        if not tool_name.startswith(adapter.TOOL_PREFIX):
            return self.env['ir.actions.server']
        tech = tool_name[len(adapter.TOOL_PREFIX) :]
        if tech.startswith('action_') and tech[7:].isdigit():
            recs = self.env['ir.actions.server'].sudo().browse(int(tech[7:]))
            return recs.exists().filtered('use_in_ai')
        candidates = (
            self.env['ir.model.data']
            .sudo()
            .search(
                [('model', '=', 'ir.actions.server'), ('name', '=', tech)],
                order='module, id',
            )
        )
        return (
            self.env['ir.actions.server']
            .sudo()
            .browse(candidates.mapped('res_id'))
            .filtered('use_in_ai')
            .exists()
            .sorted('id')[:1]
        )

    @api.model
    def _resolve_ee_record(self, env: Environment) -> models.BaseModel:
        """Resolve the record a session is bound to, falling back to the user."""
        session = (
            env['muk_ai.session']
            .sudo()
            .browse(env.context.get('muk_mcp_session_id') or 0)
        )
        vc = (
            session.view_context
            if session.exists() and isinstance(session.view_context, dict)
            else {}
        )
        if vc.get('kind') != 'record':
            return env.user
        if (
            not (model_name := vc.get('model'))
            or not isinstance(res_id := vc.get('id'), int)
            or env.registry.get(model_name) is None
        ):
            return env.user
        return env[model_name].browse(res_id).exists() or env.user

    @api.model
    def _ee_tools_for_topics(self, topics: models.BaseModel) -> list[dict]:
        """Return tool descriptors for the AI-enabled actions of EE topics."""
        actions = topics.sudo().mapped('tool_ids').filtered('use_in_ai')
        xml_ids = actions.get_external_id() if actions else {}
        descriptors, seen = [], set()
        for action in actions:
            name = adapter.action_tool_name(action.id, xml_ids.get(action.id))
            if name in seen:
                continue
            seen.add(name)
            descriptors.append(
                {
                    'name': name,
                    'description': action.ai_tool_description or action.name or name,
                    'inputSchema': adapter.coerce_schema(action.ai_tool_schema),
                    'category': 'write',
                }
            )
        return descriptors

    @api.model
    def _call_ee_action(
        self,
        tool_name: str,
        arguments: dict | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> tuple[str, dict, str | None]:
        """Run an EE server action and return its serialized result.

        :return: a ``(payload, info, model)`` tuple where ``info`` carries any
            affected record ids and ``model`` is the action's target model
        :raise UserError: when the agent is read-only, the action is unknown,
            or the action raises a non-serialization error
        """
        if enforce_scope == 'read':
            raise UserError(
                _(
                    'Read-only agents cannot call EE action tools (%s).',
                    tool_name,
                )
            )
        if not (action := self._resolve_ee_action(tool_name)):
            raise UserError(_('Unknown EE action tool: %s', tool_name))
        record = self._resolve_ee_record(env)
        try:
            result = action.with_env(env)._ai_tool_run(record, dict(arguments or {}))
        except (UserError, psycopg2.errors.SerializationFailure):
            raise
        except Exception as exc:
            raise UserError(
                _(
                    'EE action %(name)s failed: %(error)s',
                    name=tool_name,
                    error=exc,
                )
            ) from exc
        info = {}
        if isinstance(result, dict) and isinstance(result.get('id'), int):
            info['res_id'] = result['id']
            info['res_ids'] = [result['id']]
        return adapter.serialize_result(result), info, action.model_id.model or None

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self, registry: str | None = None) -> list[dict]:
        """Append EE topic tools to the catalog for non-read-only agents."""
        tools = super().get_tools(registry=registry)
        if registry not in (None, 'odoo'):
            return tools
        agent = (
            self.env['muk_ai.agent']
            .sudo()
            .browse(self.env.context.get('muk_ai_session_agent_id') or 0)
        )
        if not agent.exists() or not agent.ee_topic_ids or agent.read_only:
            return tools
        if not (extra := self.sudo()._ee_tools_for_topics(agent.ee_topic_ids)):
            return tools
        seen = {t['name'] for t in tools}
        return list(tools) + [t for t in extra if t['name'] not in seen]

    @api.model
    def _execute(
        self,
        name: str,
        arguments: dict | None,
        env: Environment,
        enforce_scope: str | None,
    ) -> tuple[str, dict, str | None]:
        """Dispatch ``ee_action_*`` calls to the EE runner, else delegate."""
        if isinstance(name, str) and name.startswith(adapter.TOOL_PREFIX):
            return env['muk_mcp.tool']._call_ee_action(
                name,
                arguments,
                env,
                enforce_scope=enforce_scope,
            )
        return super()._execute(name, arguments, env, enforce_scope)
