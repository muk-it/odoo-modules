from __future__ import annotations

import json
import uuid

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools import build_tool_call_output


class AISession(models.Model):
    """Surface visible skills in the prompt and dispatch slash invocations."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _visible_skills(self) -> models.BaseModel:
        """Return the active skills visible to this session's agent and user."""
        skill_model = self.env['muk_ai.skill'].sudo()
        user = self.user_id or self.env.user
        domain = [('active', '=', True)]
        domain += skill_model._user_visibility_domain(user)
        agent_ids = self.agent_id.ids if self.agent_id else []
        if agent_ids:
            domain += [
                '|',
                ('agent_ids', '=', False),
                ('agent_ids', 'in', agent_ids),
            ]
        else:
            domain += [('agent_ids', '=', False)]
        return self._dedupe_visible_skills(skill_model.search(domain), user)

    @api.model
    def _dedupe_visible_skills(
        self, skills: models.BaseModel, user: models.BaseModel
    ) -> models.BaseModel:
        """Keep one skill per name, preferring the one owned by the user.

        Ties between skills the user does not own resolve to the first
        record in search order, which the model keeps deterministic by
        ordering on ``sequence, name, id``.
        """
        chosen: dict[str, models.BaseModel] = {}
        for skill in skills:
            current = chosen.get(skill.name)
            if current is None or (skill.owner_id == user and current.owner_id != user):
                chosen[skill.name] = skill
        return skills.filtered(lambda s: chosen.get(s.name) == s)

    def _format_skill_addendum(self, skills: models.BaseModel) -> str:
        """Render the ``<available_skills>`` system-prompt addendum."""
        lines = [
            '<available_skills>',
            (
                'Named procedures you can invoke with the `invoke_skill` '
                'tool (`{"skill_name": "<skill>"}`). Each returns a body '
                'of instructions plus a resource manifest with `uri` '
                'entries (e.g. `odoo://attachment/42`); fetch any listed '
                'resource with `read_resource` (`{"uri": "<uri>"}`).'
            ),
            (
                'Pick a skill when its description matches the user '
                'request. Skills are NOT tools — for tool discovery use '
                '<available_tools> + tool_load, never invoke_skill.'
            ),
        ]
        for skill in skills:
            description = (skill.description or '').strip().splitlines()
            summary = description[0] if description else ''
            lines.append(f'- `{skill.name}`: {summary}')
        lines.append('</available_skills>')
        return '\n'.join(lines)

    def _build_skill_call_id(self, name: str) -> str:
        """Build a unique synthetic tool-call id for a slash invocation."""
        return f'slash_skill_{name}_{uuid.uuid4().hex[:8]}'

    def _build_skill_tool_payload(self, skill: models.BaseModel) -> dict:
        """Build the ``invoke_skill`` tool-result payload for a skill."""
        manifest = skill._resource_manifest()
        return {
            'name': skill.name,
            'body': skill._build_body(session=self),
            'resources': manifest,
        }

    def _system_prompt_addenda(self) -> list[str]:
        """Append the available-skills block when the session exposes skills."""
        addenda = super()._system_prompt_addenda()
        if self and self.id and (skills := self._visible_skills()):
            addenda.append(self._format_skill_addendum(skills))
        return addenda

    def _available_tools_extra_paragraphs(self) -> list[str]:
        """Add a guidance paragraph steering invoke_skill away from tools."""
        paragraphs = super()._available_tools_extra_paragraphs()
        if self and self.id and self._visible_skills():
            paragraphs.append(
                '`invoke_skill` is ONLY for the named procedures listed '
                'in the <available_skills> addendum, never for tool '
                'discovery. Pick from this list instead.'
            )
        return paragraphs

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def available_skill_names(self, session_id: int | None = None) -> list[dict]:
        """Return the descriptors of the visible skills for the chat panel.

        :param session_id: session to scope visibility to, or a falsy value
            to list every globally visible skill
        """
        skills = (
            self.browse(int(session_id)).exists()._visible_skills()
            if session_id
            else self._visible_skills()
        )
        return [
            {
                'name': skill.name,
                'label': skill.label or skill.display_name or skill.name,
                'description': (skill.description or '').strip(),
                'icon': skill.icon or 'fa-bolt',
            }
            for skill in skills
        ]

    def invoke_skill_from_chat(self, name: str, user_input: str | None = None) -> dict:
        """Inject a skill invocation into the conversation and run the LLM.

        :param name: technical name of the skill to invoke
        :param user_input: optional free-text appended as a user turn
        :return: the refreshed session snapshot
        :raise UserError: when the session is busy or the skill is invalid
        """
        self._recover_if_stuck()
        if self.state in ('running', 'compacting', 'waiting'):
            raise UserError(
                _(
                    'Cannot invoke a skill while the session is %s.',
                    self.state,
                )
            )
        skill = self._visible_skills().filtered(lambda s: s.name == name)[:1]
        if not skill:
            raise UserError(_('Skill %r is not available.', name))
        payload = self._build_skill_tool_payload(skill)
        call_id = self._build_skill_call_id(skill.name)
        user_text = (user_input or '').strip()
        arguments = {'skill_name': skill.name}
        if user_text:
            arguments['user_input'] = user_text
        if not self.conversation:
            self.conversation = self._build_initial_inputs()
        self._append_event(
            {
                'kind': 'tool_call',
                'name': 'invoke_skill',
                'arguments': arguments,
                'call_id': call_id,
            }
        )
        self._append_event(
            {
                'kind': 'tool_result',
                'name': 'invoke_skill',
                'result': payload,
                'call_id': call_id,
            }
        )
        conversation_entries = [
            {
                'type': 'function_call',
                'name': 'invoke_skill',
                'arguments': json.dumps(arguments),
                'call_id': call_id,
            },
            build_tool_call_output(call_id, payload),
        ]
        if user_text:
            conversation_entries.append(
                {
                    'role': 'user',
                    'content': [{'type': 'input_text', 'text': user_text}],
                }
            )
            self._append_event(
                {
                    'kind': 'user_message',
                    'content': user_text,
                    'attachments': [],
                }
            )
        self._extend_conversation(conversation_entries)
        self.write({'state': 'running', 'error_message': False})
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self.get_snapshot()
