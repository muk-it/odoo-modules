from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import patch

from odoo.tests import new_test_user
from odoo.tools import BinaryBytes, config

from odoo.addons.mail.tools.discuss import Store
from odoo.addons.muk_mcp.tests.common import PNG, MCPHttpCase, make_mcp_key
from odoo.addons.muk_mcp.tools import version
from odoo.addons.muk_mcp.tools.common import MCP_ENDPOINT


class TestMcpHttp(MCPHttpCase):
    """Cover authentication, framing and the handshake era of the MCP endpoint."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the probe tools and the fixtures the requests act on."""
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'MCP Http Partner'})
        cls.env['muk_mcp.tool'].create(
            [
                {
                    'name': 'mcp_test_probe',
                    'description': 'Report the caller.',
                    'code': (
                        'result = {"uid": env.uid, '
                        '"mcp_name": env.context.get("mcp_name")}\n'
                    ),
                },
                {
                    'name': 'mcp_test_partial',
                    'category': 'write',
                    'description': 'Create a partner, then fail.',
                    'code': (
                        'env["res.partner"].create({"name": "MCP Partial Write"})\n'
                        'result = 1 / 0\n'
                    ),
                },
            ],
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tool_json(self, name: str, arguments=None, **kwargs: Any) -> dict:
        """Call tool ``name`` over HTTP and decode its JSON text result."""
        return json.loads(
            self.mcp_tool(name, arguments, **kwargs)['content'][0]['text']
        )

    def _read_resource(self, uri: str) -> dict:
        """Read ``uri`` through ``resources/read`` and return the decoded body."""
        return self.mcp_call('resources/read', {'uri': uri}).json()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_rejected_credentials(self):
        for label, kwargs in (
            ('no header', {'token': False}),
            ('basic scheme', {'headers': {'Authorization': 'Basic abc'}}),
            ('bare token', {'headers': {'Authorization': self.mcp_token}}),
            ('empty bearer', {'headers': {'Authorization': 'Bearer   '}}),
            ('unknown token', {'token': 'no-such-token'}),
        ):
            with self.subTest(label):
                response = self.mcp_post(**kwargs)
                self.assertEqual(response.status_code, 401)
                self.assertRegex(response.headers['WWW-Authenticate'], '(?i)^bearer')

    def test_revoked_keys_are_rejected(self):
        for revoke in ('key', 'user'):
            with self.subTest(revoke):
                user = new_test_user(self.env, login=f'mcp_revoked_{revoke}')
                token, key = make_mcp_key(user)
                self.assertEqual(self.mcp_call('ping', token=token).status_code, 200)
                (key if revoke == 'key' else user).active = False
                self.assertEqual(self.mcp_post(token=token).status_code, 401)

    def test_key_authenticates_as_its_owner(self):
        for scheme in ('bearer', 'BEARER'):
            with self.subTest(scheme):
                result = self._tool_json(
                    'mcp_test_probe',
                    headers={'Authorization': f'{scheme} {self.mcp_token}'},
                )
                self.assertEqual(
                    result,
                    {'uid': self.mcp_user.id, 'mcp_name': self.mcp_key.name},
                )
        self.assertTrue(self.mcp_key.last_used)
        self.env['ir.config_parameter'].set_bool('muk_mcp.annotate_messages', False)
        self.assertIsNone(self._tool_json('mcp_test_probe')['mcp_name'])

    def test_chatter_messages_name_the_key(self):
        result = self._tool_json(
            'post_message',
            {'model': 'res.partner', 'id': self.partner.id, 'body': '<p>Hi</p>'},
        )
        message = self.env['mail.message'].browse(result['id'])
        self.assertEqual(message.mcp_name, self.mcp_key.name)
        self.assertIn('<p>Hi</p>', message.body)
        store = Store().add(message, '_store_message_fields').as_dict()
        self.assertEqual(store['mail.message'][0]['mcp_name'], self.mcp_key.name)

    def test_malformed_requests_are_rejected(self):
        ping = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
        for body, code in (
            ('{not json', -32700),
            ('5', -32600),
            (json.dumps([ping, ping]), -32600),
            ('[]', -32600),
            (json.dumps({'id': 1, 'method': 'ping'}), -32600),
            (json.dumps({**ping, 'jsonrpc': '1.0'}), -32600),
            (json.dumps({'jsonrpc': '2.0', 'id': 1}), -32600),
            (json.dumps({**ping, 'method': 42}), -32600),
            (json.dumps({**ping, 'params': [1]}), -32600),
        ):
            with self.subTest(body):
                response = self.mcp_post(body=body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error']['code'], code)

    def test_notification_is_accepted_without_a_reply(self):
        response = self.mcp_post(
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b'')

    def test_only_post_is_routed(self):
        for method in ('GET', 'DELETE'):
            with self.subTest(method):
                response = self.url_open(
                    MCP_ENDPOINT,
                    headers={'Authorization': f'Bearer {self.mcp_token}'},
                    method=method,
                )
                self.assertEqual(response.status_code, 405)

    def test_cors_preflight_allows_the_mcp_headers(self):
        response = self.url_open(MCP_ENDPOINT, method='OPTIONS')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], '*')
        allowed = response.headers['Access-Control-Allow-Headers']
        for header in ('Authorization', 'MCP-Protocol-Version', 'Mcp-Method'):
            self.assertIn(header, allowed)

    def test_origin_allow_list(self):
        params = self.env['ir.config_parameter']
        base_url = self.base_url()
        for label, setup, origin, status in (
            ('no origin', None, None, 200),
            ('same origin', None, base_url, 200),
            ('foreign origin', None, 'https://evil.example', 403),
            (
                'configured origin',
                lambda: params.set_str(
                    'muk_mcp.allowed_origins',
                    'https://partner.example, https://other.example/',
                ),
                'https://other.example',
                200,
            ),
            (
                'request host is not trusted',
                lambda: params.set_str('web.base.url', 'https://real.example'),
                base_url,
                403,
            ),
            (
                'any origin',
                lambda: params.set_bool('muk_mcp.allow_any_origin', True),
                'https://evil.example',
                200,
            ),
        ):
            with self.subTest(label):
                if setup:
                    setup()
                response = self.mcp_call('ping', headers={'Origin': origin})
                self.assertEqual(response.status_code, status)
        self.assertEqual(
            len(self.logs([('method', '=', 'origin_rejected')])),
            2,
        )

    def test_rate_limit_answers_429_and_is_audited(self):
        token, key = make_mcp_key(self.mcp_user, rate_limit=2)
        statuses = [self.mcp_call('ping', token=token).status_code for _i in range(3)]
        self.assertEqual(statuses, [200, 200, 429])
        response = self.mcp_call('ping', token=token)
        self.assertEqual(response.json()['error']['message'], 'Rate limit exceeded')
        log = self.logs([('key_prefix', '=', key.key_prefix)])
        self.assertEqual(log.mapped('status'), ['rate_limited', 'rate_limited'])

    def test_initialize_negotiates_a_handshake_revision(self):
        for requested, negotiated in (
            (version.MCP_VERSION_2025_06_18, version.MCP_VERSION_2025_06_18),
            (version.MCP_VERSION_2025_11_25, version.MCP_VERSION_2025_11_25),
            (version.MCP_VERSION_2026_07_28, version.MCP_VERSION_2025_11_25),
            ('1999-01-01', version.MCP_VERSION_2025_11_25),
            (None, version.MCP_VERSION_2025_11_25),
        ):
            with self.subTest(requested):
                result = self.mcp_call(
                    'initialize',
                    {'protocolVersion': requested},
                ).json()['result']
                self.assertEqual(result['protocolVersion'], negotiated)
                self.assertFalse(result['capabilities']['tools']['listChanged'])
                self.assertEqual(result['serverInfo']['name'], 'odoo-mcp-server')
                self.assertNotIn('resultType', result)

    def test_handshake_era_requests(self):
        for method, headers, status, code in (
            ('ping', None, 200, None),
            ('tools/list', None, 200, None),
            ('tools/list', {'MCP-Protocol-Version': '2025-06-18'}, 200, None),
            ('tools/list', {'MCP-Protocol-Version': '1999-01-01'}, 400, -32022),
            ('server/discover', None, 200, -32601),
            ('nope/nope', None, 200, -32601),
        ):
            with self.subTest(method=method, headers=headers):
                response = self.mcp_call(method, headers=headers)
                self.assertEqual(response.status_code, status)
                body = response.json()
                self.assertEqual(body.get('error', {}).get('code'), code)
                if code is None:
                    self.assertNotIn('resultType', body['result'])
        tools = self.mcp_call('tools/list').json()['result']['tools']
        hints = {tool['name']: tool['annotations']['readOnlyHint'] for tool in tools}
        self.assertEqual((hints['search_read'], hints['create_records']), (True, False))

    def test_tool_call_errors_are_tool_results(self):
        for params, message in (
            (None, 'Tool name is required'),
            ({'name': 'no_such_tool'}, 'Tool not found'),
            ({'name': 'mcp_test_probe', 'arguments': ['a']}, 'must be a JSON object'),
        ):
            with self.subTest(params):
                response = self.mcp_post(
                    {
                        'jsonrpc': '2.0',
                        'id': 1,
                        'method': 'tools/call',
                        'params': params,
                    },
                )
                result = response.json()['result']
                self.assertTrue(result['isError'])
                self.assertIn(message, result['content'][0]['text'])
        log = self.logs([('tool_name', '=', 'mcp_test_probe')])
        self.assertEqual(log.status, 'error')
        self.assertIn('must be a JSON object', log.error_message)

    def test_failed_tool_call_rolls_back_and_hides_the_traceback(self):
        result = self.mcp_tool('mcp_test_partial')
        self.assertTrue(result['isError'])
        text = result['content'][0]['text']
        self.assertTrue(text.startswith('Internal server error:'))
        self.assertNotIn('Traceback', text)
        self.assertFalse(
            self.env['res.partner'].search([('name', '=', 'MCP Partial Write')]),
        )
        log = self.logs([('tool_name', '=', 'mcp_test_partial')])
        self.assertEqual(
            (log.status, log.key_name, log.ip_address),
            ('error', self.mcp_key.name, '127.0.0.1'),
        )
        with patch.dict(config.options, {'mcp_debug': True}):
            text = self.mcp_tool('mcp_test_partial')['content'][0]['text']
        self.assertIn('Traceback', text)

    def test_read_scope_key_cannot_write(self):
        token, key = make_mcp_key(self.mcp_user, scope='read')
        result = self.mcp_tool(
            'create_records',
            {'model': 'res.partner', 'values': {'name': 'MCP Denied'}},
            token=token,
        )
        self.assertTrue(result['isError'])
        self.assertIn('read-only', result['content'][0]['text'])
        log = self.logs([('key_prefix', '=', key.key_prefix)])
        self.assertEqual(log.status, 'denied')

    def test_export_honours_the_export_right(self):
        arguments = {
            'model': 'res.partner',
            'fields': ['name'],
            'ids': [self.partner.id],
        }
        result = self.mcp_tool('export_records', arguments)
        self.assertTrue(result['isError'])
        self.assertIn('rights to export data', result['content'][0]['text'])
        self.mcp_user.group_ids = [(4, self.env.ref('base.group_allow_export').id)]
        content = base64.b64decode(
            self._tool_json('export_records', arguments)['content_base64'],
        )
        self.assertIn('MCP Http Partner', content.decode('utf-8-sig'))

    def test_prompts_run_as_the_caller(self):
        company_a, company_b, company_c = self.env['res.company'].create(
            [
                {'name': 'MCP Prompt A'},
                {'name': 'MCP Prompt B'},
                {'name': 'MCP Prompt C'},
            ],
        )
        user = new_test_user(
            self.env,
            login='mcp_prompt_user',
            company_id=company_a.id,
            company_ids=[(6, 0, [company_a.id, company_b.id])],
        )
        token, _key = make_mcp_key(user)
        partners = self.env['res.partner'].create(
            [
                {'name': 'MCP Prompt', 'company_id': company.id}
                for company in (
                    company_a,
                    company_b,
                    company_c,
                )
            ],
        )
        self.env['muk_mcp.prompt'].create(
            {
                'name': 'mcp_test_prompt',
                'title': 'Probe',
                'description': 'Probe.',
                'body': (
                    'result = "%%s|%%s" %% (env.su, env["res.partner"].search_count('
                    '[("id", "in", %s)]))\n' % partners.ids
                ),
            },
        )
        result = self.mcp_call(
            'prompts/get',
            {'name': 'mcp_test_prompt'},
            token=token,
        ).json()['result']
        self.assertEqual(result['messages'][0]['content']['text'], 'False|2')
        prompts = self.mcp_call('prompts/list').json()['result']['prompts']
        self.assertIn('mcp_test_prompt', {prompt['name'] for prompt in prompts})

    def test_prompt_errors(self):
        self.env['muk_mcp.prompt'].create(
            {
                'name': 'mcp_test_broken',
                'title': 'Broken',
                'description': 'Fail.',
                'body': 'result = 1 / 0',
            },
        )
        for params, status, code, message in (
            (None, 400, -32602, 'Prompt not found'),
            ({'name': 'no_such_prompt'}, 400, -32602, 'Prompt not found'),
            (
                {'name': 'summarize_record', 'arguments': {'model': 'res.partner'}},
                400,
                -32602,
                'Missing required prompt arguments: record_id',
            ),
            ({'name': 'mcp_test_broken'}, 200, -32603, 'Internal server error'),
        ):
            with self.subTest(params):
                response = self.mcp_post(
                    {
                        'jsonrpc': '2.0',
                        'id': 1,
                        'method': 'prompts/get',
                        'params': params,
                    },
                )
                self.assertEqual(response.status_code, status)
                error = response.json()['error']
                self.assertEqual(error['code'], code)
                self.assertIn(message, error['message'])
        log = self.logs([('method', '=', 'prompts/get')])
        self.assertEqual(log.status, 'error')

    def test_completion_suggests_model_names(self):
        result = self.mcp_call(
            'completion/complete',
            {
                'ref': {'type': 'ref/prompt', 'name': 'summarize_record'},
                'argument': {'name': 'model', 'value': 'res.par'},
            },
        ).json()['result']
        self.assertIn('res.partner', result['completion']['values'])

    def test_resources_read_round_trip(self):
        data = bytes(range(256))
        binary, text = self.env['ir.attachment'].create(
            [
                {
                    'name': 'blob.bin',
                    'mimetype': 'application/octet-stream',
                    'raw': BinaryBytes(data),
                    'res_model': 'res.partner',
                    'res_id': self.partner.id,
                },
                {
                    'name': 'notes.txt',
                    'mimetype': 'text/plain',
                    'raw': BinaryBytes(b'hello'),
                    'res_model': 'res.partner',
                    'res_id': self.partner.id,
                },
            ],
        )
        entry = self._read_resource(f'odoo://attachment/{binary.id}')['result']
        self.assertEqual(base64.b64decode(entry['contents'][0]['blob']), data)
        self.assertEqual(entry['contents'][0]['name'], 'blob.bin')
        block = self.mcp_tool(
            'read_resource', {'uri': f'odoo://attachment/{binary.id}'}
        )
        self.assertEqual(
            base64.b64decode(block['content'][0]['resource']['blob']), data
        )
        entry = self._read_resource(f'odoo://attachment/{text.id}')['result']
        self.assertEqual(entry['contents'][0]['text'], 'hello')
        self.partner.image_1920 = PNG
        uri = f'odoo://record/res.partner/{self.partner.id}/image_1920'
        entry = self._read_resource(uri)['result']['contents'][0]
        self.assertEqual(entry['mimeType'], 'image/png')
        self.assertEqual(
            base64.b64decode(entry['blob']),
            self.partner.image_1920.content,
        )

    def test_unreadable_resources_are_not_found(self):
        cron = self.env['ir.cron'].search([], limit=1)
        forbidden = self.env['ir.attachment'].create(
            {
                'name': 'cron.txt',
                'raw': BinaryBytes(b'secret'),
                'res_model': 'ir.cron',
                'res_id': cron.id,
            },
        )
        for uri in (
            f'odoo://attachment/{forbidden.id}',
            'odoo://attachment/999999999',
            'https://example.com/file.png',
            None,
        ):
            with self.subTest(uri):
                response = self.mcp_call('resources/read', {'uri': uri})
                self.assertEqual(response.status_code, 400)
                error = response.json()['error']
                self.assertEqual(error['code'], -32602)
                self.assertEqual(error['data']['uri'], uri or '')
