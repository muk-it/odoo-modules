from __future__ import annotations

import json
import uuid

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools.call import build_tool_call_output


class AISession(models.Model):
    """Surface visible skills in the prompt and dispatch slash invocations."""

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _visible_skills(self, skill_type: str = 'chat') -> models.BaseModel:
        """Return the active skills visible to this session's agent and user.

        Only chat skills by default: a skill another surface offers as a
        button is picked there, and nobody reaches it from a conversation.
        """
        agent_domain = [('agent_ids', '=', False)]
        if self.agent_id:
            agent_domain = ['|', *agent_domain, ('agent_ids', 'in', self.agent_id.ids)]
        return self.env['muk_ai.skill']._search_visible(
            self.user_id or self.env.user, skill_type, agent_domain
        )

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
                'request. Skills are NOT tools - for tool discovery use '
                '<available_tools> + tool_load, never invoke_skill.'
            ),
        ]
        for skill in skills:
            summary = next(iter((skill.description or '').strip().splitlines()), '')
            requirement = skill._scope_requirement()
            suffix = f' ({requirement})' if requirement else ''
            lines.append(f'- `{skill.name}`: {summary}{suffix}')
        lines.append('</available_skills>')
        return '\n'.join(lines)

    def _skill_scope_context(self) -> dict | None:
        """Return the context a skill's scope is judged against.

        The pinned view, for a session somebody is watching. A surface that
        runs without one stands its own record in.
        """
        return self.view_context

    def _check_skill_scope(self, skill: models.BaseModel) -> None:
        """Refuse a skill the session's context does not satisfy.

        :raise UserError: when what the session has open does not match its scope
        """
        if not skill._scope_satisfied_by(self._skill_scope_context()):
            raise UserError(
                self.env._(
                    'Skill %(name)s %(requirement)s.',
                    name=skill.name,
                    requirement=skill._scope_requirement(),
                )
            )

    def _find_skill(self, name: str) -> models.BaseModel:
        """Return the visible skill of that name whose scope the session meets.

        :raise UserError: when the skill is unknown, hidden or out of scope
        """
        skill = self._visible_skills().filtered(lambda s: s.name == name)[:1]
        if not skill:
            raise UserError(self.env._('Skill %(name)r is not available.', name=name))
        self._check_skill_scope(skill)
        return skill

    def _snapshot_values(self) -> dict:
        """Add the descriptors of the visible skills, without their bodies."""
        skills = [
            {
                key: value
                for key, value in skill._skill_descriptor().items()
                if key != 'body'
            }
            for skill in self._visible_skills()
        ]
        return {**super()._snapshot_values(), 'skills': skills}

    @api.model
    def _eager_tool_name_registry(self) -> set[str]:
        """Register the skill tool as loaded by the session, not chosen on the agent."""
        return super()._eager_tool_name_registry() | {'invoke_skill'}

    def _eager_tool_names(self) -> set[str]:
        """Load the skill invocation tool when this session exposes skills."""
        names = super()._eager_tool_names()
        if self._visible_skills():
            names.add('invoke_skill')
        return names

    def _system_prompt_addenda(self) -> list[str]:
        """Append the available-skills block when the session exposes skills."""
        addenda = super()._system_prompt_addenda()
        if skills := self._visible_skills():
            addenda.append(self._format_skill_addendum(skills))
        return addenda

    def _available_tools_extra_paragraphs(self) -> list[str]:
        """Add a guidance paragraph steering invoke_skill away from tools."""
        paragraphs = super()._available_tools_extra_paragraphs()
        if self._visible_skills():
            paragraphs.append(
                '`invoke_skill` is ONLY for the named procedures listed '
                'in the <available_skills> addendum, never for tool '
                'discovery. Pick from this list instead.'
            )
        return paragraphs

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def invoke_skill_from_chat(self, name: str, user_input: str | None = None) -> dict:
        """Run a skill the user picked as if the agent had invoked it, then reply.

        :param user_input: optional free text sent along as a user message
        :raise AccessError: when the caller may only read the session
        :raise UserError: when the session is busy or the skill is unavailable
        """
        self.check_access('write')
        self._recover_if_stuck()
        if self.state in ('running', 'compacting', 'waiting'):
            raise UserError(
                self.env._('Cannot invoke a skill while the session is %s.', self.state)
            )
        skill = self._find_skill(name)
        payload = skill._invocation_payload()
        call_id = f'slash_skill_{skill.name}_{uuid.uuid4().hex[:8]}'
        text = (user_input or '').strip()
        arguments = {'skill_name': skill.name, **({'user_input': text} if text else {})}
        self._extend_conversation(
            [
                {
                    'type': 'function_call',
                    'name': 'invoke_skill',
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                },
                build_tool_call_output(call_id, payload),
            ]
        )
        event = {'name': 'invoke_skill', 'call_id': call_id}
        self._append_event({**event, 'kind': 'tool_call', 'arguments': arguments})
        self._append_event({**event, 'kind': 'tool_result', 'result': payload})
        self._enqueue_user_turn(text, self.env['ir.attachment'])
        self._trigger_worker()
        return self.get_snapshot()
