import json
import uuid

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools import build_tool_call_output


class AISession(models.Model):

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _visible_skills(self):
        domain = [('active', '=', True)]
        agent_ids = self.agent_id.ids if self.agent_id else []
        if agent_ids:
            domain += [
                '|',
                ('agent_ids', '=', False),
                ('agent_ids', 'in', agent_ids),
            ]
        else:
            domain += [('agent_ids', '=', False)]
        return self.env['muk_ai.skill'].sudo().search(domain)

    def _format_skill_addendum(self, skills):
        lines = [
            '<available_skills>',
            (
                'Named workflows you can invoke with the `invoke_skill` '
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

    def _build_skill_call_id(self, name):
        return f"slash_skill_{name}_{uuid.uuid4().hex[:8]}"

    def _build_skill_tool_payload(self, skill):
        manifest = skill._resource_manifest()
        return {
            'name': skill.name,
            'body': skill._build_body(session=self),
            'resources': manifest,
        }

    def _effective_system_prompt(self):
        rendered = super()._effective_system_prompt()
        if not self or not self.id:
            return rendered
        skills = self._visible_skills()
        if not skills:
            return rendered
        addendum = self._format_skill_addendum(skills)
        if not rendered:
            return addendum
        return f"{rendered}\n\n{addendum}"

    def _available_tools_extra_paragraphs(self):
        paragraphs = super()._available_tools_extra_paragraphs()
        if self and self.id and self._visible_skills():
            paragraphs.append(
                '`invoke_skill` is ONLY for the named workflows listed '
                'in the <available_skills> addendum, never for tool '
                'discovery. Pick from this list instead.'
            )
        return paragraphs

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def available_skill_names(self, session_id=None):
        skills = (
            self.browse(int(session_id)).exists()._visible_skills()
            if session_id else self.env['muk_ai.skill'].sudo().search([
                ('active', '=', True), ('agent_ids', '=', False),
            ])
        )
        return [
            {
                'name': skill.name,
                'label': skill.label or skill.display_name or skill.name,
                'description': (skill.description or '').strip(),
            }
            for skill in skills
        ]

    def invoke_skill_from_chat(self, name, user_input=None):
        self._recover_if_stuck()
        if self.state in ('running', 'compacting', 'waiting'):
            raise UserError(_(
                "Cannot invoke a skill while the session is %s.", self.state,
            ))
        skill = self._visible_skills().filtered(
            lambda s: s.name == name
        )[:1]
        if not skill:
            raise UserError(_("Skill %r is not available.", name))
        payload = self._build_skill_tool_payload(skill)
        call_id = self._build_skill_call_id(skill.name)
        user_text = (user_input or '').strip()
        arguments = {'skill_name': skill.name}
        if user_text:
            arguments['user_input'] = user_text
        if not self.conversation:
            self.conversation = self._build_initial_inputs()
        self._append_event({
            'kind': 'tool_call',
            'name': 'invoke_skill',
            'arguments': arguments,
            'call_id': call_id,
        })
        self._append_event({
            'kind': 'tool_result',
            'name': 'invoke_skill',
            'result': payload,
            'call_id': call_id,
        })
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
            conversation_entries.append({
                'role': 'user',
                'content': [{'type': 'input_text', 'text': user_text}],
            })
            self._append_event({
                'kind': 'user_message',
                'content': user_text,
                'attachments': [],
            })
        self._extend_conversation(conversation_entries)
        self.write({'state': 'running', 'error_message': False})
        self._publish_event('state', {'state': 'running'})
        self._trigger_worker()
        return self.get_snapshot()
