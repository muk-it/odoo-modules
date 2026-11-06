from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import Mock, patch

from odoo import fields, models
from odoo.exceptions import AccessDenied, AccessError
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools import convert_file

FLAG = 'muk_check.test_flag'
STORE_POST = 'odoo.addons.muk_check.models.ir_module_module.requests.post'
IMAGE_BUILDS = 'odoo.addons.muk_check.models.check_rule.fetch_image_builds'


@tagged('post_install', '-at_install')
class TestRuleEngine(TransactionCase):
    """Cover running rules, findings, the score and the findings mail."""

    @classmethod
    def setUpClass(cls) -> None:
        """Start without findings and with an administrator."""
        super().setUpClass()
        cls.env['muk_check.finding'].search([]).unlink()
        cls.admin = new_test_user(
            cls.env, 'check_admin', 'base.group_system', email='admin@example.com'
        )
        cls.user = new_test_user(cls.env, 'check_user', 'base.group_user')

    def _rule(self, **values) -> models.BaseModel:
        """Create a custom Expression rule unless the values say otherwise."""
        return self.env['muk_check.rule'].create(
            {
                'name': 'Test Rule',
                'kind': 'expression',
                'expression': 'False',
                **values,
            }
        )

    def _flag_rule(self, **values) -> models.BaseModel:
        """Create a rule that fails while the test flag parameter is set."""
        expression = f"env['ir.config_parameter'].sudo().get_param('{FLAG}')"
        return self._rule(expression=expression, **values)

    def _set_flag(self, value: bool) -> None:
        """Make the flag rules fail or pass."""
        self.env['ir.config_parameter'].sudo().set_param(FLAG, value)

    def _store_reply(self) -> Mock:
        """Return a store reply that lists no module."""
        response = Mock()
        response.json.return_value = {'result': {}}
        return response

    def _run_all(self) -> models.BaseModel:
        """Run everything with the online sources answering, return the last run."""
        with (
            patch(STORE_POST, return_value=self._store_reply()),
            patch(IMAGE_BUILDS, return_value={'20.0': '20991231'}),
        ):
            self.env['muk_check.run'].action_run()
        return self.env['muk_check.run'].search([], limit=1)

    def _finding_messages(self) -> models.BaseModel:
        """Return the findings posted in the administrators channel so far."""
        return self.env['mail.message'].search(
            [
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', self.env.ref('mail.channel_admin').id),
                ('body', 'ilike', 'Security Check:'),
            ]
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_answers(self):
        cases = [
            ('true', 'True', 'failed', 1),
            ('false', 'False', 'passed', 0),
            ('empty text', "''", 'passed', 0),
            ('nothing to say', 'None', 'not_applicable', 0),
            ('text', "'one thing'", 'failed', 1),
            ('texts', "['one', 'two']", 'failed', 2),
            ('records', 'env.user', 'failed', 1),
            ('no records', "env['res.users'].browse()", 'passed', 0),
            ('numbers', '[1, 2]', 'failed', 2),
            ('repeated texts', "['one', 'one']", 'failed', 1),
        ]
        for label, expression, state, count in cases:
            with self.subTest(label):
                rule = self._rule(expression=expression)
                rule.action_run_rule()
                self.assertEqual(rule.state, state)
                self.assertEqual(len(rule.finding_ids), count)
                rule.action_run_rule()
                self.assertEqual(len(rule.finding_ids), count)

    def test_records_rule_links_each_record(self):
        partner = self.env['res.partner'].create({'name': 'Checked Partner'})
        rule = self._rule(
            kind='records',
            model_id=self.env['ir.model']._get_id('res.partner'),
            domain=f"[('id', '=', {partner.id})]",
            detail_field_id=self.env['ir.model.fields']._get('res.partner', 'id').id,
        )
        rule.action_run_rule()
        finding = rule.finding_ids
        self.assertEqual(finding.target, 'Checked Partner')
        self.assertEqual(finding.detail, str(partner.id))
        partner.name = 'Renamed Partner'
        rule.action_run_rule()
        self.assertEqual(rule.finding_ids, finding)
        self.assertEqual(finding.target, 'Renamed Partner')
        action = rule.finding_ids.action_open_record()
        self.assertEqual(
            (action['res_model'], action['res_id']), ('res.partner', partner.id)
        )
        rule.action_id = self.env.ref('base.action_res_users')
        self.assertEqual(finding.action_open_fix()['res_model'], 'res.users')

    def test_detail_shows_a_readable_value(self):
        company = self.env['res.partner'].create({'name': 'Parent'})
        partner = self.env['res.partner'].create(
            {'name': 'Child', 'parent_id': company.id}
        )
        cases = [
            ('relation', 'parent_id', company.display_name),
            ('empty', 'comment', False),
        ]
        for label, field, detail in cases:
            with self.subTest(label):
                rule = self._rule(
                    kind='records',
                    model_id=self.env['ir.model']._get_id('res.partner'),
                    domain=f"[('id', '=', {partner.id})]",
                    detail_field_id=self.env['ir.model.fields']
                    ._get('res.partner', field)
                    .id,
                )
                rule.action_run_rule()
                self.assertEqual(rule.finding_ids.detail, detail)

    def test_missing_module_or_model_does_not_apply(self):
        missing = self.env['ir.module.module'].create(
            {'name': 'no_such_module', 'state': 'uninstalled'}
        )
        installed = self.env['ir.module.module'].search(
            [('name', 'in', ['base', 'mail'])]
        )
        cases = [
            {'module_ids': missing.ids},
            {'module_ids': (installed | missing).ids},
            {'kind': 'records'},
        ]
        for values in cases:
            with self.subTest(values):
                rule = self._rule(expression='True', **values)
                rule.action_run_rule()
                self.assertEqual(rule.state, 'not_applicable')
                self.assertFalse(rule.error)
        rule = self._rule(expression='True', module_ids=installed.ids)
        rule.action_run_rule()
        self.assertEqual(rule.state, 'failed')

    def test_a_broken_rule_stays_contained(self):
        cases = [
            ('exception', {'expression': '1 / 0'}),
            ('forbidden name', {'expression': 'env.__class__'}),
            (
                'bad domain',
                {
                    'kind': 'records',
                    'model_id': self.env['ir.model']._get_id('res.users'),
                    'domain': '[(',
                },
            ),
            ('database password', {'expression': "config('db_password')"}),
        ]
        for label, values in cases:
            with self.subTest(label):
                rule = self._rule(**values)
                rule.action_run_rule()
                self.assertEqual(rule.state, 'error')
                self.assertTrue(rule.error)
        healthy = self._rule(expression='True')
        self._run_all()
        self.assertEqual(healthy.state, 'failed')

    def test_a_failing_run_keeps_the_findings(self):
        rule = self._rule(expression='True')
        rule.action_run_rule()
        finding = rule.finding_ids
        rule.expression = '1 / 0'
        rule.action_run_rule()
        self.assertEqual(finding.state, 'open')

    def test_a_rule_cannot_change_data(self):
        partner = self.env['res.partner'].create({'name': 'Untouched'})
        rule = self._rule(
            expression=f"env['res.partner'].browse({partner.id}).write({{'name': 'Changed'}})"
        )
        rule.action_run_rule()
        self.assertEqual(rule.state, 'failed')
        self.env.cr.execute('SELECT name FROM res_partner WHERE id = %s', [partner.id])
        self.assertEqual(self.env.cr.fetchone()[0], 'Untouched')

    def test_finding_opens_resolves_and_reopens(self):
        rule = self._flag_rule()
        self._set_flag(True)
        rule.action_run_rule()
        finding = rule.finding_ids
        self.assertEqual(finding.state, 'open')
        rule.action_run_rule()
        self.assertEqual(rule.finding_ids, finding)
        self._set_flag(False)
        rule.action_run_rule()
        self.assertEqual(finding.state, 'resolved')
        finding.notified = True
        self._set_flag(True)
        rule.action_run_rule()
        self.assertEqual(rule.finding_ids, finding)
        self.assertEqual(finding.state, 'open')
        self.assertFalse(finding.notified)

    def test_a_new_detail_is_a_new_finding(self):
        rule = self._rule(expression="'20.0.1.0.0'")
        rule.action_run_rule()
        first = rule.finding_ids
        rule.expression = "'20.0.2.0.0'"
        rule.action_run_rule()
        self.assertEqual(first.state, 'resolved')
        self.assertEqual(
            rule.finding_ids.filtered(lambda f: f.state == 'open').detail, '20.0.2.0.0'
        )

    def test_accepted_finding_lasts_until_its_end_date(self):
        rule = self._rule(expression='True', severity='critical')
        rule.action_run_rule()
        finding = rule.finding_ids
        tomorrow = date.today() + timedelta(days=1)
        finding.with_user(self.admin).write(
            {'accepted_reason': 'Test server', 'accepted_until': tomorrow}
        )
        finding.with_user(self.admin).action_accept()
        self.assertEqual(finding.accepted_by_id, self.admin)
        rule.action_run_rule()
        self.assertEqual(finding.state, 'accepted')
        self.assertEqual(self.env['muk_check.run']._record_run().critical_count, 0)
        rule.expression = 'False'
        rule.action_run_rule()
        self.assertEqual(finding.state, 'accepted')
        rule.expression = 'True'
        rule.action_run_rule()
        self.assertEqual(finding.state, 'accepted')
        self.assertEqual(finding.accepted_reason, 'Test server')
        finding.accepted_until = date.today() - timedelta(days=1)
        rule.action_run_rule()
        self.assertEqual(finding.state, 'open')
        self.assertFalse(finding.accepted_reason)
        self.assertEqual(self.env['muk_check.run']._record_run().critical_count, 1)
        finding.accepted_reason = 'Test server'
        finding.action_accept()
        finding.action_reopen()
        self.assertEqual(finding.state, 'open')
        self.assertFalse(finding.accepted_reason)

    def test_score_and_grade(self):
        cases = [
            ('nothing', [], 100, 'A'),
            ('one low', ['low'], 99, 'A'),
            ('one medium', ['medium'], 96, 'A'),
            ('one high', ['high'], 90, 'A'),
            ('one critical', ['critical'], 80, 'B'),
            ('two critical', ['critical'] * 2, 60, 'C'),
            ('three critical', ['critical'] * 3, 40, 'D'),
            ('four critical', ['critical'] * 4, 20, 'F'),
            ('never below zero', ['critical'] * 6, 0, 'F'),
        ]
        for label, severities, score, grade in cases:
            with self.subTest(label):
                self.env['muk_check.finding'].search([]).unlink()
                for severity in severities:
                    self._rule(expression='True', severity=severity).action_run_rule()
                run = self.env['muk_check.run']._record_run()
                self.assertEqual((run.score, run.grade), (score, grade))

    def test_a_rule_counts_once_toward_the_score(self):
        self.env['muk_check.finding'].search([]).unlink()
        self._rule(
            expression="['one', 'two', 'three']", severity='high'
        ).action_run_rule()
        run = self.env['muk_check.run']._record_run()
        self.assertEqual((run.score, run.high_count), (90, 3))

    def test_severity_override_counts(self):
        rule = self._rule(
            expression='True', severity='critical', severity_override='low'
        )
        rule.action_run_rule()
        self.assertEqual(rule.finding_ids.severity, 'low')
        self.assertEqual(self.env['muk_check.run']._record_run().score, 99)

    def test_upgrade_keeps_overrides_and_restores_logic(self):
        rule = self.env.ref('muk_check.rule_server_list_db')
        shipped = rule.expression
        rule.write({'severity_override': 'low', 'active': False, 'expression': 'False'})
        convert_file(self.env, 'muk_check', 'data/check_rule.xml', {}, mode='update')
        self.assertEqual(rule.severity_effective, 'low')
        self.assertFalse(rule.active)
        self.assertEqual(rule.expression, shipped)

    def test_rules_only_offer_models_with_their_own_records(self):
        offered = self.env['ir.model'].search(
            self.env['muk_check.rule']._domain_model_id()
        )
        names = offered.mapped('model')
        self.assertIn('res.partner', names)
        self.assertNotIn('mail.thread', names)
        self.assertNotIn('res.config.settings', names)

    def test_only_custom_rules_are_custom(self):
        with Form(self.env['muk_check.rule']) as form:
            form.name = 'A New Rule'
            form.kind = 'expression'
            form.expression = 'True'
        shipped = self.env.ref('muk_check.rule_server_list_db')
        self.assertFalse(shipped.is_custom)
        copied = shipped.copy()
        self.assertTrue(copied.is_custom)

    def test_turning_a_rule_off_resolves_its_findings(self):
        rule = self._rule(expression='True')
        rule.action_run_rule()
        finding = rule.finding_ids
        rule.active = False
        self._run_all()
        self.assertEqual(finding.state, 'resolved')

    def test_channel_message_once_per_new_finding(self):
        self.env['muk_check.rule'].search([]).active = False
        rule = self._flag_rule(name='Flagged Rule')
        self._set_flag(True)
        self._run_all()
        message = self._finding_messages()
        self.assertEqual(len(message), 1)
        self.assertIn('Flagged Rule', message.body)
        self.assertIn('1 new finding', message.body)
        self._run_all()
        self.assertEqual(len(self._finding_messages()), 1)
        self._set_flag(False)
        self._run_all()
        self.assertEqual(rule.finding_ids.state, 'resolved')
        self._set_flag(True)
        self._run_all()
        self.assertEqual(len(self._finding_messages()), 2)

    def test_channel_message_shows_each_rule_once(self):
        self.env['muk_check.rule'].search([]).active = False
        self._rule(
            name='Many Records',
            expression="env['res.users'].search([], limit=2)",
        )
        self._run_all()
        body = self._finding_messages().body
        self.assertEqual(body.count('Many Records'), 1)
        self.assertIn('2 records', body)
        self.assertIn('2 new findings', body)

    def test_channel_message_lists_the_five_most_severe_rules(self):
        self.env['muk_check.rule'].search([]).active = False
        for index in range(6):
            self._rule(
                name=f'Rule {index}',
                severity='medium' if index == 5 else 'critical',
                expression='True',
            )
        self._run_all()
        body = self._finding_messages().body
        self.assertEqual(sum(f'Rule {index}' in body for index in range(5)), 5)
        self.assertNotIn('Rule 5', body)
        self.assertIn('more', body)

    def test_a_deleted_channel_does_not_stop_the_check(self):
        self.env.ref('mail.channel_admin').unlink()
        rule = self._rule(expression='True')
        self._run_all()
        self.assertTrue(rule.finding_ids.notified)

    def test_settings_turn_off_online_checks_and_notifications(self):
        self.env['res.config.settings'].create(
            {'check_online': False, 'check_notifications': False}
        ).execute()
        self._rule(expression='True')
        with patch(STORE_POST) as store, patch(IMAGE_BUILDS) as images:
            self.env['muk_check.run'].action_run()
        self.assertFalse(store.called)
        self.assertFalse(images.called)
        self.assertFalse(self._finding_messages())

    def test_cron_runs_the_check(self):
        rule = self._rule(expression='True')
        before = self.env['muk_check.run'].search_count([])
        with (
            patch(STORE_POST, return_value=self._store_reply()),
            patch(IMAGE_BUILDS, return_value={}),
        ):
            self.env.ref('muk_check.ir_cron_check').ir_actions_server_id.run()
        self.assertEqual(rule.state, 'failed')
        self.assertEqual(self.env['muk_check.run'].search_count([]), before + 1)

    def test_cleanup_deletes_only_old_history(self):
        old_run, new_run = self.env['muk_check.run'].create([{}, {}])
        self.env.cr.execute(
            "UPDATE muk_check_run SET create_date = NOW() - INTERVAL '366 days' "
            'WHERE id = %s',
            [old_run.id],
        )
        self.env.invalidate_all()
        rule = self._rule()
        now = fields.Datetime.now()
        long_ago = now - timedelta(days=366)
        kept = self.env['muk_check.finding'].create(
            [
                {'rule_id': rule.id, 'state': 'open', 'last_seen': long_ago},
                {'rule_id': rule.id, 'state': 'accepted', 'last_seen': long_ago},
                {'rule_id': rule.id, 'state': 'resolved', 'last_seen': now},
            ]
        )
        deleted = self.env['muk_check.finding'].create(
            {'rule_id': rule.id, 'state': 'resolved', 'last_seen': long_ago}
        )
        parameters = self.env['ir.config_parameter'].sudo()
        for days in (0, 400):
            with self.subTest(days=days):
                parameters.set_param('muk_check.history_days', days)
                self.env['muk_check.run']._autovacuum_history()
                self.assertTrue(old_run.exists())
                self.assertTrue(deleted.exists())
        parameters.set_param('muk_check.history_days', 365)
        self.env['muk_check.run']._autovacuum_history()
        self.assertFalse(old_run.exists())
        self.assertTrue(new_run.exists())
        self.assertFalse(deleted.exists())
        self.assertEqual(kept.exists(), kept)

    def test_overview_runs_the_first_time_and_reuses_later(self):
        self.env['muk_check.run'].search([]).unlink()
        with (
            patch(STORE_POST, return_value=self._store_reply()),
            patch(IMAGE_BUILDS, return_value={}),
        ):
            first = self.env['muk_check.run'].action_open_overview()
        self.assertTrue(first['res_id'])
        self.assertEqual(
            self.env['muk_check.run'].action_open_overview()['res_id'], first['res_id']
        )
        run = self.env['muk_check.run'].browse(first['res_id'])
        rule = self._rule(expression='True')
        rule.action_run_rule()
        self.assertIn(rule.finding_ids, run.open_finding_ids)
        self.assertTrue(run.is_latest)
        self.assertTrue(run.next_check)
        self._run_all()
        run.invalidate_recordset()
        self.assertFalse(run.is_latest)
        self.assertFalse(run.open_finding_ids)
        self.assertFalse(run.next_check)

    def test_overview_says_how_many_findings_are_open(self):
        cases = [
            ({}, '0 open findings'),
            ({'low_count': 1}, '1 open finding'),
            ({'critical_count': 1, 'high_count': 2}, '3 open findings'),
        ]
        for values, note in cases:
            with self.subTest(note):
                run = self.env['muk_check.run'].create(values)
                self.assertEqual(run.open_note, note)

    def test_only_administrators_can_use_it(self):
        rule = self._rule()
        denied = [
            self.env['muk_check.run'].with_user(self.user).action_run,
            rule.with_user(self.user).action_run_rule,
        ]
        with patch(STORE_POST) as store:
            for action in denied:
                with self.subTest(action=action), self.assertRaises(AccessDenied):
                    action()
        self.assertFalse(store.called)
        for model in ('muk_check.rule', 'muk_check.finding', 'muk_check.run'):
            with self.subTest(model), self.assertRaises(AccessError):
                self.env[model].with_user(self.user).search([])
        manager = new_test_user(self.env, 'check_manager', 'base.group_erp_manager')
        with self.assertRaises(AccessError):
            rule.with_user(manager).action_run_rule()
