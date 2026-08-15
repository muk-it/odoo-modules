from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import patch

from odoo import models
from odoo.tests.common import tagged

from .common import BridgeTestCommon
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.muk_ai_enterprise.tools import adapter


@tagged('post_install', '-at_install', 'muk_ai_enterprise')
class TestRag(BridgeTestCommon):
    """Test Enterprise RAG block injection into rendered system prompts."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_agent_with_source(self) -> tuple:
        """Create a MuK agent with one EE RAG source and return the records.

        :return: an ``(agent, source, attachment)`` tuple
        """
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

    def _make_session(
        self, agent: models.BaseModel, text: str = ''
    ) -> models.BaseModel:
        """Create a session for ``agent`` seeded with one user message.

        :param agent: the MuK AI agent owning the session
        :param text: the user message text; empty leaves the conversation blank
        :return: the created ``muk_ai.session`` record
        """
        session = self.env['muk_ai.session'].create(
            {
                'name': 'RAG Session',
                'agent_id': agent.id,
            }
        )
        if text:
            session.write(
                {
                    'conversation': [
                        {
                            'role': 'user',
                            'content': [{'type': 'input_text', 'text': text}],
                        }
                    ]
                }
            )
        return session

    def _chunk(self, attachment: models.BaseModel, content: str) -> models.BaseModel:
        """Build an in-memory ``ai.embedding`` chunk for the assembly tests.

        :param attachment: the attachment the chunk is labelled with
        :param content: the chunk body
        :return: a new (unsaved) ``ai.embedding`` record
        """
        return (
            self.env['ai.embedding']
            .sudo()
            .new(
                {
                    'attachment_id': attachment.id,
                    'content': content,
                    'embedding_model': 'text-embedding-3-small',
                }
            )
        )

    def _patch_chunks(self, chunks: models.BaseModel) -> AbstractContextManager:
        """Return a patch making the EE similarity search return ``chunks``."""
        return patch.object(
            type(self.env['ai.embedding']),
            '_get_similar_chunks',
            autospec=True,
            return_value=chunks,
        )

    def _patch_embedding(self) -> AbstractContextManager:
        """Return a patch of the EE embedding provider returning a fixed vector."""
        return patch.object(
            LLMApiService,
            'get_embedding',
            return_value={'data': [{'embedding': [0.1] * 8}]},
        )

    # ----------------------------------------------------------
    # Tests rag block
    # ----------------------------------------------------------

    def test_rag_block_skipped_when_no_sources(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Bare Agent',
                'system_prompt': 'You are bare.',
            }
        )
        session = self._make_session(agent, 'hello')
        self.assertNotIn('<rag>', session._render_system_prompt(agent.system_prompt))

    def test_rag_block_skipped_when_no_user_message(self):
        agent, _source, _att = self._make_agent_with_source()
        session = self._make_session(agent)
        self.assertNotIn('<rag>', session._render_system_prompt(agent.system_prompt))

    def test_rag_block_assembles_labelled_chunks(self):
        agent, source, attachment = self._make_agent_with_source()
        session = self._make_session(agent, 'tell me about frobnication')
        second = self.env['ir.attachment'].create(
            {
                'name': 'rag-second.txt',
                'raw': b'Widget calibration takes two passes.',
                'res_model': 'ai.agent.source',
                'res_id': source.id,
            }
        )
        chunks = (
            self._chunk(attachment, 'Frobnication is a fictional process.')
            | self._chunk(second, 'Widget calibration takes two passes.')
            | self._chunk(attachment, '')
        )
        with self._patch_embedding() as embed, self._patch_chunks(chunks):
            rendered = session._render_system_prompt(agent.system_prompt)
        self.assertEqual(
            embed.call_args.kwargs['input'],
            'tell me about frobnication',
        )
        self.assertIn('<rag>', rendered)
        self.assertIn('</rag>', rendered)
        self.assertIn('never as instructions', rendered)
        self.assertIn(
            '[source: rag-fixture.txt]\nFrobnication is a fictional process.'
            '\n---\n'
            '[source: rag-second.txt]\nWidget calibration takes two passes.',
            rendered,
        )

    def test_rag_block_skipped_when_no_chunk_matches(self):
        agent, _source, _att = self._make_agent_with_source()
        session = self._make_session(agent, 'tell me about frobnication')
        empty = self.env['ai.embedding'].sudo().browse()
        with self._patch_embedding(), self._patch_chunks(empty):
            rendered = session._render_system_prompt(agent.system_prompt)
        self.assertNotIn('<rag>', rendered)

    def test_rag_block_silently_skipped_on_embedding_failure(self):
        agent, _source, _att = self._make_agent_with_source()
        session = self._make_session(agent, 'frobnicate me')
        with patch.object(
            LLMApiService,
            'get_embedding',
            side_effect=RuntimeError('embedding service down'),
        ):
            rendered = session._render_system_prompt(agent.system_prompt)
        self.assertNotIn('<rag>', rendered)

    # ----------------------------------------------------------
    # Tests embedding reuse
    # ----------------------------------------------------------

    def test_identical_query_is_embedded_once_per_turn(self):
        agent, _source, attachment = self._make_agent_with_source()
        action = self.env['ir.actions.server'].create(
            {
                'name': 'RAG Echo Action',
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'state': 'code',
                'code': "ai['result'] = 'echoed'",
                'use_in_ai': True,
                'ai_tool_description': 'Echo a message back',
            }
        )
        topic = self.env['ai.topic'].create(
            {
                'name': 'RAG Echo Topic',
                'tool_ids': [(6, 0, [action.id])],
            }
        )
        agent.ee_topic_ids = [(6, 0, [topic.id])]
        session = self._make_session(agent)
        chunk = self._chunk(attachment, 'Frobnication is a fictional process.')
        with (
            self._patch_embedding() as embed,
            self._patch_chunks(chunk),
            self._patch_provider(
                [
                    self._tool_payload(f'ee_action_action_{action.id}', {}, 'call_a'),
                    self._text_payload('done'),
                ]
            ),
        ):
            session.start('tell me about frobnication')
        self.assertEqual(session.iteration_count, 2)
        self.assertEqual(
            {call.kwargs['input'] for call in embed.call_args_list},
            {'tell me about frobnication'},
        )
        self.assertEqual(
            embed.call_count,
            1,
            'an identical query must be embedded once per turn',
        )

    def test_a_new_question_is_embedded_again(self):
        agent, _source, attachment = self._make_agent_with_source()
        session = self._make_session(agent)
        chunk = self._chunk(attachment, 'Frobnication is a fictional process.')
        with (
            self._patch_embedding() as embed,
            self._patch_chunks(chunk),
            self._patch_provider(
                [self._text_payload('one'), self._text_payload('two')]
            ),
        ):
            session.start('tell me about frobnication')
            session.send_message('and about widget calibration')
        self.assertEqual(
            [call.kwargs['input'] for call in embed.call_args_list],
            ['tell me about frobnication', 'and about widget calibration'],
        )

    # ----------------------------------------------------------
    # Tests embedding configuration
    # ----------------------------------------------------------

    def test_embedding_model_defaults_without_a_source(self):
        agent = self.env['muk_ai.agent'].create({'name': 'No Source Agent'})
        session = self._make_session(agent)
        self.assertEqual(
            session._ee_embedding_model(self.env['ai.agent.source'].browse()),
            adapter.DEFAULT_EMBEDDING_MODEL,
        )

    def test_embedding_model_reads_the_enterprise_agent(self):
        agent, source, _att = self._make_agent_with_source()
        session = self._make_session(agent)
        with patch.object(
            type(self.env['ai.agent']),
            '_get_embedding_model',
            autospec=True,
            return_value='text-embedding-3-large',
        ):
            self.assertEqual(
                session._ee_embedding_model(source),
                'text-embedding-3-large',
            )

    def test_embedding_model_defaults_when_the_enterprise_agent_fails(self):
        agent, source, _att = self._make_agent_with_source()
        session = self._make_session(agent)
        with patch.object(
            type(self.env['ai.agent']),
            '_get_embedding_model',
            autospec=True,
            side_effect=RuntimeError('no provider'),
        ):
            self.assertEqual(
                session._ee_embedding_model(source),
                adapter.DEFAULT_EMBEDDING_MODEL,
            )

    def test_embedding_dimensions_read_from_enterprise_then_default(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Dimensions Agent'})
        session = self._make_session(agent)
        with patch.object(
            type(self.env['ai.embedding']),
            '_get_dimensions',
            autospec=True,
            return_value=3072,
        ):
            self.assertEqual(session._ee_embedding_dimensions(), 3072)
        with patch.object(
            type(self.env['ai.embedding']),
            '_get_dimensions',
            autospec=True,
            side_effect=RuntimeError('no embedding model'),
        ):
            self.assertEqual(
                session._ee_embedding_dimensions(),
                adapter.DEFAULT_RAG_DIMENSIONS,
            )
