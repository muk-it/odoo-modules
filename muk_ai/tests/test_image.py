from __future__ import annotations

import base64
import re
from unittest.mock import MagicMock, patch

import urllib3.exceptions

from odoo.addons.muk_ai.models import session as session_module
from odoo.addons.muk_ai.tests.common import AITestCommon

PNG_1x1_RED = base64.b64encode(
    bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
        '890000000d49444154789c63f8cf00000003000100184b96c10000000049454e'
        '44ae426082'
    )
).decode()


class TestImageRefPersistence(AITestCommon):
    """Verify generated-image reference extraction and attachment persistence."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.session = (
            self.env['muk_ai.session']
            .sudo()
            .create(
                {
                    'name': 'image-refs-test',
                    'user_id': self.env.user.id,
                }
            )
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _extract_attachment_id(text: str) -> int | None:
        """Return the id of the first ``@attachment:`` reference in ``text``."""
        match = re.search(r'@attachment:(\d+)', text)
        return int(match.group(1)) if match else None

    def _count_session_attachments(self) -> int:
        """Count the attachments linked to the session under test."""
        return (
            self.env['ir.attachment']
            .sudo()
            .search_count(
                [
                    ('res_model', '=', 'muk_ai.session'),
                    ('res_id', '=', self.session.id),
                ]
            )
        )

    # ----------------------------------------------------------
    # Persist
    # ----------------------------------------------------------

    def test_inline_image_is_persisted_as_attachment(self):
        text = f'Here you go: ![generated.png](data:image/png;base64,{PNG_1x1_RED})'
        before = self._count_session_attachments()
        new_text = self.session._persist_inline_images(text)
        after = (
            self.env['ir.attachment']
            .sudo()
            .search(
                [
                    ('res_model', '=', 'muk_ai.session'),
                    ('res_id', '=', self.session.id),
                ]
            )
        )
        self.assertEqual(len(after) - before, 1)
        attachment = after[-1]
        self.assertIn(f'/web/image/{attachment.id}', new_text)
        self.assertIn(f'@attachment:{attachment.id}', new_text)
        self.assertNotIn('data:image/png;base64,', new_text)

    def test_persist_caches_duplicate_blobs(self):
        text = (
            f'A: ![a.png](data:image/png;base64,{PNG_1x1_RED}) '
            f'B: ![b.png](data:image/png;base64,{PNG_1x1_RED})'
        )
        before = self._count_session_attachments()
        new_text = self.session._persist_inline_images(text, cache={})
        after = self._count_session_attachments()
        self.assertEqual(after - before, 1)
        self.assertIn('/web/image/', new_text)

    def test_persist_text_and_carry_share_one_attachment(self):
        b64_text = f'Reply: ![x.png](data:image/png;base64,{PNG_1x1_RED})'
        carry = [
            {
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': b64_text}],
            }
        ]
        before = self._count_session_attachments()
        cache = {}
        new_text = self.session._persist_inline_images(b64_text, cache=cache)
        new_carry = self.session._persist_inline_images_in_carry(carry, cache)
        after = self._count_session_attachments()
        self.assertEqual(after - before, 1)
        carry_text = new_carry[0]['content'][0]['text']
        self.assertEqual(
            self._extract_attachment_id(new_text),
            self._extract_attachment_id(carry_text),
        )

    def test_persist_skips_text_without_inline_images(self):
        text = 'Just plain text, no images here.'
        before = self.env['ir.attachment'].sudo().search_count([])
        result = self.session._persist_inline_images(text)
        after = self.env['ir.attachment'].sudo().search_count([])
        self.assertEqual(result, text)
        self.assertEqual(before, after)

    # ----------------------------------------------------------
    # Resolve
    # ----------------------------------------------------------

    def test_resolve_attachment_ref_loads_bytes(self):
        attachment = (
            self.env['ir.attachment']
            .sudo()
            .create(
                {
                    'name': 'test.png',
                    'datas': PNG_1x1_RED,
                    'mimetype': 'image/png',
                    'res_model': 'muk_ai.session',
                    'res_id': self.session.id,
                }
            )
        )
        args = {
            'model': 'product.template',
            'ids': [1],
            'values': {'image_1920': f'@attachment:{attachment.id}'},
        }
        resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], PNG_1x1_RED)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['kind'], 'attachment')
        self.assertEqual(refs[0]['preview_url'], f'/web/image/{attachment.id}')

    def test_resolve_attachment_ref_unknown_id_keeps_placeholder(self):
        args = {'values': {'image_1920': '@attachment:999999999'}}
        resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], '@attachment:999999999')
        self.assertEqual(refs, [])

    def test_resolve_attachment_ref_oversized_keeps_placeholder(self):
        attachment = (
            self.env['ir.attachment']
            .sudo()
            .create(
                {
                    'name': 'big.png',
                    'datas': PNG_1x1_RED,
                    'mimetype': 'image/png',
                    'res_model': 'muk_ai.session',
                    'res_id': self.session.id,
                }
            )
        )
        with patch.object(session_module, 'ATTACHMENT_REF_MAX_BYTES', 0):
            args = {'values': {'image_1920': f'@attachment:{attachment.id}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(
            resolved['values']['image_1920'], f'@attachment:{attachment.id}'
        )
        self.assertEqual(refs, [])

    def test_resolve_attachment_ref_disallowed_mimetype_keeps_placeholder(self):
        attachment = (
            self.env['ir.attachment']
            .sudo()
            .create(
                {
                    'name': 'evil.bin',
                    'datas': PNG_1x1_RED,
                    'res_model': 'muk_ai.session',
                    'res_id': self.session.id,
                }
            )
        )
        attachment.sudo().mimetype = 'application/octet-stream'
        args = {'values': {'image_1920': f'@attachment:{attachment.id}'}}
        resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(
            resolved['values']['image_1920'], f'@attachment:{attachment.id}'
        )
        self.assertEqual(refs, [])

    def test_resolve_url_ref_fetches_and_b64_encodes(self):
        png_bytes = base64.b64decode(PNG_1x1_RED)
        response = MagicMock()
        response.status = 200
        response.stream.return_value = iter([png_bytes])
        response.release_conn.return_value = None
        pool = MagicMock()
        pool.urlopen.return_value = response
        pool.close.return_value = None
        url = 'https://example.com/cat.png'
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=[(0, 0, 0, '', ('8.8.8.8', 0))],
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=pool,
            ) as mock_pool_cls,
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        mock_pool_cls.assert_called_once()
        pool.urlopen.assert_called_once()
        self.assertEqual(resolved['values']['image_1920'], PNG_1x1_RED)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['kind'], 'url')
        self.assertEqual(refs[0]['preview_url'], url)

    def test_resolve_url_ref_swallows_fetch_error(self):
        url = 'https://example.com/broken.png'
        pool = MagicMock()
        pool.urlopen.side_effect = urllib3.exceptions.HTTPError('500')
        pool.close.return_value = None
        with (
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
                return_value=[(0, 0, 0, '', ('8.8.8.8', 0))],
            ),
            patch(
                'odoo.addons.muk_ai.tools.url_fetch.urllib3.HTTPSConnectionPool',
                return_value=pool,
            ),
        ):
            args = {'values': {'image_1920': f'@url:{url}'}}
            resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], f'@url:{url}')
        self.assertEqual(refs, [])

    def test_resolve_walks_nested_dicts_and_lists(self):
        attachment = (
            self.env['ir.attachment']
            .sudo()
            .create(
                {
                    'name': 'nested.png',
                    'datas': PNG_1x1_RED,
                    'mimetype': 'image/png',
                }
            )
        )
        args = {
            'values': {
                'main_image': f'@attachment:{attachment.id}',
                'gallery': [
                    f'@attachment:{attachment.id}',
                    'plain string',
                ],
                'meta': {'thumbnail': f'@attachment:{attachment.id}'},
            },
        }
        resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['main_image'], PNG_1x1_RED)
        self.assertEqual(resolved['values']['gallery'][0], PNG_1x1_RED)
        self.assertEqual(resolved['values']['gallery'][1], 'plain string')
        self.assertEqual(resolved['values']['meta']['thumbnail'], PNG_1x1_RED)
        self.assertEqual(len(refs), 3)

    def test_resolve_leaves_non_ref_strings_intact(self):
        args = {'values': {'name': 'Hello world', 'image_1920': PNG_1x1_RED}}
        resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['name'], 'Hello world')
        self.assertEqual(resolved['values']['image_1920'], PNG_1x1_RED)
        self.assertEqual(refs, [])

    # ----------------------------------------------------------
    # Integration
    # ----------------------------------------------------------

    def test_full_loop_generated_image_persists_then_resolves_to_bytes(self):
        text = f'Here is your image: ![chair.png](data:image/png;base64,{PNG_1x1_RED})'
        new_text = self.session._persist_inline_images(text)
        attachment_id = self._extract_attachment_id(new_text)
        self.assertIsNotNone(attachment_id)
        args = {
            'model': 'product.template',
            'ids': [1],
            'values': {'image_1920': f'@attachment:{attachment_id}'},
        }
        resolved, refs = self.session._resolve_value_refs(args)
        self.assertEqual(resolved['values']['image_1920'], PNG_1x1_RED)
        self.assertEqual(refs[0]['preview_url'], f'/web/image/{attachment_id}')
