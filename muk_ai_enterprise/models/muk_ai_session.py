import logging

from odoo import models

_logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = 'text-embedding-3-small'
DEFAULT_RAG_TOP_N = 5
DEFAULT_RAG_DIMENSIONS = 1536
EE_CALLER_COMPONENT = 'mail_composer'


class MukAiSession(models.Model):

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Helper Tool Dispatch
    # ----------------------------------------------------------

    def _tool_dispatch_context(self):
        ctx = super()._tool_dispatch_context()
        if self.agent_id:
            ctx['muk_ai_session_agent_id'] = self.agent_id.id
        return ctx

    # ----------------------------------------------------------
    # Helper RAG
    # ----------------------------------------------------------

    def _last_user_text(self):
        for entry in reversed(self.conversation or []):
            if not isinstance(entry, dict) or entry.get('role') != 'user':
                continue
            content = entry.get('content')
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get('type') in ('input_text', 'text'):
                        return part.get('text') or ''
        return ''

    def _ee_embedding_model(self, sources):
        if sources:
            ee_agent = sources[:1].agent_id
            if ee_agent and hasattr(ee_agent, '_get_embedding_model'):
                try:
                    return ee_agent._get_embedding_model()
                except Exception:
                    _logger.warning(
                        "muk_ai_enterprise: _get_embedding_model failed; "
                        "falling back to %s",
                        DEFAULT_EMBEDDING_MODEL, exc_info=True,
                    )
        return DEFAULT_EMBEDDING_MODEL

    def _ee_embedding_dimensions(self):
        Embedding = self.env.get('ai.embedding')
        if Embedding is not None and hasattr(Embedding, '_get_dimensions'):
            try:
                return Embedding.sudo()._get_dimensions()
            except Exception:
                _logger.warning(
                    "muk_ai_enterprise: ai.embedding._get_dimensions failed; "
                    "falling back to %d",
                    DEFAULT_RAG_DIMENSIONS, exc_info=True,
                )
        return DEFAULT_RAG_DIMENSIONS

    def _compute_query_embedding(self, query, embedding_model):
        try:
            from odoo.addons.ai.utils.llm_api_service import LLMApiService
            from odoo.addons.ai.utils.llm_providers import (
                get_provider_for_embedding_model,
            )
        except ImportError:
            _logger.warning(
                "muk_ai_enterprise: ai.utils.llm_* unavailable; skipping RAG",
            )
            return None
        try:
            provider = get_provider_for_embedding_model(
                self.env, embedding_model,
            )
            service = LLMApiService(env=self.env, provider=provider)
            response = service.get_embedding(
                input=query,
                dimensions=self._ee_embedding_dimensions(),
                model=embedding_model,
            )
        except Exception:
            _logger.warning(
                "muk_ai_enterprise: embedding request failed for model %s",
                embedding_model, exc_info=True,
            )
            return None
        try:
            return response['data'][0]['embedding']
        except (KeyError, IndexError, TypeError):
            _logger.warning(
                "muk_ai_enterprise: unexpected embedding response shape: %r",
                response,
            )
            return None

    def _build_ee_rag_snippet(self, sources, query, top_n=DEFAULT_RAG_TOP_N):
        if not sources or not query:
            return ''
        embedding_model = self._ee_embedding_model(sources)
        query_embedding = self._compute_query_embedding(query, embedding_model)
        if not query_embedding:
            return ''
        try:
            chunks = self.env['ai.embedding'].sudo()._get_similar_chunks(
                query_embedding=query_embedding,
                sources=sources.sudo(),
                embedding_model=embedding_model,
                top_n=top_n,
            )
        except Exception:
            _logger.warning(
                "muk_ai_enterprise: _get_similar_chunks failed",
                exc_info=True,
            )
            return ''
        snippets = [chunk.content for chunk in chunks if chunk.content]
        return '\n---\n'.join(snippets)

    # ----------------------------------------------------------
    # Helper Record Context
    # ----------------------------------------------------------

    def _ee_init_context(self, model_name, record_id):
        if not model_name or not record_id:
            return []
        Model = self.env.registry.get(model_name)
        if Model is None:
            return []
        try:
            record = self.env[model_name].sudo().browse(int(record_id)).exists()
        except (TypeError, ValueError, KeyError):
            return []
        if not record:
            return []
        if not hasattr(record, '_ai_initialise_context'):
            return []
        try:
            ctx = record._ai_initialise_context(
                EE_CALLER_COMPONENT, None, None,
            )
        except Exception:
            _logger.warning(
                "muk_ai_enterprise: _ai_initialise_context failed for %s/%s",
                model_name, record_id, exc_info=True,
            )
            return []
        if not ctx:
            return []
        return [str(item) for item in ctx if item]

    def _render_ee_init_context(self, view_context):
        if not isinstance(view_context, dict):
            return ''
        items = view_context.get('ee_init_context') or []
        if not items:
            return ''
        body = '\n'.join(items)
        return f'<ee_ctx>\n{body}\n</ee_ctx>'

    # ----------------------------------------------------------
    # Helper System Prompt
    # ----------------------------------------------------------

    def _append_ee_record_context(self, rendered):
        snippet = self._render_ee_init_context(self.view_context)
        if not snippet:
            return rendered
        return f"{rendered}\n\n{snippet}"

    def _append_ee_rag(self, rendered):
        if not self.agent_id:
            return rendered
        sources = self.agent_id.ee_source_ids
        if not sources:
            return rendered
        query = self._last_user_text()
        if not query:
            return rendered
        try:
            snippet = self._build_ee_rag_snippet(sources, query)
        except Exception:
            _logger.warning(
                "muk_ai_enterprise: RAG snippet build failed",
                exc_info=True,
            )
            return rendered
        if not snippet:
            return rendered
        return f"{rendered}\n\n<rag>\n{snippet}\n</rag>"

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def _enrich_view_context(self, payload):
        payload = super()._enrich_view_context(payload)
        if not isinstance(payload, dict):
            return payload
        if payload.get('kind') != 'record':
            return payload
        if 'ee_init_context' in payload:
            return payload
        ee_ctx = self._ee_init_context(
            payload.get('model'), payload.get('id'),
        )
        if ee_ctx:
            payload = dict(payload)
            payload['ee_init_context'] = ee_ctx
        return payload

    def _render_system_prompt(self, raw):
        rendered = super()._render_system_prompt(raw)
        rendered = self._append_ee_record_context(rendered)
        rendered = self._append_ee_rag(rendered)
        return rendered
