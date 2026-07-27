from __future__ import annotations

import base64
import json
from unittest.mock import patch

from odoo import models
from odoo.tests import tagged

from odoo.addons.muk_ai.tests.common import AITestCommon, ToolCatalogMixin

CSV_BYTES = b'Customer,Revenue\nHarri Stojka,1538.48\n'
CSV_MIMETYPE = 'text/csv;charset=utf8'
XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PDF_MIMETYPE = 'application/pdf'


def _export_result(
    content: bytes = CSV_BYTES,
    mimetype: str = CSV_MIMETYPE,
    filename: str = 'res_partner.csv',
) -> dict:
    """Build a result in the shape ``export_records`` returns."""
    return {
        'filename': filename,
        'mimetype': mimetype,
        'row_count': 2,
        'content_base64': base64.b64encode(content).decode(),
    }


@tagged('post_install', '-at_install', 'muk_ai')
class TestToolFile(AITestCommon):
    """Verify file-bearing tool results become downloadable session attachments."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _new_session(self, name: str = 'files') -> models.Model:
        """Create a fresh AI session for the test user."""
        return self.env['muk_ai.session'].create({'name': name})

    # ----------------------------------------------------------
    # Tests: payload swap
    # ----------------------------------------------------------

    def test_an_export_result_trades_its_base64_for_a_download_url(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        self.assertNotIn('content_base64', stored)
        self.assertEqual(stored['row_count'], 2)
        self.assertEqual(
            stored['url'], '/web/content/%s?download=1' % stored['attachment_id']
        )

    def test_the_stored_attachment_carries_the_exact_export_bytes(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        attachment = self.env['ir.attachment'].browse(stored['attachment_id'])
        self.assertEqual(attachment.raw, CSV_BYTES)
        self.assertEqual(attachment.name, 'res_partner.csv')

    def test_the_transport_charset_is_stripped_from_the_stored_mimetype(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        attachment = self.env['ir.attachment'].browse(stored['attachment_id'])
        self.assertEqual(attachment.mimetype, 'text/csv')

    def test_the_result_reports_the_stored_mimetype_not_the_transport_one(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        self.assertEqual(stored['mimetype'], 'text/csv')

    def test_the_stored_export_can_be_attached_to_a_later_message(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        resolved = session._resolve_attachments([stored['attachment_id']])
        self.assertEqual(resolved.ids, [stored['attachment_id']])

    def test_a_stored_export_materializes_as_inline_text_for_the_model(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        block = (
            self.env['ir.attachment'].browse(stored['attachment_id'])._ai_materialize()
        )
        self.assertEqual(block['strategy'], 'inline_text')
        self.assertIn('Harri Stojka', block['inline_text'])

    def test_a_rendered_report_is_stored_as_a_pdf(self):
        session = self._new_session()
        stored = session._persist_tool_file(
            _export_result(
                content=b'%PDF-1.4 fake',
                mimetype=PDF_MIMETYPE,
                filename='sale_order.pdf',
            )
        )
        attachment = self.env['ir.attachment'].browse(stored['attachment_id'])
        self.assertEqual(attachment.mimetype, PDF_MIMETYPE)
        self.assertEqual(attachment.raw, b'%PDF-1.4 fake')

    def test_the_file_is_reachable_from_the_session_attachments(self):
        session = self._new_session()
        stored = session._persist_tool_file(_export_result())
        self.assertIn(stored['attachment_id'], session.attachment_ids.ids)

    def test_an_xlsx_export_is_stored_although_the_model_cannot_ingest_it(self):
        session = self._new_session()
        stored = session._persist_tool_file(
            _export_result(mimetype=XLSX_MIMETYPE, filename='res_partner.xlsx')
        )
        attachment = self.env['ir.attachment'].browse(stored['attachment_id'])
        self.assertEqual(attachment.mimetype, XLSX_MIMETYPE)

    def test_a_corrupt_payload_reports_an_error_instead_of_keeping_the_base64(self):
        session = self._new_session()
        stored = session._persist_tool_file(
            {'filename': 'broken.csv', 'mimetype': 'text/csv', 'content_base64': '!!!!'}
        )
        self.assertNotIn('content_base64', stored)
        self.assertNotIn('attachment_id', stored)
        self.assertIn('base64', stored['error'])

    def test_a_result_without_a_file_payload_is_returned_untouched(self):
        session = self._new_session()
        result = {'records': [{'id': 1}], 'length': 1}
        self.assertIs(session._persist_tool_file(result), result)
        self.assertEqual(session.attachment_ids.ids, [])

    # ----------------------------------------------------------
    # Tests: serialized results
    # ----------------------------------------------------------

    def test_a_json_encoded_export_result_is_materialized_too(self):
        session = self._new_session()
        stored = json.loads(session._persist_tool_file(json.dumps(_export_result())))
        self.assertNotIn('content_base64', stored)
        self.assertIn(stored['attachment_id'], session.attachment_ids.ids)

    def test_plain_text_results_are_returned_untouched(self):
        session = self._new_session()
        for result in ('nothing to see here', '{"content_base64": not json}'):
            self.assertIs(session._persist_tool_file(result), result)
        self.assertEqual(session.attachment_ids.ids, [])

    # ----------------------------------------------------------
    # Tests: conversation output
    # ----------------------------------------------------------

    def test_the_recorded_tool_output_never_carries_the_base64(self):
        session = self._new_session()
        outputs = []
        session._append_tool_output_with_vision(
            outputs, 'call-1', json.dumps(_export_result())
        )
        self.assertEqual(len(outputs), 1)
        output = outputs[0]['output']
        self.assertNotIn('content_base64', output)
        self.assertIn('/web/content/', output)

    def test_a_large_export_shrinks_the_model_facing_output(self):
        session = self._new_session()
        payload = _export_result(content=b'x' * 200000)
        outputs = []
        session._append_tool_output_with_vision(outputs, 'call-1', json.dumps(payload))
        self.assertLess(len(outputs[0]['output']), 500)

    # ----------------------------------------------------------
    # Tests: prompt contract
    # ----------------------------------------------------------

    def test_the_files_block_forbids_hand_written_file_contents(self):
        block = self._new_session()._build_files_block()
        self.assertIn('`data:` URIs', block)
        self.assertIn('/web/content/', block)

    def test_the_files_block_names_the_way_back_to_a_stored_file(self):
        block = self._new_session()._build_files_block()
        self.assertIn('odoo://attachment/', block)

    def test_the_files_block_reaches_the_system_prompt(self):
        session = self._new_session()
        prompt = session._system_message()['content'][0]['text']
        self.assertIn(session._build_files_block(), prompt)


@tagged('post_install', '-at_install', 'muk_ai')
class TestToolFileInlineLoad(ToolCatalogMixin, AITestCommon):
    """Verify a file produced through a bundled ``tool_load`` call is stored too."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create(
            {'name': 'Inline export', 'approval_mode': 'off'}
        )
        cls.session = cls.env['muk_ai.session'].create(
            {'name': 'Inline export', 'agent_id': cls.agent.id}
        )
        cls.catalog = [
            {
                'name': 'export_records',
                'description': 'Export records as CSV or XLSX',
                'inputSchema': {'type': 'object'},
            },
        ]

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _load_and_call(self) -> dict:
        """Run ``export_records`` through a bundled ``tool_load`` call."""
        with (
            self._patch_catalog(),
            patch.object(
                type(self.session),
                '_dispatch_tool_call',
                autospec=True,
                return_value=(json.dumps(_export_result()), True),
            ),
        ):
            return self.session._dispatch_tool_load(
                {
                    'names': ['export_records'],
                    'call': {
                        'name': 'export_records',
                        'arguments': {'model': 'res.partner'},
                    },
                },
                parent_call_id='call_inline',
            )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_bundled_call_stores_the_file_instead_of_returning_base64(self):
        output = self._load_and_call()['call']['output']
        self.assertNotIn('content_base64', output)
        self.assertIn('/web/content/', output)

    def test_a_bundled_call_attaches_the_file_to_the_session(self):
        before = self.session.attachment_ids.ids
        stored = json.loads(self._load_and_call()['call']['output'])
        self.session.invalidate_recordset(['attachment_ids'])
        self.assertNotIn(stored['attachment_id'], before)
        self.assertIn(stored['attachment_id'], self.session.attachment_ids.ids)

    def test_a_bundled_call_keeps_the_base64_out_of_the_event_log(self):
        self._load_and_call()
        self.session.invalidate_recordset(['event_ids'])
        payloads = json.dumps(self.session.event_ids.mapped('payload'))
        self.assertIn('/web/content/', payloads)
        self.assertNotIn('content_base64', payloads)
