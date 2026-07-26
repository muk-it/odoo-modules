from __future__ import annotations

import base64
import io
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

from PIL import Image

from odoo import models
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools import (
    TOOL_VISION_MAX_B64_CHARS,
    TOOL_VISION_MAX_IMAGES,
)


def _tiny_png_b64() -> str:
    """Return a 1x1 PNG image encoded as base64 ASCII text."""
    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), (0, 128, 255)).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


PNG_B64 = _tiny_png_b64()


@tagged('post_install', '-at_install', 'muk_ai')
class TestSessionLimits(AITestCommon):
    """Verify tool-output bounding, vision caps, and turn cost accounting."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cost_model = cls.env['muk_ai.model'].create(
            {
                'name': 'Limits',
                'provider_id': cls.provider.id,
                'technical_name': 'test-limits-model',
                'context_window': 400000,
                'input_rate': 100000.0,
                'output_rate': 200000.0,
                'cache_read_rate': 0.0,
                'currency': 'EUR',
            }
        )
        cls.provider.default_model_id = cls.cost_model

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, name: str = 'limits') -> models.Model:
        """Create a session priced by the test cost model."""
        return self.env['muk_ai.session'].create({'name': name, 'agent_id': False})

    def _text_payload(
        self, text: str = 'done', input_tokens: int = 3, output_tokens: int = 1
    ) -> dict:
        """Build a provider payload emitting plain assistant text."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens},
        }

    def _tool_payload(
        self,
        name: str = 'list_modules',
        call_id: str = 'limits_c1',
        input_tokens: int = 4,
        output_tokens: int = 2,
    ) -> dict:
        """Build a provider payload emitting a single tool call."""
        return {
            'text': '',
            'tool_calls': [{'call_id': call_id, 'name': name, 'arguments': {}}],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': '{}',
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens},
        }

    def _mock_tool_call(self, result: str) -> AbstractContextManager[MagicMock]:
        """Patch server tool execution to return a fixed result payload."""

        def fake(self_arg, name, arguments, env, enforce_scope=None):
            return result, {}

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_call',
            autospec=True,
            side_effect=fake,
        )

    def _image_specs(self, count: int) -> list[dict]:
        """Build ``count`` distinct tool image specs sharing the same payload."""
        return [
            {'data': PNG_B64, 'mimetype': 'image/png', 'name': f'shot{index}'}
            for index in range(count)
        ]

    # ----------------------------------------------------------
    # Tests: tool output bounding
    # ----------------------------------------------------------

    def test_tool_output_within_the_window_is_returned_verbatim(self):
        session = self._session()
        entry = {'call_id': 'c1', 'output': 'x' * 4000}
        self.assertEqual(session._bound_tool_output(entry), entry)

    def test_tool_output_over_the_window_is_truncated_with_a_marker(self):
        self.cost_model.context_window = 200
        session = self._session()
        bounded = session._bound_tool_output({'call_id': 'c1', 'output': 'x' * 500})
        self.assertEqual(bounded['call_id'], 'c1')
        self.assertTrue(bounded['output'].startswith('x' * 200))
        self.assertNotIn('x' * 201, bounded['output'])
        self.assertIn('300 of 500 characters dropped', bounded['output'])

    def test_non_text_tool_output_is_never_bounded(self):
        self.cost_model.context_window = 1
        session = self._session()
        for output in ({'rows': [1, 2, 3]}, [1, 2, 3], None):
            entry = {'call_id': 'c1', 'output': output}
            self.assertEqual(session._bound_tool_output(entry), entry)
        bare = {'call_id': 'c1'}
        self.assertEqual(session._bound_tool_output(bare), bare)

    # ----------------------------------------------------------
    # Tests: tool vision limits
    # ----------------------------------------------------------

    def test_oversized_tool_image_is_dropped(self):
        session = self._session()
        spec = {
            'data': 'A' * (TOOL_VISION_MAX_B64_CHARS + 1),
            'mimetype': 'image/png',
            'name': 'huge.png',
        }
        self.assertFalse(session._persist_tool_image(spec))

    def test_data_url_prefix_is_stripped_before_storing(self):
        session = self._session()
        spec = {
            'data': f'data:image/png;base64,{PNG_B64}',
            'mimetype': 'image/png',
            'name': 'tiny.png',
        }
        attachment = session._persist_tool_image(spec)
        self.assertEqual(attachment.raw, base64.b64decode(PNG_B64))
        self.assertEqual(attachment.mimetype, 'image/png')
        self.assertEqual(attachment.res_model, 'muk_ai.session')
        self.assertEqual(attachment.res_id, session.id)

    def test_tool_vision_keeps_only_the_first_images(self):
        session = self._session()
        specs = self._image_specs(TOOL_VISION_MAX_IMAGES + 2)
        attachments, cleaned = session._extract_tool_vision(
            {'text': 'shots', 'images': specs}
        )
        self.assertEqual(len(attachments), TOOL_VISION_MAX_IMAGES)
        self.assertEqual(
            set(attachments.mapped('name')),
            {spec['name'] for spec in specs[:TOOL_VISION_MAX_IMAGES]},
        )
        self.assertNotIn('images', cleaned)
        self.assertEqual(cleaned['text'], 'shots')

    # ----------------------------------------------------------
    # Tests: cost notice and cost errors
    # ----------------------------------------------------------

    def test_cost_notice_warns_once_the_spend_crosses_the_ratio(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.turn_cost_limit', '1.0'
        )
        session = self._session()
        session.turn_cost_spent = 0.9
        notice = session._round_limit_notice(None)
        self.assertIsNotNone(notice)
        text = notice['content'][0]['text']
        self.assertIn('0.10 EUR of the 1.00 EUR turn cost budget remain', text)
        self.assertNotIn('tool round(s) remain', text)

    def test_cost_notice_stays_silent_below_the_ratio(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.turn_cost_limit', '1.0'
        )
        session = self._session()
        session.turn_cost_spent = 0.5
        self.assertIsNone(session._round_limit_notice(None))

    def test_cost_error_renders_the_model_currency(self):
        session = self._session()
        session._turn_cost_error(1.5)
        self.assertEqual(session.state, 'error')
        self.assertIn('1.50 EUR', session.error_message)

    def test_cost_error_falls_back_to_usd_without_a_model(self):
        self.provider.default_model_id = False
        self.cost_model.active = False
        session = self._session()
        self.assertEqual(session._cost_currency(), 'USD')
        session._turn_cost_error(2.0)
        self.assertEqual(session.state, 'error')
        self.assertIn('2.00 USD', session.error_message)

    # ----------------------------------------------------------
    # Tests: turn cost accrual
    # ----------------------------------------------------------

    def test_turn_cost_spent_accrues_on_every_round(self):
        session = self._session('accrual')
        session.write(
            {
                'state': 'running',
                'conversation': [
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'go'}]}
                ],
            }
        )
        with (
            self._mock_responses([self._tool_payload(), self._text_payload()]),
            self._mock_tool_call('{}'),
        ):
            session._run_iterations()
        self.assertEqual(session.state, 'done')
        self.assertAlmostEqual(session.turn_cost_spent, 1.3, places=6)
        self.assertAlmostEqual(session.total_cost, 1.3, places=6)

    def test_turn_cost_spent_resets_when_a_paused_turn_resumes(self):
        session = self._session('resume')
        session.write(
            {
                'state': 'waiting',
                'turn_cost_spent': 7.0,
                'conversation': [
                    {'role': 'user', 'content': [{'type': 'input_text', 'text': 'go'}]}
                ],
            }
        )
        with self._mock_responses(
            [self._text_payload('resumed', input_tokens=10, output_tokens=5)]
        ):
            session._resume_turn([])
        self.assertEqual(session.state, 'done')
        self.assertAlmostEqual(session.turn_cost_spent, 2.0, places=6)

    # ----------------------------------------------------------
    # Tests: attachment size limit
    # ----------------------------------------------------------

    def test_upload_size_limit_follows_the_config_parameter(self):
        attachment_model = self.env['ir.attachment']
        self.env['ir.config_parameter'].sudo().set_param(
            'web.max_file_upload_size', '1024'
        )
        self.assertEqual(attachment_model._ai_max_size_bytes(), 1024)
        accepted = attachment_model._ai_create_from_upload(
            'ok.txt',
            'text/plain',
            base64.b64encode(b'a' * 1024).decode('ascii'),
        )
        self.assertEqual(accepted.file_size, 1024)
        with self.assertRaises(UserError):
            attachment_model._ai_create_from_upload(
                'big.txt',
                'text/plain',
                base64.b64encode(b'a' * 1025).decode('ascii'),
            )
