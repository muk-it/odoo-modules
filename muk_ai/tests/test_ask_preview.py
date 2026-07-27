from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai.tools import clean_ask_preview


@tagged('post_install', '-at_install', 'muk_ai')
class TestAskPreview(TransactionCase):
    """Verify model-supplied ask_user previews are coerced to renderable shape."""

    def test_none_and_non_dict_dropped(self):
        self.assertIsNone(clean_ask_preview(None))
        self.assertIsNone(clean_ask_preview('update'))
        self.assertIsNone(clean_ask_preview([{'kind': 'update'}]))

    def test_unknown_kind_dropped(self):
        self.assertIsNone(clean_ask_preview({'kind': 'explode'}))
        self.assertIsNone(clean_ask_preview({'title': 'No kind'}))

    def test_update_without_changes_gets_empty_lists(self):
        cleaned = clean_ask_preview(
            {'kind': 'update', 'model': 'res.partner', 'title': 'Update'}
        )
        self.assertEqual(cleaned['kind'], 'update')
        self.assertEqual(cleaned['changes'], [])
        self.assertEqual(cleaned['targets'], [])
        self.assertEqual(cleaned['title'], 'Update')

    def test_list_fields_keep_only_dicts(self):
        cleaned = clean_ask_preview(
            {
                'kind': 'delete',
                'targets': [{'id': 1, 'display_name': 'A'}, 'junk', 7],
            }
        )
        self.assertEqual(cleaned['targets'], [{'id': 1, 'display_name': 'A'}])

    def test_create_and_call_shapes(self):
        created = clean_ask_preview({'kind': 'create', 'properties': None})
        self.assertEqual(created['properties'], [])
        called = clean_ask_preview({'kind': 'call', 'method': 'action_post'})
        self.assertEqual(called['targets'], [])
        self.assertEqual(called['method'], 'action_post')

    def test_register_ask_user_sanitizes_preview(self):
        session = self.env['muk_ai.session'].create({'name': 'ask-preview'})
        session._register_ask_user(
            {
                'call_id': 'c-ask',
                'arguments': {
                    'question': 'Proceed?',
                    'resolution': 'yesno',
                    'preview': {'kind': 'update', 'model': 'res.partner'},
                },
            }
        )
        preview = session.pending_ask['preview']
        self.assertEqual(preview['changes'], [])
        self.assertEqual(preview['targets'], [])
