import json
import logging

import psycopg2

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

EE_TOOL_PREFIX = 'ee_action_'


class EeToolsAdapter(models.AbstractModel):

    _name = 'muk_ai_enterprise.ee_tools'
    _description = "Adapter exposing EE ir.actions.server AI tools as muk_mcp tools"

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _ee_action_tool_name(self, action, xml_ids=None):
        if xml_ids is None:
            xml_ids = action.get_external_id()
        xml_id = xml_ids.get(action.id)
        if xml_id and '.' in xml_id:
            tech = xml_id.split('.', 1)[1]
        else:
            tech = f'action_{action.id}'
        return f'{EE_TOOL_PREFIX}{tech}'

    @api.model
    def _coerce_ee_schema(self, schema_text):
        if not schema_text:
            return {'type': 'object', 'properties': {}}
        try:
            schema = json.loads(schema_text)
        except (TypeError, ValueError):
            return {'type': 'object', 'properties': {}}
        if not isinstance(schema, dict):
            return {'type': 'object', 'properties': {}}
        schema.setdefault('type', 'object')
        schema.setdefault('properties', {})
        return schema

    @api.model
    def _resolve_ee_action(self, tool_name):
        if not tool_name.startswith(EE_TOOL_PREFIX):
            return self.env['ir.actions.server']
        tech = tool_name[len(EE_TOOL_PREFIX):]
        if tech.startswith('action_') and tech[len('action_'):].isdigit():
            return self.env['ir.actions.server'].sudo().browse(
                int(tech[len('action_'):])
            ).exists().filtered(lambda a: a.use_in_ai)
        candidates = self.env['ir.model.data'].sudo().search(
            [('model', '=', 'ir.actions.server'), ('name', '=', tech)],
            order='module, id',
        )
        if not candidates:
            return self.env['ir.actions.server']
        actions = self.env['ir.actions.server'].sudo().browse(
            candidates.mapped('res_id'),
        ).filtered(lambda a: a.use_in_ai).exists()
        if not actions:
            return self.env['ir.actions.server']
        if len(actions) > 1:
            _logger.warning(
                "muk_ai_enterprise: %s ambiguous (%d EE actions share that "
                "xmlid name); picking the lowest id for determinism.",
                tool_name, len(actions),
            )
        return actions.sorted('id')[:1]

    @api.model
    def _resolve_ee_record(self, env):
        session_id = env.context.get('muk_mcp_session_id')
        if not session_id:
            return env.user
        session = env['muk_ai.session'].sudo().browse(session_id).exists()
        if not session or not isinstance(session.view_context, dict):
            return env.user
        vc = session.view_context
        if vc.get('kind') != 'record':
            return env.user
        model_name = vc.get('model')
        res_id = vc.get('id')
        if not model_name or not isinstance(res_id, int):
            return env.user
        Model = env.registry.get(model_name)
        if Model is None:
            return env.user
        record = env[model_name].browse(res_id).exists()
        return record or env.user

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _ee_tools_for_topics(self, topics):
        descriptors = []
        seen = set()
        actions = topics.sudo().mapped('tool_ids').filtered(lambda a: a.use_in_ai)
        xml_ids = actions.get_external_id() if actions else {}
        for action in actions:
            tool_name = self._ee_action_tool_name(action, xml_ids=xml_ids)
            if tool_name in seen:
                continue
            seen.add(tool_name)
            descriptors.append({
                'name': tool_name,
                'description': (
                    action.ai_tool_description or action.name or tool_name
                ),
                'inputSchema': self._coerce_ee_schema(action.ai_tool_schema),
                'category': 'write',
            })
        return descriptors

    @api.model
    def _call_ee_action(self, tool_name, arguments, env, enforce_scope=None):
        if enforce_scope == 'read':
            raise UserError(_(
                "Read-only agents cannot call EE action tools (%s).",
                tool_name,
            ))
        action = self._resolve_ee_action(tool_name)
        if not action:
            raise UserError(_(
                "Unknown EE action tool: %s", tool_name,
            ))
        record = self._resolve_ee_record(env)
        try:
            result = action.with_env(env)._ai_tool_run(record, dict(arguments or {}))
        except (UserError, psycopg2.errors.SerializationFailure):
            raise
        except Exception as exc:
            _logger.exception(
                "muk_ai_enterprise: EE action %s raised", tool_name,
            )
            raise UserError(_(
                "EE action %(name)s failed: %(error)s",
                name=tool_name, error=exc,
            ))
        text = self._serialize_ee_result(result)
        info = {}
        if isinstance(result, dict) and isinstance(result.get('id'), int):
            info['res_id'] = result['id']
            info['res_ids'] = [result['id']]
        model_name = action.model_id.model if action.model_id else None
        return text, info, model_name

    @api.model
    def _serialize_ee_result(self, result):
        if result is None:
            return ''
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, default=str)
        except (TypeError, ValueError):
            return str(result)
