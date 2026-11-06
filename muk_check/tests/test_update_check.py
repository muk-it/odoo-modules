from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from odoo.api import call_kw
from odoo.exceptions import AccessDenied
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

import odoo.addons
from odoo.addons.muk_check.models.ir_module_module import IrModuleModule

STORE_POST = 'odoo.addons.muk_check.models.ir_module_module.requests.post'
IMAGE_BUILDS = 'odoo.addons.muk_check.models.check_rule.fetch_image_builds'


@tagged('post_install', '-at_install')
class TestUpdateCheck(TransactionCase):
    """Cover the update check over a real addon folder on the addons path."""

    @classmethod
    def setUpClass(cls) -> None:
        """Put an empty folder on the addons path and activate German."""
        super().setUpClass()
        cls.env['res.lang']._activate_lang('de_DE')
        addons_path = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, addons_path)
        cls.classPatch(odoo.addons, '__path__', [*odoo.addons.__path__, addons_path])
        cls.module_name = f'muk_fixture_{uuid.uuid4().hex}'
        cls.root = Path(addons_path) / cls.module_name
        cls.admin = new_test_user(
            cls.env, 'update_admin', 'base.group_system', email='admin@example.com'
        )

    def setUp(self) -> None:
        """Write the fixture addon and register it with saved baselines."""
        super().setUp()
        self.startPatcher(patch(IMAGE_BUILDS, return_value={}))
        self._write_addon()
        self.module = self.env['ir.module.module'].create(
            {
                'name': self.module_name,
                'shortdesc': 'Fixture Addon',
                'author': 'Acme',
                'state': 'installed',
            }
        )
        self.module._save_upgrade_baseline()
        self.module._save_translation_baseline()

    def _write_addon(self) -> None:
        """Write the fixture addon to disk, replacing an earlier state."""
        shutil.rmtree(self.root, ignore_errors=True)
        files = {
            '__manifest__.py': (
                "{'name': 'Fixture', 'author': 'Acme', 'license': 'LGPL-3', "
                "'version': '17.0.1.0.0', 'data': ['data/records.xml']}"
            ),
            'data/records.xml': '<odoo/>',
            'models/fixture.py': 'VALUE = 1',
            'static/src/fixture.js': 'export const value = 1;',
            'i18n/de.po': (
                'msgid ""\nmsgstr ""\n'
                '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                f'#. module: {self.module_name}\n'
                '#: model:res.partner.category,name:'
                f'{self.module_name}.fixture_term\n'
                'msgid "Source"\nmsgstr "Quelle"\n\n'
                f'#. module: {self.module_name}\n'
                f'#: code:addons/{self.module_name}/models/fixture.py:0\n'
                'msgid "Code term"\nmsgstr "Codebegriff"\n'
            ),
        }
        for name, content in files.items():
            self._write_file(name, content)

    def _write_file(self, name: str, content: str) -> None:
        """Write one file of the fixture addon."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def _replace_in_translations(self, old: str, new: str) -> None:
        """Change a term in the German translation file of the fixture addon."""
        path = self.root / 'i18n/de.po'
        path.write_text(path.read_text(encoding='utf-8').replace(old, new), 'utf-8')

    def _check(self, published: dict | None = None) -> Mock:
        """Run the check with the store answering with the given modules."""
        response = Mock()
        response.json.return_value = {'result': published or {}}
        with patch(STORE_POST, return_value=response) as post:
            call_kw(self.env['ir.module.module'], 'action_check_updates', [[]], {})
        return post

    def _published(self, version: str, changelog: str = '') -> dict:
        """Return a store answer listing the fixture addon."""
        info = {'version_remote': version, 'changelog': changelog}
        return {self.module_name: info}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_flags_only_what_needs_action(self):
        changes = [
            (
                'data',
                lambda: self._write_file('data/records.xml', '<odoo></odoo>'),
                True,
                False,
            ),
            (
                'removed data file',
                (self.root / 'data/records.xml').unlink,
                True,
                False,
            ),
            (
                'migration',
                lambda: self._write_file('migrations/17.0.1.1.0/post-x.py', 'x = 1'),
                True,
                False,
            ),
            (
                'python method',
                lambda: self._write_file('models/fixture.py', 'VALUE = 2'),
                False,
                False,
            ),
            (
                'javascript',
                lambda: self._write_file(
                    'static/src/fixture.js', 'export const value = 2;'
                ),
                False,
                False,
            ),
            (
                'database term',
                lambda: self._replace_in_translations('Quelle', 'Ursprung'),
                False,
                True,
            ),
            (
                'code term',
                lambda: self._replace_in_translations('Codebegriff', 'Begriff'),
                False,
                False,
            ),
        ]
        for label, change, upgrade, translation in changes:
            with self.subTest(label):
                self._write_addon()
                self.module._save_upgrade_baseline()
                self.module._save_translation_baseline()
                change()
                self._check()
                self.assertEqual(bool(self.module.upgrade_status), upgrade)
                self.assertEqual(bool(self.module.translation_status), translation)

    def test_flags_what_the_module_declares(self):
        model = self.env.registry['ir.module.module']
        field = next(
            field
            for field in IrModuleModule._field_definitions
            if field.name == 'store_version'
        )
        changes = [
            ('field', patch.object(field, '_args__', {'required': True})),
            (
                'table object',
                patch.object(
                    IrModuleModule,
                    '_sql_constraints',
                    [('fixture', 'CHECK(id > 0)', 'Fixture')],
                    create=True,
                ),
            ),
        ]
        with patch.object(IrModuleModule, '_module', self.module_name):
            self.module._save_upgrade_baseline()
            for label, change in changes:
                with self.subTest(label), change:
                    self._check()
                    self.assertEqual(self.module.upgrade_status, 'needed')
            self.module._save_upgrade_baseline()
            with patch.object(model._fields['store_version'], 'required', True):
                self._check()
            self.assertFalse(self.module.upgrade_status)
            first_run = {
                'selection': [('a', 'A'), ('b', 'B')],
                'ondelete': {'a': lambda records: records},
            }
            second_run = {
                'selection': [('b', 'B'), ('a', 'A')],
                'ondelete': {'a': lambda records: records},
            }
            with patch.object(field, '_args__', first_run):
                self.module._save_upgrade_baseline()
            with patch.object(field, '_args__', second_run):
                self._check()
            self.assertFalse(self.module.upgrade_status)

    def test_upgrade_clears_flag_but_keeps_translation_flag(self):
        self._write_file('data/records.xml', '<odoo></odoo>')
        self._replace_in_translations('Quelle', 'Ursprung')
        self._check()
        self.assertEqual(self.module.upgrade_status, 'needed')
        self.assertEqual(self.module.translation_status, 'changed')
        with patch.object(self.registry, 'updated_modules', [self.module_name]):
            self.env['ir.module.module']._register_hook()
        self.assertFalse(self.module.upgrade_status)
        self.assertEqual(self.module.translation_status, 'changed')
        self._check()
        self.assertFalse(self.module.upgrade_status)
        self.assertEqual(self.module.translation_status, 'changed')

    def test_first_load_saves_baselines_without_flags(self):
        self.module.write(
            {'upgrade_fingerprint': False, 'translation_fingerprint': False}
        )
        self._write_file('data/records.xml', '<odoo></odoo>')
        self.env['ir.module.module']._register_hook()
        self._check()
        self.assertTrue(self.module.upgrade_fingerprint)
        self.assertTrue(self.module.translation_fingerprint)
        self.assertFalse(self.module.upgrade_status)
        self.assertFalse(self.module.translation_status)

    def test_dismiss_clears_upgrade_until_the_next_change(self):
        self._write_file('data/records.xml', '<odoo></odoo>')
        self._check()
        self.module.action_dismiss_upgrade()
        self._check()
        self.assertFalse(self.module.upgrade_status)
        self._write_file('data/records.xml', '<odoo> </odoo>')
        self._check()
        self.assertEqual(self.module.upgrade_status, 'needed')

    def test_reload_applies_translations_as_requested(self):
        category = self.env['res.partner.category'].create({'name': 'Source'})
        self.env['ir.model.data'].create(
            {
                'module': self.module_name,
                'name': 'fixture_term',
                'model': category._name,
                'res_id': category.id,
            }
        )
        german = category.with_context(lang='de_DE')
        german.name = 'Customized'
        for overwrite, expected in [(False, 'Customized'), (True, 'Quelle')]:
            with self.subTest(overwrite=overwrite):
                self.module.translation_fingerprint = '{"de_DE": "stale"}'
                self._check()
                self.assertEqual(self.module.translation_status, 'changed')
                self.module.with_context(
                    overwrite=overwrite
                ).action_reload_translations()
                category.invalidate_recordset()
                self.assertEqual(german.name, expected)
                self.assertFalse(self.module.translation_status)

    def test_update_state_shows_one_badge_per_status(self):
        self.env['res.lang']._activate_lang('en_US')
        self.assertFalse(self.module.update_state)
        self.module.write({'store_status': 'update', 'translation_status': 'changed'})
        state = self.module.with_context(lang='en_US').update_state
        self.assertEqual(state.count('class="badge'), 2)
        self.assertIn('text-bg-info">Store Update<', state)
        self.assertIn('text-bg-300">Translations Changed<', state)
        self.assertNotIn('Upgrade Needed', state)

    def test_store_status(self):
        cases = [
            ('newer', self._published('17.0.1.0.1'), '17.0.1.0.1', 'update'),
            ('same', self._published('17.0.1.0.0'), '17.0.1.0.0', False),
            ('older', self._published('17.0.0.9.0'), '17.0.0.9.0', False),
            ('not on the store', {}, False, False),
        ]
        for label, published, version, status in cases:
            with self.subTest(label):
                self._check(published)
                self.assertEqual(self.module.store_version, version)
                self.assertEqual(self.module.store_status, status)

    def test_store_failure_keeps_the_last_answer(self):
        self._check(self._published('17.0.2.0.0'))
        checked_at = self.module.store_checked_at
        bad_json = Mock()
        bad_json.json.side_effect = ValueError('no json')
        rejected = Mock()
        rejected.json.return_value = {'error': {'code': 200}}
        empty = Mock()
        empty.json.return_value = {'result': None}
        odd = Mock()
        odd.json.return_value = {'result': {self.module_name: 'odd'}}
        cases = [
            ('timeout', {'side_effect': requests.Timeout('slow')}),
            ('bad json', {'return_value': bad_json}),
            ('rejected', {'return_value': rejected}),
            ('empty', {'return_value': empty}),
            ('odd entry', {'return_value': odd}),
        ]
        for label, behaviour in cases:
            with self.subTest(label), patch(STORE_POST, **behaviour):
                self.env['ir.module.module'].action_check_updates()
                self.assertEqual(self.module.store_version, '17.0.2.0.0')
                self.assertEqual(self.module.store_status, 'update')
                self.assertEqual(self.module.store_checked_at, checked_at)
        unknown = Mock()
        unknown.json.return_value = {'result': {self.module_name: None}}
        with patch(STORE_POST, return_value=unknown):
            self.env['ir.module.module'].action_check_updates()
        self.assertFalse(self.module.store_version)

    def test_store_request_sends_only_covered_names(self):
        post = self._check()
        modules = post.call_args.kwargs['json']['params']['modules']
        self.assertEqual(modules[self.module_name], {})
        self.assertNotIn('base', modules)

    def test_changelog_cannot_carry_scripts(self):
        changelog = '<p>Added</p><script>alert(1)</script>'
        self._check(self._published('17.0.2.0.0', changelog))
        self.assertIn('Added', self.module.store_changelog)
        self.assertNotIn('script', self.module.store_changelog)

    def test_broken_translation_file_breaks_nothing(self):
        contents = [
            '<<<<<<< HEAD',
            '#: code:addons/foo/x.py\nmsgid "Foo"\nmsgstr "Bar"\n',
        ]
        for content in contents:
            with self.subTest(content):
                self._write_file('i18n/de.po', content)
                self._check()
                self.assertEqual(self.module.translation_status, 'changed')
                self.module.translation_fingerprint = False
                self.env['ir.module.module']._register_hook()
                self.assertTrue(self.module.translation_fingerprint)

    def test_a_new_language_changes_nothing(self):
        self.env['res.lang']._activate_lang('fr_FR')
        self._check()
        self.assertFalse(self.module.translation_status)

    def test_module_not_on_disk_is_missing(self):
        module = self.env['ir.module.module'].create(
            {
                'name': f'{self.module_name}_gone',
                'shortdesc': 'Gone',
                'author': 'Acme',
                'state': 'installed',
            }
        )
        self.env['ir.module.module']._register_hook()
        self._check()
        self.assertEqual(module.disk_status, 'missing')
        self.assertFalse(module.upgrade_status)
        self.assertFalse(module.translation_status)
        self.assertFalse(module.upgrade_fingerprint)

    def test_check_clears_a_module_it_no_longer_covers(self):
        self.module.write(
            {
                'store_version': '17.0.2.0.0',
                'store_status': 'update',
                'upgrade_status': 'needed',
                'translation_status': 'changed',
                'disk_status': 'missing',
                'author': 'Odoo SA',
            }
        )
        self._check()
        self.assertFalse(self.module.store_version)
        self.assertFalse(self.module.update_state)

    def test_covered_modules(self):
        action = self.env.ref('muk_check.action_update_check')
        covered = self.env['ir.module.module'].search(safe_eval(action.domain))
        self.assertEqual(
            covered,
            self.env['ir.module.module'].search(
                self.env['ir.module.module'].UPDATE_CHECK_DOMAIN
            ),
        )
        self.assertIn(self.module, covered)
        self.assertFalse(covered.filtered(lambda module: module.name == 'base'))
        cases = [
            ('Odoo S.A.', False),
            ('Odoo SA', False),
            ('Odoo Sa', False),
            ('Odoo PS', False),
            ('Odoo', False),
            ('odoo', False),
            ('Vauxoo, Odoo S.A.', False),
            ('Odoo Community Association (OCA)', True),
            ('MuK IT', True),
        ]
        author = self.module.author
        for name, is_covered in cases:
            with self.subTest(name):
                self.module.author = name
                found = self.env['ir.module.module'].search(safe_eval(action.domain))
                self.assertEqual(self.module in found, is_covered)
        self.module.author = author
        self.module.imported = True
        self.assertNotIn(
            self.module, self.env['ir.module.module'].search(safe_eval(action.domain))
        )

    def test_only_administrators_can_act(self):
        user = new_test_user(self.env, 'update_user', 'base.group_user')
        actions = [
            lambda: self.env['ir.module.module'].with_user(user).action_check_updates(),
            self.module.with_user(user).action_dismiss_upgrade,
            self.module.with_user(user).action_reload_translations,
        ]
        with patch(STORE_POST) as post:
            for action in actions:
                with self.subTest(action=action), self.assertRaises(AccessDenied):
                    action()
        self.assertFalse(post.called)
