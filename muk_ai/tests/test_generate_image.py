from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai.mcp.image import IMAGE_OPTIONS
from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.tests.common import ImageCase, PNG_1x1, ToolCatalogMixin
from odoo.addons.muk_mcp.core.tool import get_tool_index


class TestGenerateImageProvider(ImageCase):
    """Verify the shared ``/images/generations`` adapter."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_gpt_image_sends_only_what_was_asked(self):
        captured = {}
        payload = {'data': [{'b64_json': PNG_1x1, 'revised_prompt': 'a red dot'}]}
        with self._post(payload, captured):
            result = self.provider._get_client().generate_image(
                'gpt-image-2', 'a dot', {'size': '1024x1024', 'quality': None}
            )
        self.assertEqual(
            captured['url'], 'https://api.openai.com/v1/images/generations'
        )
        self.assertEqual(
            captured['json'],
            {'model': 'gpt-image-2', 'prompt': 'a dot', 'size': '1024x1024'},
        )
        self.assertEqual(captured['headers']['Authorization'], 'Bearer test-key')
        self.assertEqual(result['data_b64'], PNG_1x1)
        self.assertEqual(result['mimetype'], 'image/png')
        self.assertEqual(result['revised_prompt'], 'a red dot')
        self.assertEqual(result['usage'], {'images': 1})

    def test_other_models_ask_for_base64(self):
        captured = {}
        with self._post({'data': [{'b64_json': PNG_1x1}]}, captured):
            self.provider._get_client().generate_image('dall-e-3', 'a dot')
        self.assertEqual(captured['json']['response_format'], 'b64_json')

    def test_timeout_follows_the_provider_image_setting(self):
        captured = {}
        self.provider.write({'request_timeout': 60, 'image_timeout': 300})
        with self._post({'data': [{'b64_json': PNG_1x1}]}, captured):
            self.provider._get_client().generate_image('gpt-image-2', 'a dot')
        self.assertEqual(captured['timeout'], 300)

    def test_the_image_budget_outlives_the_chat_request_timeout(self):
        self.assertEqual(self.provider.request_timeout, 60)
        self.assertEqual(self.provider.image_timeout, 180)

    def test_a_failed_render_surfaces_the_vendor_error(self):
        response = MagicMock(
            status_code=400,
            text='{"error": {"message": "The model gpt-image-99 does not exist."}}',
        )
        error = requests.HTTPError(response=response)
        with (
            patch.object(requests.Session, 'post', side_effect=error),
            self.assertRaises(UserError) as caught,
        ):
            self.provider._get_client().generate_image('gpt-image-99', 'a dot')
        self.assertIn('The model gpt-image-99 does not exist.', str(caught.exception))

    def test_a_missing_route_surfaces_the_failing_request(self):
        response = MagicMock(status_code=404, text='')
        error = requests.HTTPError(
            '404 Client Error: Not Found for url: '
            'https://api.anthropic.com/v1/images/generations',
            response=response,
        )
        with (
            patch.object(requests.Session, 'post', side_effect=error),
            self.assertRaises(UserError) as caught,
        ):
            self.provider_anthropic._get_client().generate_image('x', 'a dot')
        self.assertIn('404', str(caught.exception))
        self.assertIn('images/generations', str(caught.exception))

    def test_empty_data_raises_a_user_error(self):
        with self._post({'data': []}, {}), self.assertRaises(UserError):
            self.provider._get_client().generate_image('gpt-image-2', 'a dot')


class TestGenerateImageTool(ImageCase):
    """Verify the generate_image MCP tool, its storage and its cost settlement."""

    # ----------------------------------------------------------
    # Tests: tool
    # ----------------------------------------------------------

    def test_tool_registered_in_odoo_catalog(self):
        index = get_tool_index(self.env, registry='odoo')
        self.assertIn('generate_image', index)
        self.assertEqual(index['generate_image']['category'], 'read')
        self.assertIn('![alt](image_url)', index['generate_image']['description'])
        self.assertNotIn('n', index['generate_image']['input_schema']['properties'])

    def test_the_schema_enum_is_the_enforced_contract(self):
        properties = get_tool_index(self.env, registry='odoo')['generate_image'][
            'input_schema'
        ]['properties']
        for name, spec in IMAGE_OPTIONS.items():
            self.assertEqual(properties[name]['enum'], list(spec['enum']))
        for value in ('low', 'medium', 'high'):
            options, notices = self.env['muk_mcp.mixin']._image_options(
                None, value, None
            )
            self.assertEqual(options['quality'], value)
            self.assertEqual(notices, [])

    def test_an_invented_option_value_is_dropped_and_reported(self):
        options, notices = self.env['muk_mcp.mixin']._image_options(
            '1024x1024', 'standard', 'white'
        )
        self.assertEqual(options['size'], '1024x1024')
        self.assertIsNone(options['quality'])
        self.assertIsNone(options['background'])
        self.assertEqual(len(notices), 2)
        self.assertIn('standard', notices[0])
        self.assertIn('low, medium, high', notices[0])
        self.assertIn('white', notices[1])
        self.assertIn('transparent, opaque', notices[1])

    def test_an_invented_option_value_still_renders_the_image(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Painter',
                'enable_image_generation': True,
                'image_model_id': self.image.id,
            }
        )
        session = self._session(agent)
        captured = {}

        def fake(client, model, prompt, options=None):
            captured.update(options or {})
            return self._rendered('revised')

        with patch.object(
            OpenAIProvider, 'generate_image', autospec=True, side_effect=fake
        ):
            result = (
                self.env['muk_mcp.mixin']
                .with_context(muk_mcp_session_id=session.id)
                ._mcp_generate_image(prompt='a dot', quality='standard')
            )
        self.assertIsNone(captured['quality'])
        self.assertEqual(result['type'], 'image')
        self.assertEqual(result['content_base64'], PNG_1x1)
        self.assertEqual(len(result['warnings']), 1)
        self.assertIn('low, medium, high', result['warnings'][0])

    def test_a_legal_option_value_reaches_the_wire_without_warnings(self):
        captured = {}
        payload = {'data': [{'b64_json': PNG_1x1}]}
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Painter',
                'enable_image_generation': True,
                'image_model_id': self.image.id,
            }
        )
        session = self._session(agent)
        with self._post(payload, captured):
            result = (
                self.env['muk_mcp.mixin']
                .with_context(muk_mcp_session_id=session.id)
                ._mcp_generate_image(
                    prompt='a dot', quality='high', background='opaque'
                )
            )
        self.assertEqual(captured['json']['quality'], 'high')
        self.assertEqual(captured['json']['background'], 'opaque')
        self.assertEqual(captured['timeout'], 180)
        self.assertNotIn('warnings', result)

    def test_renders_with_the_session_image_model(self):
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Painter',
                'model_id': self.chat_anthropic.id,
                'enable_image_generation': True,
                'image_model_id': self.image.id,
            }
        )
        session = self._session(agent)
        captured = {}

        def fake(client, model, prompt, options=None):
            captured.update(model=model, prompt=prompt, options=options)
            return self._rendered('revised')

        with patch.object(
            OpenAIProvider, 'generate_image', autospec=True, side_effect=fake
        ):
            result = (
                self.env['muk_mcp.mixin']
                .with_context(muk_mcp_session_id=session.id)
                ._mcp_generate_image(prompt='a dot', size='1024x1024')
            )
        self.assertEqual(captured['model'], 'gpt-image-test')
        self.assertEqual(captured['prompt'], 'a dot')
        self.assertEqual(captured['options']['size'], '1024x1024')
        self.assertEqual(result['type'], 'image')
        self.assertEqual(result['filename'], 'generated.png')
        self.assertEqual(result['mimetype'], 'image/png')
        self.assertEqual(result['content_base64'], PNG_1x1)
        self.assertEqual(result['model'], 'gpt-image-test')
        self.assertEqual(result['revised_prompt'], 'revised')
        self.assertNotIn('model_id', result['cost'])
        self.assertAlmostEqual(result['cost']['total'], 0.25)
        self.assertEqual(result['cost']['currency'], 'USD')

    def test_without_a_session_the_tool_raises(self):
        self.provider.default_image_model_id = self.image
        with self.assertRaises(UserError):
            self.env['muk_mcp.mixin']._mcp_generate_image(prompt='a dot')

    def test_a_session_without_a_usable_image_model_raises(self):
        self._clear_default_models('image')
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Painter',
                'model_id': self.chat_anthropic.id,
                'enable_image_generation': True,
            }
        )
        session = self._session(agent)
        with self.assertRaises(UserError) as caught:
            self.env['muk_mcp.mixin'].with_context(
                muk_mcp_session_id=session.id
            )._mcp_generate_image(prompt='a dot')
        self.assertIn('No image model is available', str(caught.exception))

    def test_the_agent_pick_renders_on_its_own_provider(self):
        gemini_image = self.env.ref('muk_ai.model_gemini_3_1_flash_image')
        agent = self.env['muk_ai.agent'].create(
            {
                'name': 'Mixed',
                'enable_image_generation': True,
                'image_model_id': gemini_image.id,
            }
        )
        session = self._session(agent)
        self.provider.default_image_model_id = self.image
        self.assertEqual(session._resolve_model_for('image'), gemini_image)
        self.assertEqual(
            self.env['muk_mcp.mixin']
            .with_context(muk_mcp_session_id=session.id)
            ._image_model(),
            gemini_image,
        )

    def test_provider_error_returned_not_raised(self):
        session = self._painter_session()
        with patch.object(
            OpenAIProvider, 'generate_image', side_effect=UserError('boom')
        ):
            result = (
                self.env['muk_mcp.mixin']
                .with_context(muk_mcp_session_id=session.id)
                ._mcp_generate_image(prompt='a dot')
            )
        self.assertEqual(result['error'], 'boom')
        self.assertNotIn('content_base64', result)

    # ----------------------------------------------------------
    # Tests: storage and cost
    # ----------------------------------------------------------

    def test_stored_image_gets_an_embeddable_url(self):
        session = self.env['muk_ai.session'].create({'name': 'store'})
        stored = json.loads(
            session._persist_tool_file(json.dumps(self._tool_result(), indent=2))
        )
        self.assertNotIn('content_base64', stored)
        self.assertEqual(stored['image_url'], f'/web/image/{stored["attachment_id"]}')
        self.assertEqual(
            stored['url'], f'/web/content/{stored["attachment_id"]}?download=1'
        )
        self.assertEqual(stored['cost']['total'], 0.25)
        attachment = self.env['ir.attachment'].browse(stored['attachment_id'])
        self.assertEqual(attachment.mimetype, 'image/png')
        self.assertEqual(attachment.res_id, session.id)

    def test_non_image_files_get_no_image_url(self):
        session = self.env['muk_ai.session'].create({'name': 'csv'})
        stored = session._persist_tool_file(
            {
                'filename': 'x.csv',
                'mimetype': 'text/csv',
                'content_base64': base64.b64encode(b'a,b\n').decode(),
            }
        )
        self.assertNotIn('image_url', stored)

    def test_dispatch_settles_the_cost_at_image_rates(self):
        session = self._painter_session()
        patcher, calls = self._patch_tool(
            {'generate_image': json.dumps(self._tool_result(), indent=2)}
        )
        with patcher:
            _text, ok = session._dispatch_tool_call(
                'generate_image', {'prompt': 'a dot'}, 'call-1'
            )
        self.assertTrue(ok)
        self.assertEqual(calls, ['generate_image'])
        self.assertAlmostEqual(session.turn_cost_spent, 0.25)
        self.assertAlmostEqual(session.total_output_cost, 0.25)
        self.assertAlmostEqual(session.total_input_cost, 0.0)

    def test_a_result_cannot_bill_a_model_the_session_did_not_resolve(self):
        session = self._painter_session()
        expensive = self._create_model(
            'gpt-image-premium', modality='image', input_rate=0.0, output_rate=100.0
        )
        result = {
            **self._tool_result(),
            'cost': {'model_id': expensive.id, 'usage': {'images': 1}},
        }
        patcher, _calls = self._patch_tool(
            {'generate_image': json.dumps(result, indent=2)}
        )
        with patcher:
            session._dispatch_tool_call('generate_image', {'prompt': 'a dot'}, 'c1')
        self.assertAlmostEqual(session.turn_cost_spent, 0.25)

    def test_only_the_image_tool_reaches_the_cost_ledger(self):
        session = self._painter_session()
        patcher, _calls = self._patch_tool(
            {'mcp__remote__draw': json.dumps(self._tool_result(), indent=2)}
        )
        with patcher:
            session._dispatch_tool_call('mcp__remote__draw', {}, 'c1')
        self.assertEqual(session.turn_cost_spent, 0.0)

    def test_results_without_a_cost_block_charge_nothing(self):
        session = self._painter_session()
        for text in ('{"cost": 3}', '[{"cost": {"usage": {}}}]', '{"ok": true}'):
            session._settle_tool_cost('generate_image', text)
        self.assertEqual(session.turn_cost_spent, 0.0)

    def test_a_session_that_resolves_no_image_model_settles_nothing(self):
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Writer', 'enable_image_generation': False}
        )
        session = self._session(agent)
        session._settle_tool_cost(
            'generate_image', json.dumps(self._tool_result(), indent=2)
        )
        self.assertEqual(session.turn_cost_spent, 0.0)

    def test_settled_cost_stops_the_turn_at_the_limit(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_ai.turn_cost_limit', '0.2'
        )
        session = self._painter_session()
        call = {
            'text': '',
            'tool_calls': [
                {
                    'call_id': 'c1',
                    'name': 'generate_image',
                    'arguments': {'prompt': 'x'},
                }
            ],
            'carry_inputs': [
                {
                    'type': 'function_call',
                    'name': 'generate_image',
                    'arguments': '{"prompt": "x"}',
                    'call_id': 'c1',
                }
            ],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }
        patcher, calls = self._patch_tool(
            {'generate_image': json.dumps(self._tool_result(), indent=2)}
        )
        with patcher, self._mock_responses([call, self._make_text_response()]):
            session.start('draw')
        self.assertEqual(calls, ['generate_image'])
        self.assertEqual(session.state, 'error')
        self.assertIn('cost budget', session.error_message)
        self.assertGreaterEqual(session.turn_cost_spent, 0.25)


class TestImageModelResolution(ToolCatalogMixin, ImageCase):
    """Verify the image model resolves agent, own provider, then the others."""

    catalog = [
        {'name': 'generate_image', 'description': 'draw', 'inputSchema': {}},
        {'name': 'web_fetch', 'description': 'fetch', 'inputSchema': {}},
    ]

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self._clear_default_models('image')
        self.gemini_image = self.env.ref('muk_ai.model_gemini_3_1_flash_image')
        self.provider.default_image_model_id = self.image
        self.provider_google.write(
            {
                'default_image_model_id': self.gemini_image.id,
                'sequence': 30,
                'active': True,
            }
        )
        self.provider_anthropic.write({'sequence': 20, 'active': True})
        self.agent = self.env['muk_ai.agent'].create(
            {'name': 'Drawer', 'enable_image_generation': True}
        )
        self.session = self._session(self.agent)

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _catalog_names(self) -> set[str]:
        """Return the tool names the session currently offers."""
        with self._patch_catalog():
            return {entry['name'] for entry in self.session._get_filtered_catalog()}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_agent_pick_wins(self):
        self.assertEqual(self.agent._resolve_model_for('image'), self.image)
        self.agent.image_model_id = self.gemini_image
        self.assertEqual(self.agent._resolve_model_for('image'), self.gemini_image)
        self.assertEqual(self.session._resolve_model_for('image'), self.gemini_image)

    def test_the_own_provider_default_beats_the_company_default(self):
        self.assertEqual(self.env.company.default_ai_provider_id, self.provider)
        self.agent.model_id = self.env.ref('muk_ai.model_gemini_3_8_flash')
        self.assertEqual(self.agent._resolve_model_for('image'), self.gemini_image)

    def test_the_fallback_crosses_providers_by_sequence(self):
        self.agent.model_id = self.chat_anthropic
        self.assertFalse(self.provider_anthropic.default_image_model_id)
        self.assertEqual(self.agent._resolve_model_for('image'), self.image)
        self.provider.default_image_model_id = False
        self.assertEqual(self.agent._resolve_model_for('image'), self.gemini_image)
        self.provider_google.default_image_model_id = False
        self.assertFalse(self.agent._resolve_model_for('image'))

    def test_the_toggle_gates_the_tool(self):
        self.assertEqual(self._catalog_names(), {'web_fetch', 'generate_image'})
        self.agent.enable_image_generation = False
        self.assertFalse(self.agent._resolve_model_for('image'))
        self.assertEqual(self._catalog_names(), {'web_fetch'})
        self.agent.enable_image_generation = True
        self._clear_default_models('image')
        self.assertEqual(self._catalog_names(), {'web_fetch'})
