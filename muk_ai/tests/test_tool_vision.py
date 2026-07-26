from __future__ import annotations

import base64
import io
import json
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

from PIL import Image

from odoo import models
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


def _tiny_png_b64() -> str:
    """Return a 1x1 PNG image encoded as base64 ASCII text."""
    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), (0, 128, 255)).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


PNG_B64 = _tiny_png_b64()


@tagged('post_install', '-at_install', 'muk_ai')
class TestToolVision(AITestCommon):
    """Verify image-bearing tool results route to the vision model."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _new_session(self, name: str = 'vision') -> models.Model:
        """Create a fresh AI session for the test user."""
        return self.env['muk_ai.session'].create({'name': name})

    def _tool_payload(self, name: str, arguments: dict, call_id: str) -> dict:
        """Build a provider payload emitting a single tool call."""
        return {
            'text': '',
            'tool_calls': [{'call_id': call_id, 'name': name, 'arguments': arguments}],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': name,
                    'arguments': json.dumps(arguments),
                    'call_id': call_id,
                }
            ],
            'usage': {'input_tokens': 4, 'output_tokens': 2},
        }

    def _text_payload(self, text: str) -> dict:
        """Build a provider payload emitting plain assistant text."""
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': text}],
                }
            ],
            'usage': {'input_tokens': 3, 'output_tokens': 1},
        }

    def _script_provider(
        self, payloads: list[dict]
    ) -> AbstractContextManager[MagicMock]:
        """Patch the provider to pop one scripted payload per LLM round."""
        queue = list(payloads)

        def fake(self_arg, *args, **kwargs):
            if queue:
                return queue.pop(0)
            msg = 'exhausted scripted provider responses'
            raise AssertionError(msg)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _mock_call(self, result: dict) -> AbstractContextManager[MagicMock]:
        """Patch server tool execution to return the given result payload."""

        def fake(self_arg, name, arguments, env, enforce_scope=None):
            return result, {}

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_call',
            autospec=True,
            side_effect=fake,
        )

    def _as_client_tool(self, *client_names: str) -> AbstractContextManager[MagicMock]:
        """Patch the catalog hook so the given tools are client-executed."""
        names = set(client_names)
        return patch.object(
            type(self.env['muk_ai.session']),
            '_client_tool_names',
            autospec=True,
            side_effect=lambda self_arg: names,
        )

    def _no_vision(self, session: models.Model) -> AbstractContextManager[MagicMock]:
        """Patch the session to report the provider lacks vision support."""
        return patch.object(
            type(session),
            '_vision_enabled',
            autospec=True,
            return_value=False,
        )

    def _image_result(self) -> dict:
        """Return a tool result carrying one PNG under the images convention."""
        return {
            'text': 'Captured desktop 1280',
            'images': [{'data': PNG_B64, 'mimetype': 'image/png', 'name': 'desktop'}],
        }

    def _outputs_for(self, session: models.Model, call_id: str) -> list:
        """Return the conversation tool outputs recorded for the call id."""
        return [
            item
            for item in (session.conversation or [])
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    def _vision_entry_after(self, session: models.Model, output: dict) -> dict | None:
        """Return the first user entry following the given output item."""
        conversation = session.conversation or []
        index = conversation.index(output)
        for item in conversation[index + 1 :]:
            if isinstance(item, dict) and item.get('role') == 'user':
                return item
        return None

    # ----------------------------------------------------------
    # Tests: server tool result path
    # ----------------------------------------------------------

    def test_server_tool_image_result_injects_vision_entry(self):
        session = self._new_session()
        with (
            self._script_provider(
                [
                    self._tool_payload('search_read', {'model': 'res.partner'}, 'c0'),
                    self._text_payload('done'),
                ]
            ),
            self._mock_call(self._image_result()),
        ):
            session.start('render it')
        outputs = self._outputs_for(session, 'c0')
        self.assertEqual(len(outputs), 1)
        cleaned = json.loads(outputs[0]['output'])
        self.assertEqual(cleaned['text'], 'Captured desktop 1280')
        self.assertNotIn('images', cleaned)
        entry = self._vision_entry_after(session, outputs[0])
        self.assertIsNotNone(entry)
        blocks = [b for b in entry['content'] if b['type'] == 'muk_ai_attachment']
        self.assertEqual(len(blocks), 1)
        attachment = self.env['ir.attachment'].browse(blocks[0]['attachment_id'])
        self.assertEqual(attachment.mimetype, 'image/png')
        self.assertEqual(attachment.res_model, 'muk_ai.session')
        self.assertEqual(attachment.res_id, session.id)

    def test_vision_entry_materializes_to_image_block(self):
        session = self._new_session()
        with (
            self._script_provider(
                [
                    self._tool_payload('search_read', {'model': 'res.partner'}, 'c0'),
                    self._text_payload('done'),
                ]
            ),
            self._mock_call(self._image_result()),
        ):
            session.start('render it')
        entry = self._vision_entry_after(session, self._outputs_for(session, 'c0')[0])
        materialized = self.provider._materialize_inputs([entry])
        block = materialized[0]['content'][0]
        self.assertEqual(block['strategy'], 'image')
        self.assertEqual(base64.b64decode(block['data_b64']), base64.b64decode(PNG_B64))

    def test_no_vision_support_strips_images_keeps_text(self):
        session = self._new_session()
        with (
            self._script_provider(
                [
                    self._tool_payload('search_read', {'model': 'res.partner'}, 'c0'),
                    self._text_payload('done'),
                ]
            ),
            self._mock_call(self._image_result()),
            self._no_vision(session),
        ):
            session.start('render it')
        outputs = self._outputs_for(session, 'c0')
        cleaned = json.loads(outputs[0]['output'])
        self.assertTrue(cleaned['text'].startswith('Captured desktop 1280'))
        self.assertIn('cannot be shown to this model', cleaned['text'])
        self.assertNotIn('images', cleaned)
        self.assertIsNone(self._vision_entry_after(session, outputs[0]))

    # ----------------------------------------------------------
    # Tests: client action result path
    # ----------------------------------------------------------

    def test_client_tool_image_result_injects_vision_entry(self):
        session = self._new_session()
        with (
            self._script_provider(
                [
                    self._tool_payload('render_preview', {}, 'c0'),
                    self._text_payload('done'),
                ]
            ),
            self._as_client_tool('render_preview'),
        ):
            session.start('preview it')
            session.submit_client_result('c0', self._image_result())
        outputs = self._outputs_for(session, 'c0')
        self.assertEqual(len(outputs), 1)
        self.assertNotIn('images', json.loads(outputs[0]['output']))
        entry = self._vision_entry_after(session, outputs[0])
        self.assertIsNotNone(entry)
        blocks = [b for b in entry['content'] if b['type'] == 'muk_ai_attachment']
        self.assertEqual(len(blocks), 1)

    def test_undo_after_vision_flush_preserves_prior_turn(self):
        session = self._new_session()
        with (
            self._script_provider(
                [
                    self._tool_payload('search_read', {'model': 'res.partner'}, 'c0'),
                    self._text_payload('answer one'),
                ]
            ),
            self._mock_call(self._image_result()),
        ):
            session.start('first question')
        with self._script_provider([self._text_payload('answer two')]):
            session.send_message('second question')
        u2 = (
            self.env['muk_ai.session.event']
            .sudo()
            .search(
                [('session_id', '=', session.id), ('kind', '=', 'user_message')],
                order='sequence desc',
                limit=1,
            )
        )
        conv_before = list(session.conversation)
        expected_cut = max(
            index
            for index, item in enumerate(conv_before)
            if isinstance(item, dict)
            and item.get('role') == 'user'
            and 'second question' in str(item.get('content'))
        )
        session.undo_to_event(u2.id)
        self.assertEqual(list(session.conversation), conv_before[:expected_cut])
        self.assertTrue(any('answer one' in str(item) for item in session.conversation))
