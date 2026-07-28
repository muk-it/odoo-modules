from __future__ import annotations

from unittest.mock import patch

from odoo import fields, models
from odoo.tests.common import new_test_user, tagged

from odoo.addons.mail.tests.common import MailCommon


@tagged('post_install', '-at_install')
class TestRouter(MailCommon):
    """Test routing failed messages onto new and existing records."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.model_res_partner = cls.env.ref('base.model_res_partner')
        cls.model_container = cls.env.ref(
            'muk_mail_route.model_muk_mail_route_container'
        )

        cls.container = cls.env['mail.thread']._get_failed_route_container()
        cls.partner_target = cls.env['res.partner'].create(
            {
                'name': 'Mail Route Target',
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _post_message(
        self,
        *,
        subject: str,
        attachment: bool = False,
    ) -> models.BaseModel:
        """Post a message on the container, optionally with an attachment."""
        msg = self.container.message_post(
            subject=subject,
            body='Test',
            message_type='comment',
        )
        if attachment:
            att = self.env['ir.attachment'].create(
                {
                    'name': 'test.txt',
                    'raw': b'test',
                    'res_model': msg._name,
                    'res_id': msg.id,
                }
            )
            msg.write({'attachment_ids': [fields.Command.link(att.id)]})
        return msg

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_route_new_creates_record_per_message_and_attaches(self):
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Create Partner',
                'model_id': self.model_res_partner.id,
                'route_type': 'new',
                'code': "values = {'name': message.subject}",
            }
        )

        msg_1 = self._post_message(subject='Partner A', attachment=True)
        msg_2 = self._post_message(subject='Partner B')

        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
                'message_ids': [fields.Command.set([msg_1.id, msg_2.id])],
            }
        )
        action = wizard.action_route()

        self.assertEqual(action.get('res_model'), 'res.partner')
        self.assertEqual(action.get('view_mode'), 'list,form')
        self.assertEqual(action.get('target'), 'current')

        partners = self.env['res.partner'].search(
            [
                ('name', 'in', ['Partner A', 'Partner B']),
            ]
        )
        self.assertEqual(set(partners.mapped('name')), {'Partner A', 'Partner B'})

        msg_1.invalidate_model(['model', 'res_id', 'attachment_ids'])
        msg_2.invalidate_model(['model', 'res_id'])
        self.assertEqual(msg_1.model, 'res.partner')
        self.assertEqual(msg_2.model, 'res.partner')
        self.assertIn(msg_1.res_id, partners.ids)
        self.assertIn(msg_2.res_id, partners.ids)

        self.assertTrue(msg_1.attachment_ids)
        self.assertEqual(msg_1.attachment_ids.res_model, 'res.partner')
        self.assertEqual(msg_1.attachment_ids.res_id, msg_1.res_id)

    def test_route_new_with_empty_code(self):
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Empty Code',
                'model_id': self.model_container.id,
                'route_type': 'new',
            }
        )
        config.write({'code': False})

        msg = self._post_message(subject='Empty Code Container')
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
                'message_ids': [fields.Command.set([msg.id])],
            }
        )
        action = wizard.action_route()

        self.assertEqual(action.get('res_model'), 'muk_mail_route.container')

        msg.invalidate_model(['model', 'res_id'])
        self.assertEqual(msg.model, 'muk_mail_route.container')

    def test_route_existing_attaches_messages_and_can_notify_internal(self):
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Attach to Existing',
                'model_id': self.model_res_partner.id,
                'route_type': 'search',
                'notify': True,
                'set_is_internal': True,
                'code': 'values = {}',
            }
        )

        msg = self._post_message(subject='To Existing')
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
                'reference': f'{self.partner_target._name},{self.partner_target.id}',
                'message_ids': [fields.Command.set([msg.id])],
            }
        )

        with patch.object(
            type(self.partner_target),
            '_notify_thread',
            autospec=True,
        ) as notify_mock:
            action = wizard.action_route()

        self.assertEqual(action.get('res_model'), 'res.partner')
        self.assertEqual(action.get('res_id'), self.partner_target.id)

        msg.invalidate_model(['model', 'res_id', 'is_internal'])
        self.assertEqual(msg.model, 'res.partner')
        self.assertEqual(msg.res_id, self.partner_target.id)
        self.assertTrue(msg.is_internal)
        self.assertTrue(notify_mock.called)

    def test_route_existing_without_notify_keeps_the_message_public(self):
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Attach Silently',
                'model_id': self.model_res_partner.id,
                'route_type': 'search',
                'notify': False,
                'set_is_internal': True,
            }
        )

        msg = self._post_message(subject='Silent')
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
                'reference': f'{self.partner_target._name},{self.partner_target.id}',
                'message_ids': [fields.Command.set([msg.id])],
            }
        )

        with patch.object(
            type(self.partner_target),
            '_notify_thread',
            autospec=True,
        ) as notify_mock:
            wizard.action_route()

        msg.invalidate_model(['model', 'res_id', 'is_internal'])
        self.assertEqual(msg.res_id, self.partner_target.id)
        self.assertFalse(msg.is_internal)
        self.assertFalse(notify_mock.called)

    def test_route_new_uses_the_configured_action(self):
        action = self.env['ir.actions.act_window'].create(
            {
                'name': 'Routed Partners',
                'res_model': 'res.partner',
                'view_mode': 'kanban,form',
            }
        )
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Create With Action',
                'model_id': self.model_res_partner.id,
                'route_type': 'new',
                'action_id': action.id,
                'code': "values = {'name': message.subject}",
            }
        )

        msg = self._post_message(subject='Action Partner')
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
                'message_ids': [fields.Command.set([msg.id])],
            }
        )
        result = wizard.action_route()

        self.assertEqual(result['name'], 'Routed Partners')
        self.assertEqual(result['view_mode'], 'kanban,form')
        partner = self.env['res.partner'].search(result['domain'])
        self.assertEqual(partner.name, 'Action Partner')

    def test_route_new_propagates_a_failing_snippet(self):
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Failing Code',
                'model_id': self.model_res_partner.id,
                'route_type': 'new',
                'code': "values = {'name': 1 / 0}",
            }
        )

        msg = self._post_message(subject='Boom')
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
                'message_ids': [fields.Command.set([msg.id])],
            }
        )
        with self.assertRaises(ZeroDivisionError):
            wizard.action_route()

    def test_configuration_flags_reset_without_a_configuration(self):
        config = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'Flagged',
                'model_id': self.model_res_partner.id,
                'route_type': 'search',
                'notify': True,
                'set_is_internal': True,
            }
        )
        wizard = self.env['muk_mail_route.router'].create(
            {
                'configuration_id': config.id,
            }
        )
        self.assertTrue(wizard.notify)
        self.assertTrue(wizard.set_is_internal)

        wizard.write({'configuration_id': False})
        self.assertFalse(wizard.notify)
        self.assertFalse(wizard.set_is_internal)

    def test_reference_selection_follows_model_access(self):
        plain_user = new_test_user(
            self.env,
            'router_plain_user',
            groups='base.group_user',
        )
        manager_user = new_test_user(
            self.env,
            'router_manager_user',
            groups='base.group_user,base.group_erp_manager',
        )
        wizard_model = self.env['muk_mail_route.router']

        plain_models = dict(wizard_model.with_user(plain_user)._selection_reference())
        manager_models = dict(
            wizard_model.with_user(manager_user)._selection_reference()
        )

        self.assertIn('res.partner', plain_models)
        self.assertNotIn('muk_mail_route.container', plain_models)
        self.assertIn('muk_mail_route.container', manager_models)
