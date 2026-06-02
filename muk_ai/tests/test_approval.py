import json

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


# post_install: these reference account.move and create res.partner, which on
# Odoo 18 require sibling modules (e.g. account) to be fully loaded — only
# guaranteed once the registry is complete.
@tagged('post_install', '-at_install')
class TestApprovalRiskPredicate(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mark_sensitive('res.partner', 'account.move', 'muk_ai.session')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_delete_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk('delete_records', {
            'model': 'res.partner', 'ids': [1, 2],
        })
        self.assertIsNotNone(risk)
        self.assertEqual(risk['tool'], 'delete_records')
        self.assertTrue(risk['signature'])
        self.assertIn('flagged sensitive', risk['reason'])

    def test_call_method_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk('call_method', {
            'model': 'account.move',
            'method': 'action_post',
            'ids': [1],
        })
        self.assertIsNotNone(risk)
        self.assertEqual(risk['method'], 'action_post')
        self.assertIn('action_post', risk['reason'])

    def test_update_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk('update_records', {
            'model': 'res.partner',
            'ids': [1],
            'values': {'user_id': 1},
        })
        self.assertIsNotNone(risk)
        self.assertEqual(risk['tool'], 'update_records')

    def test_update_on_non_sensitive_model_is_safe(self):
        risk = self.env['muk_ai.approval']._assess_risk('update_records', {
            'model': 'res.partner.category',
            'ids': [1],
            'values': {'name': 'tag'},
        })
        self.assertIsNone(risk)

    def test_create_on_sensitive_model_is_risky(self):
        risk = self.env['muk_ai.approval']._assess_risk('create_records', {
            'model': 'res.users',
            'values': {'name': 'X'},
        })
        self.assertIsNotNone(risk)

    def test_create_on_non_sensitive_model_is_safe(self):
        risk = self.env['muk_ai.approval']._assess_risk('create_records', {
            'model': 'res.partner.category',
            'values': {'name': 'Tag'},
        })
        self.assertIsNone(risk)

    def test_signature_stable_for_same_tool_and_model(self):
        a = self.env['muk_ai.approval']._assess_risk('update_records', {
            'model': 'res.partner', 'ids': [1], 'values': {'user_id': 2},
        })
        b = self.env['muk_ai.approval']._assess_risk('update_records', {
            'model': 'res.partner', 'ids': [9], 'values': {'user_id': 3},
        })
        self.assertEqual(a['signature'], b['signature'])

    def test_signature_differs_when_tool_differs(self):
        a = self.env['muk_ai.approval']._assess_risk('delete_records', {
            'model': 'res.partner', 'ids': [1],
        })
        b = self.env['muk_ai.approval']._assess_risk('update_records', {
            'model': 'res.partner', 'ids': [1], 'values': {'name': 'X'},
        })
        self.assertNotEqual(a['signature'], b['signature'])

    def test_signature_differs_when_method_differs(self):
        a = self.env['muk_ai.approval']._assess_risk('call_method', {
            'model': 'account.move', 'ids': [1], 'method': 'action_post',
        })
        b = self.env['muk_ai.approval']._assess_risk('call_method', {
            'model': 'account.move', 'ids': [1], 'method': 'action_archive',
        })
        self.assertNotEqual(a['signature'], b['signature'])


# post_install: creates res.partner, which on Odoo 18 needs sibling modules
# (e.g. account's required res.partner.autopost_bills) fully loaded.
@tagged('post_install', '-at_install')
class TestApprovalPreview(AITestCommon):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_update_preview_shows_field_label_and_from_to(self):
        partner = self.env['res.partner'].create({'name': 'Preview Target'})
        preview = self.env['muk_ai.approval']._build_preview('update_records', {
            'model': 'res.partner', 'ids': [partner.id],
            'values': {'name': 'New Name'},
        })
        self.assertEqual(preview['kind'], 'update')
        self.assertEqual(len(preview['changes']), 1)
        change = preview['changes'][0]
        self.assertEqual(change['field'], 'name')
        self.assertEqual(change['from'], 'Preview Target')
        self.assertEqual(change['to'], 'New Name')
        targets = preview['targets']
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]['id'], partner.id)

    def test_update_preview_resolves_many2one_id_to_display_name(self):
        partner = self.env['res.partner'].create({'name': 'M2o Target'})
        user = self.env.ref('base.user_admin')
        preview = self.env['muk_ai.approval']._build_preview('update_records', {
            'model': 'res.partner', 'ids': [partner.id],
            'values': {'user_id': user.id},
        })
        change = preview['changes'][0]
        self.assertEqual(change['to'], user.display_name)

    def test_delete_preview_lists_display_names(self):
        p1 = self.env['res.partner'].create({'name': 'Del1'})
        p2 = self.env['res.partner'].create({'name': 'Del2'})
        preview = self.env['muk_ai.approval']._build_preview('delete_records', {
            'model': 'res.partner', 'ids': [p1.id, p2.id],
        })
        self.assertEqual(preview['kind'], 'delete')
        names = sorted(t['display_name'] for t in preview['targets'])
        self.assertEqual(names, ['Del1', 'Del2'])

    def test_call_method_preview_shows_method_and_targets(self):
        partner = self.env['res.partner'].create({'name': 'CallTarget'})
        preview = self.env['muk_ai.approval']._build_preview('call_method', {
            'model': 'res.partner', 'method': 'action_archive',
            'ids': [partner.id],
        })
        self.assertEqual(preview['kind'], 'call')
        self.assertEqual(preview['method'], 'action_archive')
        self.assertEqual(len(preview['targets']), 1)
        self.assertEqual(preview['targets'][0]['id'], partner.id)

    def test_create_preview_lists_property_labels(self):
        preview = self.env['muk_ai.approval']._build_preview('create_records', {
            'model': 'res.partner',
            'values': {'name': 'New Guy', 'email': 'new@x.test'},
        })
        self.assertEqual(preview['kind'], 'create')
        fields_seen = {p['field'] for p in preview['properties']}
        self.assertEqual(fields_seen, {'name', 'email'})
        name_prop = next(p for p in preview['properties'] if p['field'] == 'name')
        self.assertTrue(name_prop['label'])
        self.assertEqual(name_prop['value'], 'New Guy')

    def test_preview_survives_missing_model_gracefully(self):
        preview = self.env['muk_ai.approval']._build_preview('delete_records', {
            'model': 'nonexistent.model', 'ids': [1, 2],
        })
        self.assertEqual(preview['kind'], 'delete')
        self.assertEqual(preview['targets'], [])


class TestApprovalFlow(AITestCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mark_sensitive('res.partner')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_provider(self, payloads):
        remaining = list(payloads)

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            if not remaining:
                raise AssertionError('No more mocked responses')
            return remaining.pop(0)

        return patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        )

    def _patch_tool(self, result_by_tool):
        calls = []

        def fake(self_arg, name, arguments, env, enforce_scope):
            calls.append(name)
            return result_by_tool.get(name, '{"ok": true}'), {}, arguments.get('model')

        return patch.object(
            type(self.env['muk_mcp.tool']),
            '_execute',
            autospec=True,
            side_effect=fake,
        ), calls

    def _delete_call_payload(self, call_id='c1', ids=None):
        args = {'model': 'res.partner', 'ids': ids or [42]}
        return {
            'text': '',
            'tool_calls': [{
                'call_id': call_id,
                'name': 'delete_records',
                'arguments': args,
            }],
            'carry_inputs': [{
                'type': 'function_call',
                'name': 'delete_records',
                'arguments': json.dumps(args),
                'call_id': call_id,
            }],
            'usage': {'input_tokens': 2, 'output_tokens': 1},
        }

    def _text(self, text='done'):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [{
                'type': 'message',
                'content': [{'type': 'output_text', 'text': text}],
            }],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_risky_dispatch_pauses_for_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'approve-me'})
        with self._patch_provider([self._delete_call_payload()]):
            snapshot = session.start('delete 42')
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertIsInstance(session.pending_ask, dict)
        self.assertEqual(session.pending_ask['kind'], 'approval')
        self.assertEqual(session.pending_ask['name'], 'delete_records')

    def test_approve_once_dispatches_and_resumes(self):
        session = self.env['muk_ai.session'].create({'name': 'approve-run'})
        with self._patch_provider([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        tool_patch, calls = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._patch_provider([self._text('done')]):
            snapshot = session.approve_tool()
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('delete_records', calls)
        audit = self.env['muk_ai.approval'].search([
            ('session_id', '=', session.id),
            ('decision', '=', 'approved'),
        ])
        self.assertEqual(len(audit), 1)
        self.assertFalse(session.pending_ask)

    def test_reject_flows_rejected_by_user_back_to_model(self):
        session = self.env['muk_ai.session'].create({'name': 'reject'})
        with self._patch_provider([self._delete_call_payload()]):
            session.start('delete')
        captured = []

        def fake(
            self_arg,
            inputs,
            tools_schema=None,
            text_schema=None,
            on_delta=None,
            model=None,
            **kwargs,
        ):
            captured.append(list(inputs or []))
            return self._text('acknowledged')

        with patch.object(
            type(self.provider),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            snapshot = session.reject_tool(reason='not now')
        self.assertEqual(snapshot['state'], 'done')
        audit = self.env['muk_ai.approval'].search([
            ('session_id', '=', session.id),
            ('decision', '=', 'rejected'),
        ])
        self.assertEqual(len(audit), 1)
        tool_outputs_in_conversation = [
            item for item in session.conversation or []
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
        ]
        self.assertTrue(tool_outputs_in_conversation)
        last = tool_outputs_in_conversation[-1]
        parsed = json.loads(last.get('output') or '{}')
        self.assertEqual(parsed.get('error'), 'rejected_by_user')
        self.assertEqual(parsed.get('reason'), 'not now')

    def test_approve_for_session_auto_approves_same_signature(self):
        session = self.env['muk_ai.session'].create({'name': 'remember'})
        with self._patch_provider([self._delete_call_payload(call_id='c1', ids=[11])]):
            session.start('del 11')
        self.assertEqual(session.state, 'waiting')
        tool_patch, _calls = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._patch_provider([self._text('ok')]):
            session.approve_for_session()
        self.assertEqual(session.state, 'done')
        self.assertTrue(session.approved_signatures)

        tool_patch2, calls2 = self._patch_tool({'delete_records': '{"success": true}'})
        with self._patch_provider([
            self._delete_call_payload(call_id='c2', ids=[22]),
            self._text('auto ok'),
        ]), tool_patch2:
            snapshot = session.send_message('del 22')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('delete_records', calls2)
        auto = self.env['muk_ai.approval'].search([
            ('session_id', '=', session.id),
            ('decision', '=', 'auto_approved'),
        ])
        self.assertEqual(len(auto), 1)

    def test_approve_for_session_memory_is_scoped_to_that_session(self):
        s1 = self.env['muk_ai.session'].create({'name': 'first'})
        with self._patch_provider([self._delete_call_payload(call_id='c1', ids=[11])]):
            s1.start('del 11')
        tool_patch, _ = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._patch_provider([self._text('ok')]):
            s1.approve_for_session()

        s2 = self.env['muk_ai.session'].create({'name': 'second'})
        with self._patch_provider([self._delete_call_payload(call_id='c2', ids=[22])]):
            s2.start('del 22')
        self.assertEqual(s2.state, 'waiting')
        self.assertFalse(s2.approved_signatures)

    def test_agent_approval_mode_off_bypasses(self):
        agent = self.env['muk_ai.agent'].create({
            'name': 'Fast',
            'approval_mode': 'off',
        })
        session = self.env['muk_ai.session'].create({
            'name': 'no-approval', 'agent_id': agent.id,
        })
        tool_patch, calls = self._patch_tool({'delete_records': '{"success": true}'})
        with self._patch_provider([
            self._delete_call_payload(),
            self._text('done'),
        ]), tool_patch:
            snapshot = session.start('delete')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('delete_records', calls)
        self.assertFalse(session.pending_ask)
        self.assertEqual(
            self.env['muk_ai.approval'].search_count(
                [('session_id', '=', session.id)],
            ), 0,
        )

    def test_write_to_non_sensitive_model_does_not_trigger_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'safe'})
        args = {
            'model': 'res.partner.category', 'ids': [1],
            'values': {'name': 'harmless'},
        }
        update_payload = {
            'text': '',
            'tool_calls': [{
                'call_id': 'u1',
                'name': 'update_records',
                'arguments': args,
            }],
            'carry_inputs': [{
                'type': 'function_call',
                'name': 'update_records',
                'arguments': json.dumps(args),
                'call_id': 'u1',
            }],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }
        tool_patch, calls = self._patch_tool({'update_records': '{"success": true}'})
        with self._patch_provider([update_payload, self._text('ok')]), tool_patch:
            snapshot = session.start('rename tag')
        self.assertEqual(snapshot['state'], 'done')
        self.assertIn('update_records', calls)

    def test_send_message_queues_while_waiting_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'blocked'})
        with self._patch_provider([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        snapshot = session.send_message('queued while waiting')
        self.assertEqual(session.state, 'waiting')
        self.assertEqual(len(session.pending_ids), 1)
        self.assertEqual(
            session.pending_ids[0].content, 'queued while waiting',
        )
        self.assertEqual(
            snapshot['pending_user_messages'][0]['content'],
            'queued while waiting',
        )

    def test_compact_refused_while_waiting_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'no-compact'})
        with self._patch_provider([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        with self.assertRaises(UserError):
            session.compact()

    def test_stop_clears_pending_approval(self):
        session = self.env['muk_ai.session'].create({'name': 'stop-clears'})
        with self._patch_provider([self._delete_call_payload()]):
            session.start('delete')
        self.assertEqual(session.state, 'waiting')
        session.action_stop()
        self.assertEqual(session.state, 'stopped')
        self.assertFalse(session.pending_ask)

    def test_clear_wipes_approved_signatures(self):
        session = self.env['muk_ai.session'].create({'name': 'clearable'})
        with self._patch_provider([self._delete_call_payload()]):
            session.start('del')
        tool_patch, _ = self._patch_tool({'delete_records': '{"success": true}'})
        with tool_patch, self._patch_provider([self._text('ok')]):
            session.approve_for_session()
        self.assertTrue(session.approved_signatures)
        session.clear()
        self.assertFalse(session.approved_signatures)
