from __future__ import annotations

import io
import json

from PIL import Image

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import (
    PNG_BYTES,
    AITestCommon,
    PNG_1x1,
    json_response,
    text_payload,
    tool_payload,
)


class TestGenerateImage(AITestCommon):
    """Verify the generate_image tool renders with the image model of the session."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a painter agent: a chat model on Anthropic, images on OpenAI."""
        super().setUpClass()
        catalogue = cls.env['muk_ai.model']
        cls.image_model = catalogue.create(
            {
                'name': 'Test Image',
                'provider_id': cls.provider.id,
                'technical_name': 'gpt-image-test',
                'modality': 'image',
                'input_rate': 0.0,
                'output_rate': 0.25,
            }
        )
        cls.claude = catalogue.create(
            {
                'name': 'Test Claude',
                'provider_id': cls.provider_anthropic.id,
                'technical_name': 'claude-test',
                'context_window': 200000,
                'input_rate': 1.0,
                'output_rate': 1.0,
            }
        )
        cls.painter = cls.env['muk_ai.agent'].create(
            {
                'name': 'Painter',
                'model_id': cls.claude.id,
                'enable_image_generation': True,
                'image_model_id': cls.image_model.id,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _generate(self, session: models.BaseModel | None, **arguments) -> dict:
        """Run the image tool bound to ``session``, as a chat dispatches it."""
        context = {'muk_mcp_session_id': session.id} if session else {}
        env = self.env(context={**self.env.context, **context})
        text, _info = env['muk_mcp.tool']._call('generate_image', arguments, env)
        return json.loads(text)

    def _rendered(self, revised: str = '') -> dict:
        """Return the images endpoint answer carrying one rendered PNG."""
        return json_response(
            {'data': [{'b64_json': PNG_1x1, 'revised_prompt': revised}]}
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_image_model_of_the_session_renders_the_prompt(self):
        session = self._session(agent_id=self.painter.id)
        with self._capture_post(self._rendered('a red dot')) as sent:
            result = self._generate(session, prompt='a dot', size='1024x1024')
        url, request = sent[0]
        self.assertEqual(url, 'https://api.openai.com/v1/images/generations')
        self.assertEqual(
            request['json'],
            {'model': 'gpt-image-test', 'prompt': 'a dot', 'size': '1024x1024'},
        )
        self.assertEqual(
            result,
            {
                'type': 'image',
                'filename': 'generated.png',
                'mimetype': 'image/png',
                'content_base64': PNG_1x1,
                'model': 'gpt-image-test',
                'revised_prompt': 'a red dot',
                'ai_generated': True,
                'cost': {
                    'model_id': self.image_model.id,
                    'usage': {'images': 1},
                    'total': 0.25,
                    'currency': 'USD',
                },
            },
        )

    def test_reference_images_reach_the_image_request(self):
        photo = self.env['ir.attachment'].create(
            {'name': 'photo.png', 'raw': PNG_BYTES, 'mimetype': 'image/png'}
        )
        gemini = self.image_model.copy(
            {'provider_id': self.provider_google.id, 'technical_name': 'gemini-image'}
        )
        inline = {'inlineData': {'mimeType': 'image/png', 'data': PNG_1x1}}
        for model, answer, url, sent_images in (
            (
                self.image_model,
                self._rendered(),
                'https://api.openai.com/v1/images/edits',
                lambda body: body['images'],
            ),
            (
                gemini,
                json_response({'candidates': [{'content': {'parts': [inline]}}]}),
                'models/gemini-image:generateContent',
                lambda body: body['contents'][0]['parts'][1:],
            ),
        ):
            with self.subTest(provider=model.provider_id.name):
                self.painter.image_model_id = model
                session = self._session(agent_id=self.painter.id)
                with self._capture_post(answer) as sent:
                    result = self._generate(
                        session, prompt='restage', reference_attachment_ids=[photo.id]
                    )
                self.assertTrue(sent[0][0].endswith(url))
                self.assertEqual(
                    sent_images(sent[0][1]['json']),
                    [{'image_url': f'data:image/png;base64,{PNG_1x1}'}]
                    if model == self.image_model
                    else [inline],
                )
                self.assertEqual(result['content_base64'], PNG_1x1)
        note = self.env['ir.attachment'].create(
            {'name': 'note.txt', 'raw': b'a dot', 'mimetype': 'text/plain'}
        )
        with (
            self._capture_post() as sent,
            self.assertRaisesRegex(UserError, 'Reference images must be .*: note.txt'),
        ):
            self._generate(session, prompt='a dot', reference_attachment_ids=[note.id])
        self.assertFalse(sent)

    def test_an_unsupported_option_is_dropped_with_a_notice(self):
        session = self._session(agent_id=self.painter.id)
        legal = {'quality': 'high', 'background': 'opaque'}
        for options, sent_options, notices in (
            (legal, legal, []),
            ({'quality': 'standard'}, {}, ['low, medium, high']),
            (
                {'quality': 'low', 'background': 'white'},
                {'quality': 'low'},
                ['transparent, opaque'],
            ),
            (
                {'size': '512x512', 'quality': 'ultra', 'background': 'white'},
                {'size': '512x512'},
                ['"ultra"', '"white"'],
            ),
        ):
            with self.subTest(options=options):
                with self._capture_post(self._rendered()) as sent:
                    result = self._generate(session, prompt='a dot', **options)
                self.assertEqual(
                    sent[0][1]['json'],
                    {'model': 'gpt-image-test', 'prompt': 'a dot', **sent_options},
                )
                self.assertEqual(result['content_base64'], PNG_1x1)
                warnings = result.get('warnings', [])
                self.assertEqual(len(warnings), len(notices))
                for warning, notice in zip(warnings, notices, strict=True):
                    self.assertIn(notice, warning)

    def test_a_render_failure_is_answered_and_a_missing_model_refused(self):
        session = self._session(agent_id=self.painter.id)
        refusal = json_response({'error': {'message': 'Prompt rejected.'}}, 400)
        with self._capture_post(refusal):
            result = self._generate(session, prompt='a dot')
        self.assertEqual(set(result), {'prompt', 'error'})
        self.assertIn('Prompt rejected.', result['error'])
        self._clear_default_models('image')
        agents = self.env['muk_ai.agent']
        writer = agents.create(
            {'name': 'Writer', 'image_model_id': self.image_model.id}
        )
        unequipped = agents.create(
            {'name': 'Unequipped', 'enable_image_generation': True}
        )
        for label, bound in (
            ('no session', None),
            ('image generation off', self._session(agent_id=writer.id)),
            ('no image model', self._session(agent_id=unequipped.id)),
        ):
            with (
                self.subTest(label),
                self._capture_post() as sent,
                self.assertRaisesRegex(UserError, 'No image model is available'),
            ):
                self._generate(bound, prompt='a dot')
            self.assertFalse(sent)

    def test_a_chat_turn_stores_a_marked_image_and_counts_its_cost_once(self):
        session = self._session(agent_id=self.painter.id)
        with (
            self._capture_post(self._rendered()),
            self._mock_responses(
                [
                    tool_payload(
                        ('generate_image', {'prompt': 'a dot'}, 'c1'), usage={}
                    ),
                    text_payload('done', usage={}),
                ]
            ),
        ):
            session.send_message('draw a dot')
        stored = self._tool_output(session, 'c1')
        attachment = self.env['ir.attachment'].browse(stored['attachment_id'])
        self.assertEqual(stored['image_url'], f'/web/image/{attachment.id}')
        self.assertNotIn('content_base64', stored)
        self.assertEqual(
            (
                attachment.res_model,
                attachment.res_id,
                attachment.mimetype,
                attachment.ai_generated,
            ),
            ('muk_ai.session', session.id, 'image/png', True),
        )
        image = Image.open(io.BytesIO(attachment.raw.content))
        self.assertEqual(image.tobytes(), Image.open(io.BytesIO(PNG_BYTES)).tobytes())
        self.assertIn(
            b'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/'
            b'digitalsourcetype/trainedAlgorithmicMedia"',
            image.info['xmp'],
        )
        self.assertAlmostEqual(session.total_cost, 0.25)
        self.assertEqual(
            self.env['muk_ai.usage']
            .search([('session_id', '=', session.id)])
            .mapped(lambda row: (row.purpose, row.amount)),
            [('image', 0.25)],
        )
        self.assertNotIn(PNG_1x1, json.dumps(self._events(session, 'tool_result')))
        self.assertEqual(session.state, 'done')
        partner = self.env['res.partner'].create({'name': 'Dot'})
        for value, flagged in ((attachment.raw.to_base64(), True), (PNG_1x1, False)):
            with self.subTest(flagged=flagged):
                partner.image_1920 = value
                self.assertEqual(
                    self.env['ir.attachment']
                    .search(
                        [
                            ('res_model', '=', 'res.partner'),
                            ('res_id', '=', partner.id),
                            ('res_field', '=', 'image_1920'),
                        ]
                    )
                    .ai_generated,
                    flagged,
                )
