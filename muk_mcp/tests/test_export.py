import base64
import csv
import datetime
import io
import json
import zipfile
from typing import Any

from odoo.exceptions import UserError
from odoo.tests import common, tagged

from odoo.addons.muk_mcp.tools.xlsx import XlsxExport, build_xlsx


class TestMcpExportRecords(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.partner_a = cls.env['res.partner'].create({
            'name': 'MCP Export A',
            'email': 'a@example.com',
            'company_id': cls.env.company.id,
        })
        cls.partner_b = cls.env['res.partner'].create({
            'name': 'MCP Export B',
            'email': 'b@example.com',
            'company_id': cls.env.company.id,
        })

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name, arguments):
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text)

    def _decode_csv(self, result):
        content = base64.b64decode(result['content_base64']).decode('utf-8-sig')
        reader = csv.reader(io.StringIO(content))
        return list(reader)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_export_csv_by_ids(self):
        result = self._call('export_records', {
            'model': 'res.partner',
            'fields': ['name', 'email'],
            'ids': [self.partner_a.id, self.partner_b.id],
        })
        self.assertEqual(result['mimetype'], 'text/csv;charset=utf8')
        self.assertTrue(result['filename'].endswith('.csv'))
        self.assertEqual(result['row_count'], 2)
        rows = self._decode_csv(result)
        self.assertEqual(rows[0], ['name', 'email'])
        values = {row[0] for row in rows[1:]}
        self.assertIn('MCP Export A', values)
        self.assertIn('MCP Export B', values)

    def test_export_csv_by_domain(self):
        result = self._call('export_records', {
            'model': 'res.partner',
            'fields': ['name'],
            'domain': [['name', 'in', ['MCP Export A', 'MCP Export B']]],
            'order': 'name asc',
        })
        rows = self._decode_csv(result)
        self.assertEqual(result['row_count'], 2)
        self.assertEqual(rows[1][0], 'MCP Export A')
        self.assertEqual(rows[2][0], 'MCP Export B')

    def test_export_csv_traverses_relation(self):
        result = self._call('export_records', {
            'model': 'res.partner',
            'fields': ['name', 'company_id/name'],
            'ids': [self.partner_a.id],
        })
        rows = self._decode_csv(result)
        self.assertEqual(rows[0], ['name', 'company_id/name'])
        self.assertEqual(rows[1][0], 'MCP Export A')
        self.assertTrue(rows[1][1])

    def test_export_csv_limits_records(self):
        for i in range(3):
            self.env['res.partner'].create({'name': 'MCP Bulk %d' % i})
        result = self._call('export_records', {
            'model': 'res.partner',
            'fields': ['name'],
            'domain': [['name', 'like', 'MCP Bulk']],
            'limit': 2,
        })
        self.assertEqual(result['row_count'], 2)

    def test_export_xlsx_builds_a_real_workbook_without_a_request(self):
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name', 'email'],
                'ids': [self.partner_a.id, self.partner_b.id],
                'format': 'xlsx',
            },
        )
        self.assertTrue(result['filename'].endswith('.xlsx'))
        self.assertIn('spreadsheetml', result['mimetype'])
        self.assertEqual(result['row_count'], 2)
        raw = base64.b64decode(result['content_base64'])
        self.assertTrue(raw.startswith(b'PK\x03\x04'))
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            shared = book.read('xl/sharedStrings.xml').decode()
        self.assertIn('MCP Export A', shared)
        self.assertIn('a@example.com', shared)

    def test_build_exporter_selects_the_format_handler(self):
        mixin = self.env['muk_mcp.mixin']
        xlsx = mixin._build_exporter('xlsx')
        self.assertEqual(xlsx.extension, '.xlsx')
        self.assertIn('spreadsheetml', xlsx.content_type)
        for fmt in ('csv', '', 'bogus'):
            csv_exporter = mixin._build_exporter(fmt)
            self.assertEqual(csv_exporter.extension, '.csv', fmt)
            self.assertIn('csv', csv_exporter.content_type, fmt)

    def test_export_no_fields_raises(self):
        with self.assertRaises(UserError):
            self._call('export_records', {
                'model': 'res.partner',
                'fields': [],
                'ids': [self.partner_a.id],
            })

    def test_export_unknown_model_raises(self):
        with self.assertRaises(UserError):
            self._call('export_records', {
                'model': 'nonexistent.model',
                'fields': ['name'],
            })

    def test_export_empty_domain_returns_zero_rows(self):
        result = self._call('export_records', {
            'model': 'res.partner',
            'fields': ['name'],
            'domain': [['name', '=', '__never_matches__']],
        })
        self.assertEqual(result['row_count'], 0)
        rows = self._decode_csv(result)
        self.assertEqual(rows, [['name']])


@tagged('post_install', '-at_install')
class TestXlsxWriter(common.TransactionCase):
    """Covers the workbook builder used when no web request is bound."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _cells(self, raw: bytes) -> str:
        """Return the shared-string table of an XLSX payload."""
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            return book.read('xl/sharedStrings.xml').decode()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_headers_and_values_land_in_the_workbook(self):
        raw = build_xlsx(['name', 'email'], [['Alice', 'a@example.com']])
        self.assertTrue(raw.startswith(b'PK\x03\x04'))
        shared = self._cells(raw)
        for expected in ('name', 'email', 'Alice', 'a@example.com'):
            self.assertIn(expected, shared)

    def test_a_cell_longer_than_the_format_allows_is_truncated(self):
        raw = build_xlsx(['note'], [['x' * 40000]])
        shared = self._cells(raw)
        self.assertIn('x' * 32767, shared)
        self.assertNotIn('x' * 32768, shared)

    def test_both_booleans_survive_instead_of_one_blanking(self):
        raw = build_xlsx(['flag'], [[True], [False]])
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            sheet = book.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn('t="b"><v>1<', sheet)
        self.assertIn('t="b"><v>0<', sheet)

    def test_dates_floats_bytes_and_none_are_all_writable(self):
        raw = build_xlsx(
            ['when', 'at', 'amount', 'blob', 'empty'],
            [
                [
                    datetime.date(2026, 7, 27),
                    datetime.datetime(2026, 7, 27, 14, 30),
                    1234.5,
                    b'from-bytes',
                    None,
                ]
            ],
        )
        self.assertTrue(raw.startswith(b'PK\x03\x04'))
        self.assertIn('from-bytes', self._cells(raw))

    def test_the_exporter_advertises_the_xlsx_format(self):
        exporter = XlsxExport()
        self.assertEqual(exporter.extension, '.xlsx')
        self.assertIn('spreadsheetml', exporter.content_type)
        self.assertTrue(
            exporter.from_data(['name'], [['Alice']]).startswith(b'PK\x03\x04')
        )
