from __future__ import annotations

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool


class SkillToolsMixin(models.AbstractModel):
    """Expose the ``invoke_skill`` MCP tool on the shared tools mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _resolve_skill_session(self) -> models.BaseModel:
        """Resolve the AI session bound to the current MCP context.

        :raise UserError: when no session id is in context or it is gone
        """
        if not (session_id := self.env.context.get('muk_mcp_session_id')):
            raise UserError(
                _('Skill tools can only be invoked from inside an AI session.')
            )
        session = self.env['muk_ai.session'].sudo().browse(session_id)
        if not session.exists():
            raise UserError(
                _(
                    'Session %(sid)s no longer exists.',
                    sid=session_id,
                )
            )
        return session

    def _resolve_visible_skill(
        self, session: models.BaseModel, name: str
    ) -> models.BaseModel:
        """Resolve a skill by name, ensuring it is visible to the session.

        :raise UserError: when the skill is unknown or not visible
        """
        skill = session._visible_skills().filtered(lambda s: s.name == name)[:1]
        if not skill:
            raise UserError(_('Skill %(name)r is invalid.', name=name))
        return skill

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
            'or load tools — for that, see <available_tools> and '
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
                        'NOT a tool name — never pass a tool name '
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
        session = self._resolve_skill_session()
        skill = self._resolve_visible_skill(session, skill_name)
        return {
            'name': skill.name,
            'label': skill.label or skill.display_name or skill.name,
            'body': skill.body or '',
            'resources': skill._resource_manifest(),
        }
