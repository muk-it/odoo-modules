from odoo import api, models


class MukMcpTool(models.Model):

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self, registry=None):
        tools = super().get_tools(registry=registry)
        if registry not in (None, 'odoo'):
            return tools
        agent_id = self.env.context.get('muk_ai_session_agent_id')
        if not agent_id:
            return tools
        agent = self.env['muk_ai.agent'].sudo().browse(agent_id).exists()
        if not agent or not agent.ee_topic_ids:
            return tools
        if agent.read_only:
            return tools
        extra = self.env['muk_ai_enterprise.ee_tools'].sudo()._ee_tools_for_topics(
            agent.ee_topic_ids,
        )
        if not extra:
            return tools
        seen = {t['name'] for t in tools}
        return list(tools) + [t for t in extra if t['name'] not in seen]

    @api.model
    def _execute(self, name, arguments, env, enforce_scope):
        if isinstance(name, str) and name.startswith('ee_action_'):
            return env['muk_ai_enterprise.ee_tools']._call_ee_action(
                name, arguments, env, enforce_scope=enforce_scope,
            )
        return super()._execute(name, arguments, env, enforce_scope)
