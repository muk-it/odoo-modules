import base64

from odoo.addons.muk_ai_browser.tests.common import BrowserTestCommon


class TestFiles(BrowserTestCommon):
    """Store files the browser fetched as attachments, never as model input."""

    def test_a_saved_file_becomes_an_attachment_of_its_record(self):
        partner = self.env['res.partner'].create({'name': 'Nordic Parts'})
        self._rule('https://shop.example.com', 'allow', self.env.user)
        data = base64.b64encode(b'%PDF-1.7 invoice').decode()
        for label, arguments, file, error in (
            ('a PDF', {}, {'name': 'inv.pdf', 'data': data}, None),
            ('a chosen name', {'name': 'Bill.pdf'}, {'name': 'x', 'data': data}, None),
            ('broken data', {}, {'name': 'x', 'data': '%%%'}, 'save_failed'),
            (
                'a gone record',
                {'res_id': 0},
                {'name': 'x', 'data': data},
                'save_failed',
            ),
            (
                'an unknown model',
                {'res_model': 'no.model'},
                {'data': data},
                'save_failed',
            ),
        ):
            with self.subTest(label):
                chat = self._browser_chat()
                call = {'res_model': 'res.partner', 'res_id': partner.id, **arguments}
                with self._mock_responses(
                    [
                        self._make_tool_response('browser_save_file', call, 'c0'),
                        self._make_text_response('ok'),
                    ]
                ):
                    chat.start('save it')
                result = chat._browser_store_file('c0', {'ok': True, 'file': file})
                if error:
                    self.assertEqual(result['error'], error)
                    continue
                attachment = self.env['ir.attachment'].browse(result['attachment_id'])
                self.assertEqual(
                    (attachment.res_model, attachment.res_id, attachment.raw),
                    ('res.partner', partner.id, b'%PDF-1.7 invoice'),
                )
                self.assertEqual(attachment.name, arguments.get('name', 'inv.pdf'))
                self.assertNotIn('data', str(result))

    def test_other_results_pass_unchanged(self):
        chat = self._browser_chat()
        with self._mock_responses(
            [
                self._make_tool_response('browser_read_page', {}, 'c0'),
                self._make_text_response('ok'),
            ]
        ):
            chat.start('read it')
        result = {'ok': True, 'file': {'data': 'x'}}
        self.assertIs(chat._browser_store_file('c0', result), result)
        self.assertIs(chat._browser_store_file('c9', result), result)
