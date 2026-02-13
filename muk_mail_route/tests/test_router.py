from unittest.mock import patch

from odoo import fields
from odoo.tests.common import tagged

from odoo.addons.mail.tests.common import MailCommon


@tagged('post_install', '-at_install')
class TestRouter(MailCommon):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.model_res_partner = cls.env.ref('base.model_res_partner')

        cls.container = cls.env['mail.thread']._get_failed_route_container()
        cls.partner_target = cls.env['res.partner'].create({
            'name': 'Mail Route Target',
            'group_rfq': 'default',
            'group_on': 'default',
        })

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _post_message(self, *, subject, attachment=False):
        msg = self.container.message_post(
            subject=subject,
            body='Test',
            message_type='comment',
        )
        if attachment:
            att = self.env['ir.attachment'].create({
                'name': 'test.txt',
                'raw': b'test',
                'res_model': msg._name,
                'res_id': msg.id,
            })
            msg.write({'attachment_ids': [fields.Command.link(att.id)]})
        return msg

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------
    
    def test_route_new_creates_record_per_message_and_attaches(self):
        config = self.env['muk_mail_route.configuration'].create({
            'name': 'Create Partner',
            'model_id': self.model_res_partner.id,
            'route_type': 'new',
            'code': "values = {'name': message.subject}",
        })

        msg_1 = self._post_message(subject='Partner A', attachment=True)
        msg_2 = self._post_message(subject='Partner B')

        wizard = self.env['muk_mail_route.router'].create({
            'configuration_id': config.id,
            'message_ids': [fields.Command.set([msg_1.id, msg_2.id])],
        })
        action = wizard.action_route()

        self.assertEqual(action.get('res_model'), 'res.partner')
        self.assertEqual(action.get('view_mode'), 'list,form')
        self.assertEqual(action.get('target'), 'current')

        partners = self.env['res.partner'].search([
            ('name', 'in', ['Partner A', 'Partner B']),
        ])
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

    def test_route_existing_attaches_messages_and_can_notify_internal(self):
        config = self.env['muk_mail_route.configuration'].create({
            'name': 'Attach to Existing',
            'model_id': self.model_res_partner.id,
            'route_type': 'search',
            'notify': True,
            'set_is_internal': True,
            'code': "values = {}",
        })

        msg = self._post_message(subject='To Existing')
        wizard = self.env['muk_mail_route.router'].create({
            'configuration_id': config.id,
            'reference': f'{self.partner_target._name},{self.partner_target.id}',
            'message_ids': [fields.Command.set([msg.id])],
        })

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
