from __future__ import annotations

from odoo import fields, models
from odoo.exceptions import AccessError
from odoo.tests.common import new_test_user, tagged

from odoo.addons.mail.tests.common import MailCommon


@tagged('post_install', '-at_install')
class TestMessageMove(MailCommon):
    """Test moving chatter messages to another record through the router."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a contact editor, a reader, source and target records and a customer."""
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login='mover', groups='base.group_user,base.group_partner_manager'
        )
        cls.reader = new_test_user(cls.env, login='reader', groups='base.group_user')
        partners = cls.env['res.partner']
        cls.source = partners.create({'name': 'Berger Logistik'})
        cls.target = partners.create({'name': 'Weber Handels'})
        cls.customer = partners.create({'name': 'Jonas Weber'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _email(self, body: str, **values) -> models.BaseModel:
        """Return an email of the customer on the source record."""
        return self.env['mail.message'].create(
            {
                'body': body,
                'author_id': self.customer.id,
                'message_type': 'email',
                'model': 'res.partner',
                'res_id': self.source.id,
                **values,
            }
        )

    def _attachment(self, name: str) -> models.BaseModel:
        """Return a file on the source record."""
        return self.env['ir.attachment'].create(
            {
                'name': name,
                'raw': b'data',
                'res_model': 'res.partner',
                'res_id': self.source.id,
            }
        )

    def _move(self, messages, target=None, configuration=None, user=None) -> dict:
        """Move the messages as the contact editor the way the chatter does."""
        user = user or self.user
        action = messages.with_user(user).action_route_message()
        return (
            self.env['muk_mail_route.router']
            .with_user(user)
            .with_context(action['context'], mail_route_single_record=True)
            .create(
                {
                    'configuration_id': configuration and configuration.id,
                    'reference': target and f'{target._name},{target.id}',
                }
            )
            .action_route()
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_move_takes_the_messages_and_the_files_only_they_use(self):
        own, shared = self._attachment('own.pdf'), self._attachment('shared.pdf')
        first = self._email(
            'Invoice question',
            attachment_ids=[fields.Command.set([own.id, shared.id])],
        )
        reply = self._email('Charged twice', parent_id=first.id)
        staying = self._email(
            'Delivery delay',
            parent_id=reply.id,
            attachment_ids=[fields.Command.link(shared.id)],
        )
        action = self._move(first | reply, self.target)
        self.assertEqual(action['res_id'], self.target.id)
        self.assertEqual(set((first | reply).mapped('res_id')), {self.target.id})
        self.assertEqual(reply.parent_id, first)
        self.assertFalse(staying.parent_id)
        self.assertEqual((own.res_model, own.res_id), ('res.partner', self.target.id))
        self.assertEqual(shared.res_id, self.source.id)
        for record, text in (
            (self.source, 'Messages moved to'),
            (self.target, 'Messages moved from'),
        ):
            with self.subTest(record=record.name):
                self.assertIn(text, record.message_ids[0].body)

    def test_move_needs_write_access(self):
        email = self._email('Invoice question')
        with self.assertRaises(AccessError):
            self._move(email, self.target, user=self.reader)
        self.assertEqual(email.res_id, self.source.id)

    def test_move_into_a_new_record_from_a_rule(self):
        rule = self.env['muk_mail_route.configuration'].create(
            {
                'name': 'New Contact',
                'model_id': self.env['ir.model']._get_id('res.partner'),
            }
        )
        email = self._email('Invoice question')
        note = self.source._message_log(body='Refund approved')
        self.assertIn(
            {'id': rule.id, 'name': 'New Contact'},
            self.env['mail.message'].with_user(self.user).get_route_configurations(),
        )
        action = self._move(email | note, configuration=rule)
        record = self.env['res.partner'].browse(action['res_id'])
        self.assertEqual(record.name, 'Invoice question')
        self.assertEqual((email | note).mapped('res_id'), [record.id, record.id])
        self.assertIn('Messages moved to', self.source.message_ids[0].body)
