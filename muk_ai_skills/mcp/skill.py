from __future__ import annotations

from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool


class SkillToolsMixin(models.AbstractModel):
    """Expose the ``invoke_skill`` MCP tool on the shared tools mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='invoke_skill',
        description=(
            'Invoke a reusable skill by its technical name. ONLY use '
            'this for skills listed in the <available_skills> '
            'addendum of the system prompt. NEVER use this to discover '
            'or load tools - for that, see <available_tools> and '
            'tool_load. Returns the skill body (markdown instructions '
            'you should follow) and a manifest of attached resources, '
            'each with its name, mimetype and `uri` '
            '(e.g. `odoo://attachment/42`). Fetch any resource you need '
            'with `read_resource` passing its `uri`. Use this when the '
            "user's request matches a skill description, or when the "
            'user asks for the skill by name with `/<name>`.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'skill_name': {
                    'type': 'string',
                    'description': (
                        'Technical name of the skill to invoke (the '
                        'lowercase identifier shown in the addendum). '
                        'NOT a tool name - never pass a tool name '
                        'here, that is what tool_load is for.'
                    ),
                },
            },
            'required': ['skill_name'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_invoke_skill(self, skill_name: str | None = None) -> dict:
        """Return the body and resource manifest of an invoked skill."""
        session = self._resolve_mcp_session(
            self.env._('Skill tools can only be invoked from inside an AI session.')
        )
        return session._find_skill(skill_name)._invocation_payload()
