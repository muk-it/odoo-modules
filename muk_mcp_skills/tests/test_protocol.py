from __future__ import annotations

import base64
import hashlib
from typing import Any

import yaml

from odoo import Command
from odoo.tools import BinaryBytes

from odoo.addons.muk_mcp.tests.common import MCPHttpCase
from odoo.addons.muk_mcp.tools import version
from odoo.addons.muk_mcp_skills.tools.constants import EXTENSION_KEY

URI = 'skill://invoice-check/SKILL.md'


class TestSkillsProtocol(MCPHttpCase):
    """Load skills through the MCP endpoint the way a client does."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a skill whose texts and files are hard to transport."""
        super().setUpClass()
        cls.env['muk_mcp_skills.skill'].search([]).active = False
        cls.skill = cls.env['muk_mcp_skills.skill'].create(
            {
                'name': 'invoice-check',
                'description': 'Check: "invoices" # \U0001f9fe\nUse it for bills \\ refunds.',
                'body': '# Prüfung\n\nRead `rules & limits.md`.',
                'attachment_ids': [
                    Command.create({'name': name, 'raw': BinaryBytes(raw)})
                    for name, raw in (
                        ('rules & limits.md', 'Größe < 5 €\r\n'.encode()),
                        ('logo.png', b'\x89PNG\r\n\x1a\n\x00'),
                        ('empty.txt', b''),
                    )
                ],
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        """Send a stateless request and return its JSON-RPC answer."""
        return self.mcp_stateless_post(method, params).json()

    def read(self, uri: str) -> bytes:
        """Return the bytes ``resources/read`` answers for ``uri``."""
        [content] = self.call('resources/read', uri=uri)['result']['contents']
        if 'text' in content:
            return content['text'].encode()
        return base64.b64decode(content['blob'])

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_only_the_stateless_revision_offers_skills(self):
        discovered = self.call('server/discover')['result']['capabilities']
        self.assertIn(EXTENSION_KEY, discovered['extensions'])
        self.assertIn('resources', discovered)
        initialized = self.mcp_call(
            'initialize', {'protocolVersion': version.MCP_VERSION_2025_11_25}
        ).json()['result']['capabilities']
        self.assertNotIn(EXTENSION_KEY, initialized.get('extensions', {}))
        self.assertEqual(self.mcp_call('skills/list').json()['error']['code'], -32601)

    def test_a_listed_skill_verifies_against_its_files(self):
        result = self.call('skills/list')['result']
        self.assertEqual(result['cacheScope'], 'private')
        self.assertIn('ttlMs', result)
        [entry] = result['skills']
        self.assertEqual(entry['uri'], URI)
        self.assertCountEqual(
            [resource['uri'] for resource in entry['resources']],
            [
                URI,
                'skill://invoice-check/rules%20%26%20limits.md',
                'skill://invoice-check/logo.png',
                'skill://invoice-check/empty.txt',
            ],
        )
        for resource in entry['resources']:
            with self.subTest(resource['uri']):
                raw = self.read(resource['uri'])
                self.assertEqual(len(raw), resource['size'])
                self.assertEqual(
                    f'sha256:{hashlib.sha256(raw).hexdigest()}', resource['digest']
                )
        _, frontmatter, body = self.read(URI).decode().split('---\n', 2)
        self.assertEqual(yaml.safe_load(frontmatter), entry['frontmatter'])
        self.assertEqual(entry['frontmatter']['description'], self.skill.description)
        self.assertEqual(body.strip(), self.skill.body)

    def test_an_uploaded_text_file_reads_as_text(self):
        self.skill.attachment_ids.mimetype = 'application/octet-stream'
        for name, key in (('rules%20%26%20limits.md', 'text'), ('logo.png', 'blob')):
            with self.subTest(name):
                uri = f'skill://invoice-check/{name}'
                [content] = self.call('resources/read', uri=uri)['result']['contents']
                self.assertIn(key, content)

    def test_get_returns_the_listed_entry(self):
        [entry] = self.call('skills/list')['result']['skills']
        result = self.call('skills/get', uri=URI)['result']
        self.assertEqual(result['skill'], entry)
        self.assertEqual(result['cacheScope'], 'private')

    def test_a_changed_file_changes_the_entry(self):
        before = self.call('skills/get', uri=URI)['result']['skill']['resources']
        self.skill.body = 'Something else.'
        after = self.call('skills/get', uri=URI)['result']['skill']['resources']
        self.assertNotEqual(before[0]['digest'], after[0]['digest'])
        self.assertEqual(before[1:], after[1:])

    def test_a_skill_out_of_reach_is_not_served(self):
        group = self.env.ref('base.group_system')
        for label, values in (
            ('other group', {'group_ids': [Command.set(group.ids)]}),
            ('archived', {'group_ids': [Command.clear()], 'active': False}),
        ):
            with self.subTest(label):
                self.skill.write(values)
                self.assertEqual(self.call('skills/list')['result']['skills'], [])
                for method in ('skills/get', 'resources/read'):
                    answer = self.call(method, uri=URI)
                    self.assertEqual(answer['error']['code'], -32602)
        self.skill.write(
            {
                'active': True,
                'group_ids': [Command.set(self.env.ref('base.group_user').ids)],
            }
        )
        self.assertEqual(len(self.call('skills/list')['result']['skills']), 1)

    def test_other_resources_stay_readable(self):
        attachment = self.env['ir.attachment'].create(
            {
                'name': 'notes.txt',
                'raw': BinaryBytes(b'hi'),
                'res_model': 'res.partner',
                'res_id': self.mcp_user.partner_id.id,
            }
        )
        self.assertEqual(self.read(f'odoo://attachment/{attachment.id}'), b'hi')

    def test_unknown_uris_are_refused(self):
        for method, uri in (
            ('skills/get', 'skill://invoice-check/logo.png'),
            ('skills/get', 'skill://invoice-check'),
            ('skills/get', 'skill://unknown/SKILL.md'),
            ('skills/get', None),
            ('resources/read', 'skill://invoice-check/missing.md'),
            ('resources/read', 'skill://unknown/SKILL.md'),
        ):
            with self.subTest(method, uri=uri):
                answer = self.call(method, **({'uri': uri} if uri else {}))
                self.assertEqual(answer['error']['code'], -32602)
