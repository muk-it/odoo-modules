from __future__ import annotations

from odoo import api, fields, models, release

from odoo.addons.muk_ai.tools.call import (
    ASK_USER_TOOL,
    AVAILABLE_TOOLS_PREAMBLE,
    CAPABILITY_TOOLS,
    FILES_BLOCK,
    TERMINATING_TOOLS,
    TOOL_LOAD_TOOL,
    format_tool_signature,
    summarize_tool_description,
)
from odoo.addons.muk_ai.tools.context import with_ui_ctx
from odoo.addons.muk_ai.tools.runtime import (
    DEFAULT_CONTEXT_WINDOW,
    sanitize_json_schema,
)


class AISessionPrompt(models.AbstractModel):
    """System prompt, model resolution and tool catalog of a chat."""

    _name = 'muk_ai.session.prompt'
    _description = 'AI Session Prompt'
    _explanation = (
        'The part of a chat that builds what the model is sent: the system '
        'prompt, the tools it may call and the model it runs on.'
    )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    expanded_tool_names = fields.Json(
        string='Loaded Tools',
        readonly=True,
        default=list,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_terminating_tools(self) -> set[str]:
        """Return the names of tools that terminate a tool round."""
        return TERMINATING_TOOLS

    def _render_system_prompt(self, raw: str) -> str:
        """Render a raw system prompt with the session's template extras."""
        agent = self.agent_id or self.env['muk_ai.agent']._get_default()
        return agent._render_prompt(raw, **self._session_prompt_extras())

    def _effective_system_prompt(self) -> str:
        """Render the system prompt of the session's agent, or of the default one."""
        default = self.env['muk_ai.agent']._get_default()
        return self._render_system_prompt(
            self.agent_id.system_prompt or default.system_prompt or ''
        )

    def _session_prompt_extras(self) -> dict:
        """Return template variables exposed to the system prompt."""
        return {'approval_mode': self._effective_approval_mode()}

    def _system_prompt_addenda(self) -> list[str]:
        """Return capability blocks appended after the agent system prompt.

        Extension modules add their guidance here, apart from the agent's own
        rendered prompt.
        """
        return []

    def _available_tools_extra_paragraphs(self) -> list[str]:
        """Return extra paragraphs appended to the available-tools block."""
        return []

    def _build_available_tools_block(self) -> str:
        """Build the prompt block summarizing the deferred tools."""
        catalog = {
            entry['name']: entry
            for entry in self._get_filtered_catalog()
            if entry.get('name')
        }
        if not (deferred := sorted(set(catalog) - set(self._loaded_tool_names()))):
            return ''
        lines = []
        for name in deferred:
            signature = format_tool_signature(name, catalog[name].get('inputSchema'))
            summary = summarize_tool_description(catalog[name].get('description'))
            lines.append(f'{signature}: {summary}' if summary else signature)
        return '\n'.join(
            [
                '<available_tools>',
                *AVAILABLE_TOOLS_PREAMBLE,
                *self._available_tools_extra_paragraphs(),
                *lines,
                '</available_tools>',
            ]
        )

    def _build_space_block(self) -> str:
        """Build the prompt block carrying the instructions of the session's space.

        The user's text is handed over as written, never rendered. The space is
        read sudoed: a shared chat stays filed in a space only its owner can read.
        """
        space = self.space_id.sudo()
        if not (instructions := (space.instructions or '').strip()):
            return ''
        intro = (
            'How the user wants you to work in the space %(space)s. Follow them '
            'wherever they apply. They refine the instructions above rather '
            'than replace them, and they grant no access you do not already '
            'have.'
        ) % {'space': space.display_name}
        return f'<space_instructions>\n{intro}\n{instructions}\n</space_instructions>'

    def _runtime_capability_lines(self) -> list[str]:
        """State the capabilities the session serves that no tool reveals.

        A capability is stated only when the request carries it: the search
        backend route ships ``web_search``, image generation its tool.
        """
        lines = []
        route = self._web_search_route()
        if route == 'native':
            lines.append(
                'Web search: provider built-in - search the web whenever '
                'freshness matters, and name the sources you used.'
            )
        elif route is None:
            lines.append(
                'Web search: unavailable - say so plainly instead of '
                'guessing at facts that may have moved on.'
            )
        if self._resolve_model_for('image') and self.agent_id._admits_tool(
            'generate_image'
        ):
            lines.append('Image generation: available through generate_image.')
        if self._code_interpreter_route():
            lines.append(
                'Code interpreter: provider-side sandboxed Python, for '
                'analytics over data you already fetched.'
            )
        return lines

    def _build_runtime_block(self) -> str:
        """Build the prompt block stating runtime facts about the session."""
        user, company = self.env.user, self.env.company
        lines = [
            '<runtime>',
            'Facts about this session. Use them directly; do not look them up.',
            f'Odoo: {release.version}',
            f'Date: {fields.Date.context_today(self).isoformat()}',
            f'User: {user.name} (res.users,{user.id}) - tz {user.tz or "UTC"}',
            f'Company: {company.name} (res.company,{company.id})',
            f'Approval mode: {self._effective_approval_mode()}',
        ]
        if self._effective_approval_mode() == 'ask' and (
            gated := self.env['ir.model'].sudo().search([('ai_sensitive', '=', True)])
        ):
            models_list = ', '.join(sorted(gated.mapped('model')))
            lines.append(f'Approval gate (the system asks the user): {models_list}')
        if len(user.company_ids) > 1:
            names = ', '.join(user.company_ids.sorted('id').mapped('name'))
            lines.append(f'Companies accessible: {names}')
        return '\n'.join([*lines, *self._runtime_capability_lines(), '</runtime>'])

    def _resolve_model_for(self, modality: str) -> models.BaseModel:
        """Return the model this session runs ``modality`` on.

        The provider, the context window and every modality of the session
        resolve through it.
        """
        if modality == 'image' and not self._tool_source_enabled('image_generation'):
            return self.env['muk_ai.model']
        return self.agent_id._resolve_model_for(modality)

    def _web_search_route(self) -> str | None:
        """Return the agent's web search route, unless this chat switched it off."""
        if not self._tool_source_enabled('web_search'):
            return None
        return self.agent_id._web_search_route()

    def _code_interpreter_route(self) -> str | None:
        """Return the agent's code interpreter route, unless this chat switched it off."""
        if not self._tool_source_enabled('code_interpreter'):
            return None
        return self.agent_id._code_interpreter_route()

    def _resolve_provider(self) -> models.BaseModel:
        """Return the provider backing this session's chat model."""
        model = self._resolve_model_for('chat')
        return model.provider_id or self.env['muk_ai.provider']._get_default()

    def _resolve_context_window(self) -> int:
        """Return the context window of this session's model, or the default."""
        return self._resolve_model_for('chat').context_window or DEFAULT_CONTEXT_WINDOW

    def _effective_model(self) -> str | None:
        """Return the technical name of the effective model, or ``None``."""
        return self._resolve_model_for('chat').technical_name or None

    def _effective_approval_mode(self) -> str:
        """Return the approval mode from the override, agent, or default."""
        return self.override_approval_mode or self.agent_id.approval_mode or 'ask'

    def _reasoning_effort_options(self) -> list[str]:
        """Return the effort tiers the session's chat model accepts."""
        return self._resolve_model_for('chat')._reasoning_effort_options()

    def _effective_reasoning_effort(self) -> str | None:
        """Return the effort tier from the override or the agent.

        An override the chat model does not accept falls back to the effort
        of the agent.
        """
        if self.override_reasoning_effort in self._reasoning_effort_options():
            return self.override_reasoning_effort
        return self.agent_id.reasoning_effort or None

    @staticmethod
    def _tool_entry_to_schema(entry: dict) -> dict:
        """Convert a tool catalog entry into a provider function schema."""
        schema = entry.get('inputSchema') or {'type': 'object', 'properties': {}}
        return {
            'type': 'function',
            'name': entry['name'],
            'description': entry.get('description') or '',
            'parameters': sanitize_json_schema(schema),
            'strict': False,
        }

    def _build_user_entry(
        self,
        user_message: str | None = None,
        attachments: models.BaseModel | None = None,
    ) -> dict | None:
        """Build a user conversation entry from a message and attachments.

        Each attachment also names its ``odoo://`` uri, so tools can take it.
        """
        content = [{'type': 'input_text', 'text': user_message}] if user_message else []
        for attachment in attachments or []:
            content += [
                {
                    'type': 'input_text',
                    'text': f'Attached file {attachment.name}: odoo://attachment/{attachment.id}',
                },
                {
                    'type': 'muk_ai_attachment',
                    'attachment_id': attachment.id,
                    'filename': attachment.name,
                    'mimetype': attachment.mimetype,
                },
            ]
        return {'role': 'user', 'content': content} if content else None

    def _build_initial_inputs(
        self,
        user_message: str | None = None,
        attachments: models.BaseModel | None = None,
    ) -> list[dict]:
        """Build the conversation a fresh chat starts with, without the system prompt."""
        entry = self._build_user_entry(user_message, attachments)
        return [entry] if entry else []

    def _user_message_log(
        self, user_message: str | None, attachments: models.BaseModel
    ) -> dict:
        """Build the persisted log entry for a user message."""
        return {
            'kind': 'user_message',
            'content': user_message or '',
            'attachments': [attachment._ai_describe() for attachment in attachments],
        }

    def _system_message(self) -> dict:
        """Return the system message rebuilt from the current agent and context."""
        parts = [
            self._effective_system_prompt(),
            self._build_space_block(),
            *self._system_prompt_addenda(),
            self._build_runtime_block(),
            FILES_BLOCK,
            self._build_available_tools_block(),
        ]
        text = '\n\n'.join(part for part in parts if part)
        return {'role': 'system', 'content': [{'type': 'input_text', 'text': text}]}

    def _build_request_inputs(self) -> list[dict]:
        """Return a fresh system message followed by the annotated conversation.

        Internal keys stay on the items; :meth:`ProviderBase._wire_items` is
        the single place they are dropped before the request goes out.
        """
        self._close_orphan_tool_calls(
            {'error': 'interrupted', 'reason': 'tool result missing'}
        )
        history = [
            item
            for item in self.conversation or []
            if not (isinstance(item, dict) and item.get('role') == 'system')
        ]
        return [self._system_message(), *with_ui_ctx(history, self.view_context)]

    def _available_client_kinds(self) -> set[str]:
        """Return the client kinds whose executor can currently answer.

        Modules contributing client-executed tools add their kind; core answers
        ``webclient`` from the chat client in the user's browser tab.
        """
        return {'webclient'}

    def _get_filtered_catalog(self) -> list[dict]:
        """Return the tool catalog filtered by agent and client availability.

        ``web_search`` is offered only on its tool route, so the model never
        sees both the app-side tool and a built-in connector.
        """
        tools = self.env(context={**self.env.context, **self._tool_dispatch_context()})
        catalog = self.agent_id._apply_tool_filter(
            tools['muk_mcp.tool'].sudo().get_tools(registry='odoo')
        )
        hidden = set()
        if self._web_search_route() != 'tool':
            hidden.add('web_search')
        if not self._resolve_model_for('image'):
            hidden.add('generate_image')
        kinds = self._available_client_kinds()
        return [
            entry
            for entry in catalog
            if entry.get('name') not in hidden
            and (
                (meta := entry.get('_meta') or {}).get('execute') != 'client'
                or meta.get('client') in kinds
            )
        ]

    def _client_tool_names(self) -> set[str]:
        """Return the catalog tool names the client must execute."""
        return {
            entry['name']
            for entry in self._get_filtered_catalog()
            if entry.get('name')
            and (entry.get('_meta') or {}).get('execute') == 'client'
        }

    @api.model
    def _eager_tool_name_registry(self) -> set[str]:
        """Return every tool an addon may load upfront, condition aside.

        The agent form subtracts this from the essential picker.
        """
        return set(CAPABILITY_TOOLS)

    def _eager_tool_names(self) -> set[str]:
        """Return the registered tools this session can use right now."""
        return set(CAPABILITY_TOOLS)

    def _get_essential_tool_names(self) -> list[str]:
        """Return the essential names plus every client and eager-loaded tool.

        Client tools ship upfront so a call pauses on the client-action seam.
        """
        eager = self._eager_tool_names()
        return [
            *self.agent_id._get_essential_tool_names(),
            *(
                entry['name']
                for entry in self._get_filtered_catalog()
                if entry.get('name')
                and (
                    (entry.get('_meta') or {}).get('execute') == 'client'
                    or entry['name'] in eager
                )
            ),
        ]

    def _loaded_tool_names(self) -> list[str]:
        """Return the de-duplicated essential and expanded tool names."""
        names = [*self._get_essential_tool_names(), *(self.expanded_tool_names or [])]
        return list(dict.fromkeys(filter(None, names)))

    def _get_tool_schema(self) -> list[dict]:
        """Build the function schema list for currently loaded tools.

        ``ask_user`` always rides along: asking is not approving.
        """
        catalog = {entry['name']: entry for entry in self._get_filtered_catalog()}
        loaded = set(self._loaded_tool_names()) & set(catalog)
        schema = [self._tool_entry_to_schema(catalog[name]) for name in sorted(loaded)]
        if set(catalog) - loaded:
            schema.append(self._tool_entry_to_schema(TOOL_LOAD_TOOL))
        if 'ask_user' not in loaded:
            schema.append(self._tool_entry_to_schema(ASK_USER_TOOL))
        return schema
