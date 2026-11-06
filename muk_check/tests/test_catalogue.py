from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from odoo import fields, models, release
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import config

from odoo.addons.muk_check.tools.odoo_release import (
    fetch_image_builds,
    installed_build,
)

IMAGE_REQUEST = 'odoo.addons.muk_check.tools.odoo_release.requests.get'
PACKAGE_STATUS = 'odoo.addons.muk_check.tools.odoo_release.PACKAGE_STATUS'
INSTALLED_BUILD = 'odoo.addons.muk_check.models.check_rule.installed_build'
RUN_INSTALLED_BUILD = 'odoo.addons.muk_check.models.check_run.installed_build'
DISK_USAGE = 'odoo.addons.muk_check.models.check_rule.shutil.disk_usage'


@tagged('post_install', '-at_install')
class TestRuleCatalogue(TransactionCase):
    """Make each shipped rule fail and pass on a real database."""

    @classmethod
    def setUpClass(cls) -> None:
        """Start without findings."""
        super().setUpClass()
        cls.env['muk_check.finding'].search([]).unlink()

    def _rule(self, key: str) -> models.BaseModel:
        """Return the shipped rule with the given dotted name."""
        return self.env.ref(f'muk_check.rule_{key.replace(".", "_")}')

    def _assert_state(self, key: str, state: str) -> None:
        """Run a rule and check its result, skipping it without its modules."""
        rule = self._rule(key)
        if not rule._is_applicable():
            self.skipTest(f'{key} needs {rule.module_ids.mapped("name")}')
        rule.action_run_rule()
        self.assertEqual(rule.state, state, rule.error)

    def _image_builds(self, builds: dict) -> None:
        """Set the last answer from Docker Hub."""
        self.env['ir.config_parameter'].sudo().set_param(
            'muk_check.image_builds', json.dumps(builds)
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_every_shipped_rule_evaluates(self):
        for rule in self.env['muk_check.rule'].search([]):
            with self.subTest(rule.name):
                rule.action_run_rule()
                self.assertNotEqual(rule.state, 'error', rule.error)

    def test_server_options(self):
        cases = [
            ('server.list_db', 'list_db', True, False),
            ('server.dev_mode', 'dev_mode', ['reload'], []),
            ('server.workers', 'workers', 0, 4),
            ('server.log_level', 'log_level', 'debug_sql', 'info'),
        ]
        for key, option, failing, passing in cases:
            with self.subTest(key):
                with patch.dict(config.options, {option: failing}):
                    self._assert_state(key, 'failed')
                with patch.dict(config.options, {option: passing}):
                    self._assert_state(key, 'passed')

    def test_server_option_combinations(self):
        limits = {
            'workers': 4,
            'limit_memory_hard': 2684354560,
            'limit_time_cpu': 60,
            'limit_time_real': 120,
        }
        cases = [
            ('server.dbfilter', {'dbfilter': '', 'db_name': False}, 'failed'),
            ('server.dbfilter', {'dbfilter': '^test$', 'db_name': False}, 'passed'),
            ('server.dbfilter', {'dbfilter': '', 'db_name': ['test']}, 'passed'),
            ('server.request_limits', limits, 'passed'),
            ('server.request_limits', {**limits, 'limit_memory_hard': 0}, 'failed'),
            ('server.request_limits', {**limits, 'limit_time_cpu': 7200}, 'failed'),
            ('server.request_limits', {**limits, 'limit_time_real': 7200}, 'failed'),
            (
                'server.request_limits',
                {**limits, 'workers': 0, 'limit_memory_hard': 0},
                'passed',
            ),
        ]
        for key, options, state in cases:
            with self.subTest(key, options=options):
                with patch.dict(config.options, options):
                    self._assert_state(key, state)

    def test_database_superuser(self):
        self.env.cr.execute(
            'SELECT rolsuper FROM pg_roles WHERE rolname = current_user'
        )
        superuser = self.env.cr.fetchone()[0]
        self._assert_state(
            'server.database_superuser', 'failed' if superuser else 'passed'
        )

    def test_disk_space(self):
        for free, state in ((9, 'failed'), (10, 'passed')):
            with self.subTest(free), patch(DISK_USAGE) as disk_usage:
                disk_usage.return_value = Mock(total=100, free=free)
                self._assert_state('server.disk_space', state)

    def test_master_password(self):
        for default, state in ((True, 'failed'), (False, 'passed')):
            with (
                self.subTest(default),
                patch.object(
                    type(config), 'verify_admin_password', return_value=default
                ),
            ):
                self._assert_state('server.master_password', state)

    def test_server_rules_do_not_apply_on_odoo_sh(self):
        self._image_builds({release.serie: '20261102'})
        with (
            patch.dict(os.environ, {'ODOO_STAGE': 'production'}),
            patch(INSTALLED_BUILD, return_value='20260908'),
        ):
            for key in (
                'server.master_password',
                'server.list_db',
                'server.workers',
                'server.proxy_mode',
                'server.request_limits',
                'server.disk_space',
                'odoo.build_behind',
            ):
                with self.subTest(key):
                    self._assert_state(key, 'not_applicable')

    def test_overview_compares_the_current_and_the_newest_version(self):
        self._image_builds({release.serie: '20261102', '99.0': '20261201'})
        cases = [
            ('newest', {}, '20261102', 'Up to date', False),
            ('one day', {}, '20261101', 'One day behind', False),
            ('late', {}, '20260908', '55 days behind', True),
            ('from source', {}, None, False, False),
        ]
        for label, environ, build, note, late in cases:
            with (
                self.subTest(label),
                patch.dict(os.environ, environ),
                patch(RUN_INSTALLED_BUILD, return_value=build),
            ):
                run = self.env['muk_check.run'].create({})
                self.assertEqual(run.odoo_newest, release.serie)
                self.assertEqual(run.odoo_image, date(2026, 11, 2))
                self.assertEqual(run.odoo_build_note, note)
                self.assertEqual(run.odoo_build_late, late)
        with patch.dict(os.environ, {'ODOO_STAGE': 'production'}):
            run = self.env['muk_check.run'].create({})
            self.assertFalse(run.odoo_newest)
            self.assertFalse(run.odoo_image)

    def test_proxy_mode(self):
        parameters = self.env['ir.config_parameter'].sudo()
        cases = [
            ('https://example.com', False, 'failed'),
            ('https://example.com', True, 'passed'),
            ('http://example.com', False, 'passed'),
        ]
        for url, proxy_mode, state in cases:
            with (
                self.subTest(url=url, proxy_mode=proxy_mode),
                patch.dict(config.options, {'proxy_mode': proxy_mode}),
            ):
                parameters.set_param('web.base.url', url)
                self._assert_state('server.proxy_mode', state)

    def test_parameters(self):
        cases = [
            ('signin.cooldown', 'base.login_cooldown_after', 0, 5),
            ('signin.password_length', 'auth_password_policy.minlength', 6, 8),
            ('signin.open_signup', 'auth_signup.invitation_scope', 'b2c', 'b2b'),
            ('signin.session_timeout', 'sessions.max_inactivity_seconds', 999999, 3600),
            ('signin.totp_policy', 'auth_totp.policy', '', 'all_required'),
            ('accounts.portal_api_keys', 'portal.allow_api_keys', True, ''),
        ]
        parameters = self.env['ir.config_parameter'].sudo()
        for key, parameter, failing, passing in cases:
            with self.subTest(key):
                parameters.set_param(parameter, str(failing))
                self._assert_state(key, 'failed')
                parameters.set_param(parameter, str(passing))
                self._assert_state(key, 'passed')

    def test_base_url(self):
        parameters = self.env['ir.config_parameter'].sudo()
        cases = [
            ('http://example.com', True, 'failed'),
            ('https://example.com', False, 'failed'),
            ('https://example.com', True, 'passed'),
        ]
        for url, frozen, state in cases:
            with self.subTest(url=url, frozen=frozen):
                parameters.set_param('web.base.url', url)
                parameters.set_param('web.base.url.freeze', frozen)
                self._assert_state('mail.base_url', state)

    def test_website_info_page(self):
        view = self.env.ref('website.show_website_info', raise_if_not_found=False)
        if not view:
            self.skipTest('needs website')
        for active, state in ((True, 'failed'), (False, 'passed')):
            with self.subTest(active):
                view.active = active
                self._assert_state('website.info_page', state)

    def test_number_of_administrators(self):
        group = self.env.ref('base.group_system')
        group.users -= group.users.filtered(
            lambda user: user != self.env.ref('base.user_admin')
        )
        self._assert_state('accounts.many_admins', 'passed')
        for number in range(6):
            new_test_user(self.env, f'many_admin_{number}', 'base.group_system')
        self._assert_state('accounts.many_admins', 'failed')

    def test_inactive_administrators(self):
        user = new_test_user(self.env, 'old_admin', 'base.group_system')
        self.env['res.users.log'].with_user(user).create({})
        self._assert_state('accounts.inactive_admins', 'passed')
        self.env.cr.execute(
            "UPDATE res_users_log SET create_date = NOW() - INTERVAL '91 days' "
            'WHERE create_uid = %s',
            [user.id],
        )
        self.env.invalidate_all()
        self._assert_state('accounts.inactive_admins', 'failed')
        self.assertIn(
            user.display_name,
            self._rule('accounts.inactive_admins').finding_ids.mapped('target'),
        )

    def test_admin_without_two_factor(self):
        self._assert_state('signin.admin_totp', 'failed')

    def test_records_rules(self):
        modules = self.env['ir.module.module']
        base = self.env.ref('base.module_base')
        admin = self.env.ref('base.user_admin')
        cleanup = self.env.ref('base.autovacuum_job')
        cases = [
            (
                'accounts.admin_login',
                lambda: admin.write({'login': 'admin'}),
                lambda: admin.write({'login': 'someone@example.com'}),
            ),
            (
                'modules.autovacuum',
                lambda: cleanup.write({'active': False}),
                lambda: cleanup.write({'active': True}),
            ),
            (
                'server.cron_stalled',
                lambda: cleanup.write(
                    {
                        'nextcall': fields.Datetime.subtract(
                            fields.Datetime.now(), days=4
                        )
                    }
                ),
                lambda: cleanup.write({'nextcall': fields.Datetime.now()}),
            ),
            (
                'accounts.public_access',
                lambda: self.env['ir.model.access'].create(
                    {
                        'name': 'Public Write',
                        'model_id': self.env.ref('base.model_res_partner').id,
                        'group_id': self.env.ref('base.group_public').id,
                        'perm_read': True,
                        'perm_write': True,
                    }
                ),
                lambda: (
                    self.env['ir.model.access']
                    .search([('name', '=', 'Public Write')])
                    .unlink()
                ),
            ),
            (
                'modules.demo_data',
                lambda: base.write({'demo': True}),
                lambda: base.write({'demo': False}),
            ),
            (
                'modules.unfinished',
                lambda: base.write({'state': 'to upgrade'}),
                lambda: base.write({'state': 'installed'}),
            ),
            (
                'mail.smtp_encryption',
                lambda: self.env['ir.mail_server'].create(
                    {
                        'name': 'Plain',
                        'smtp_host': 'mail.example.com',
                        'smtp_encryption': 'none',
                    }
                ),
                lambda: (
                    self.env['ir.mail_server']
                    .search([])
                    .write({'smtp_host': 'localhost'})
                ),
            ),
            (
                'modules.server_actions',
                lambda: (
                    self.env['ir.actions.server']
                    .with_user(admin)
                    .create(
                        {
                            'name': 'Added Here',
                            'model_id': self.env.ref('base.model_res_partner').id,
                            'state': 'code',
                            'code': 'pass',
                        }
                    )
                ),
                lambda: (
                    self.env['ir.actions.server']
                    .search([('state', '=', 'code'), ('create_uid', '!=', 1)])
                    .unlink()
                ),
            ),
            (
                'apps.upgrade_needed',
                lambda: base.write({'upgrade_status': 'needed'}),
                lambda: modules.search([]).write({'upgrade_status': False}),
            ),
            (
                'apps.missing',
                lambda: base.write({'disk_status': 'missing'}),
                lambda: modules.search([]).write({'disk_status': False}),
            ),
            (
                'apps.translations',
                lambda: base.write({'translation_status': 'changed'}),
                lambda: modules.search([]).write({'translation_status': False}),
            ),
        ]
        for key, failing, passing in cases:
            with self.subTest(key):
                failing()
                self._assert_state(key, 'failed')
                passing()
                self._assert_state(key, 'passed')

    def test_store_update_detail_and_online_setting(self):
        base = self.env.ref('base.module_base')
        self.env['ir.module.module'].search([]).write({'store_status': False})
        self._assert_state('apps.store_update', 'passed')
        base.write({'store_status': 'update', 'store_version': '20.0.9.0.0'})
        self._assert_state('apps.store_update', 'failed')
        self.assertEqual(
            self._rule('apps.store_update').finding_ids.detail, '20.0.9.0.0'
        )
        self.env['ir.config_parameter'].sudo().set_param('muk_check.online', 'False')
        self._assert_state('apps.store_update', 'not_applicable')

    def test_odoo_series(self):
        major = int(release.serie.split('.')[0])
        cases = [
            ('current', [major - 2, major - 1, major], 'passed', 'passed'),
            ('older but supported', [major - 1, major, major + 1], 'passed', 'failed'),
            ('unsupported', [major + 1, major + 2, major + 3], 'failed', 'failed'),
            ('unknown', [], 'not_applicable', 'not_applicable'),
        ]
        for label, majors, series_state, newer_state in cases:
            with self.subTest(label):
                self._image_builds({f'{number}.0': '20991231' for number in majors})
                self._assert_state('odoo.series_unsupported', series_state)
                self._assert_state('odoo.newer_series', newer_state)

    def test_odoo_build(self):
        self._image_builds({release.serie: '20261102'})
        cases = [
            ('current', '20261102', 'passed'),
            ('slightly behind', '20261015', 'passed'),
            ('far behind', '20260908', 'failed'),
            ('no package', None, 'not_applicable'),
        ]
        for label, installed, state in cases:
            with self.subTest(label), patch(INSTALLED_BUILD, return_value=installed):
                self._assert_state('odoo.build_behind', state)
        with patch(INSTALLED_BUILD, return_value='20260908'):
            self._assert_state('odoo.build_behind', 'failed')
        self.assertEqual(self._rule('odoo.build_behind').finding_ids.detail, '20260908')
        self._image_builds({})
        with patch(INSTALLED_BUILD, return_value='20260908'):
            self._assert_state('odoo.build_behind', 'not_applicable')

    def test_image_builds_keep_the_newest_date_per_series(self):
        tags = [
            'latest',
            '20.0',
            '20',
            '20.0-20261015',
            '20.0-20261102',
            '19.0-20260926',
        ]
        response = Mock()
        response.json.return_value = {'results': [{'name': name} for name in tags]}
        with patch(IMAGE_REQUEST, return_value=response):
            builds = fetch_image_builds()
        self.assertEqual(builds, {'20.0': '20261102', '19.0': '20260926'})

    def test_failed_image_request_keeps_the_last_answer(self):
        self._image_builds({'20.0': '20261102'})
        bad_reply = Mock()
        bad_reply.json.return_value = {'results': None}
        cases = [
            ('timeout', {'side_effect': requests.Timeout('slow')}),
            ('bad reply', {'return_value': bad_reply}),
        ]
        for label, behaviour in cases:
            with self.subTest(label), patch(IMAGE_REQUEST, **behaviour):
                self.env['muk_check.rule']._update_image_builds()
                self.assertEqual(
                    self.env['muk_check.rule']._image_builds(), {'20.0': '20261102'}
                )

    def test_flags_of_an_uninstalled_app_do_not_count(self):
        module = self.env['ir.module.module'].create(
            {
                'name': 'muk_gone_app',
                'state': 'uninstalled',
                'disk_status': 'missing',
                'upgrade_status': 'needed',
                'translation_status': 'changed',
                'store_status': 'update',
            }
        )
        for key in (
            'apps.missing',
            'apps.upgrade_needed',
            'apps.translations',
            'apps.store_update',
        ):
            with self.subTest(key):
                self._assert_state(key, 'passed')
        module.state = 'installed'
        self._assert_state('apps.missing', 'failed')

    def test_installed_build_reads_the_odoo_package(self):
        other = 'Package: odoo-other\nVersion: 1.0.20200101\n\n'
        odoo = 'Package: odoo\nStatus: install ok installed\nVersion: 19.0.20261102\n\n'
        cases = [
            ('installed', other + odoo, '20261102'),
            ('other package only', other, None),
            ('no date', 'Package: odoo\nVersion: 19.0\n\n', None),
        ]
        with TemporaryDirectory() as folder:
            status = Path(folder) / 'status'
            with patch(PACKAGE_STATUS, status):
                self.assertIsNone(installed_build())
                for label, content, build in cases:
                    with self.subTest(label):
                        status.write_text(content, encoding='utf-8')
                        self.assertEqual(installed_build(), build)
