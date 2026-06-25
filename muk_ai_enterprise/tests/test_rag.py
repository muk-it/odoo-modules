from __future__ import annotations

from unittest.mock import patch

import psycopg2

from odoo.tests.common import tagged

from .common import BridgeTestCommon


@tagged('post_install', '-at_install')
class TestRag(BridgeTestCommon):
    """Test Enterprise RAG block injection into rendered system prompts."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.has_pgvector = cls._check_pgvector(cls.env)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _check_pgvector(env) -> bool:
        """Return whether the PostgreSQL ``vector`` extension is installed."""
        try:
            env.cr.execute("SELECT 1 FROM pg_extension WHERE extname='vector' LIMIT 1")
            return bool(env.cr.fetchone())
        except psycopg2.Error:
            return False

    def _make_agent_with_source(self) -> tuple:
        """Create a MuK agent with one EE RAG source and return the records."""
        ee_agent = self.env['ai.agent'].sudo().search([], limit=1)
        if not ee_agent:
            ee_agent = (
                self.env['ai.agent']
                .sudo()
                .create(
                    {
                        'name': 'Bridge RAG Agent',
                    }
                )
            )
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'rag-fixture.txt',
                'raw': b'Frobnication is a fictional process used in unit tests.',
                'res_model': 'ai.agent.source',
                'res_id': 0,
            }
        )
        source = (
            self.env['ai.agent.source']
            .sudo()
            .create(
                {
                    'name': 'Bridge RAG Source',
                    'agent_id': ee_agent.id,
                    'type': 'binary',
                    'attachment_id': attachment.id,
                    'status': 'indexed',
                    'is_active': True,
                }
            )
        )
        attachment.write({'res_id': source.id})
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Bridge RAG User',
                'system_prompt': 'You are a frobnicator.',
                'ee_source_ids': [(6, 0, [source.id])],
            }
        )
        return agent, source, attachment

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_rag_block_skipped_when_no_sources(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Bare Agent',
                'system_prompt': 'You are bare.',
            }
        )
        session = self.env['muk_ai.session'].create(
            {
                'name': 'Bare Session',
                'agent_id': agent.id,
            }
        )
        session.write(
            {
                'conversation': [
                    {
                        'role': 'user',
                        'content': [{'type': 'input_text', 'text': 'hello'}],
                    }
                ]
            }
        )
        rendered = session._render_system_prompt(agent.system_prompt)
        self.assertNotIn('<rag>', rendered)

    def test_rag_block_skipped_when_no_user_message(self):
        agent, _source, _att = self._make_agent_with_source()
        session = self.env['muk_ai.session'].create(
            {
                'name': 'No User Msg',
                'agent_id': agent.id,
            }
        )
        rendered = session._render_system_prompt(agent.system_prompt)
        self.assertNotIn('<rag>', rendered)

    def test_rag_block_added_when_chunks_returned(self):
        agent, _source, attachment = self._make_agent_with_source()
        session = self.env['muk_ai.session'].create(
            {
                'name': 'RAG Session',
                'agent_id': agent.id,
            }
        )
        session.write(
            {
                'conversation': [
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'input_text', 'text': 'tell me about frobnication'}
                        ],
                    }
                ]
            }
        )
        chunk = (
            self.env['ai.embedding']
            .sudo()
            .new(
                {
                    'attachment_id': attachment.id,
                    'content': 'Frobnication is a fictional process used in unit tests.',
                    'embedding_model': 'text-embedding-3-small',
                }
            )
        )

        with (
            patch.object(
                type(self.env['ai.embedding']),
                '_get_similar_chunks',
                autospec=True,
                return_value=chunk,
            ),
            patch.object(
                type(self.env['muk_ai.session']),
                '_compute_query_embedding',
                autospec=True,
                return_value=[0.0],
            ),
        ):
            rendered = session._render_system_prompt(agent.system_prompt)

        self.assertIn('<rag>', rendered)
        self.assertIn('Frobnication is a fictional process', rendered)

    def test_rag_block_silently_skipped_on_embedding_failure(self):
        agent, _source, _att = self._make_agent_with_source()
        session = self.env['muk_ai.session'].create(
            {
                'name': 'RAG Failover',
                'agent_id': agent.id,
            }
        )
        session.write(
            {
                'conversation': [
                    {
                        'role': 'user',
                        'content': [{'type': 'input_text', 'text': 'frobnicate me'}],
                    }
                ]
            }
        )

        def boom(*args, **kwargs):
            msg = 'embedding service down'
            raise RuntimeError(msg)

        with patch.object(
            type(self.env['muk_ai.session']),
            '_compute_query_embedding',
            autospec=True,
            side_effect=boom,
        ):
            rendered = session._render_system_prompt(agent.system_prompt)

        self.assertNotIn('<rag>', rendered)
