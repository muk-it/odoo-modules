import base64
import csv
import io
import json

from odoo.exceptions import UserError
from odoo.tests import common


try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


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

    def test_export_xlsx_produces_zip_header(self):
        if xlsxwriter is None:
            self.skipTest("xlsxwriter not installed")
        try:
            from odoo.http import request  # noqa: PLC0415
            request.env
        except (ImportError, RuntimeError):
            self.skipTest(
                "xlsx export requires a bound HTTP request "
                "(odoo.addons.web.controllers.export.ExcelExport "
                "accesses request.env); covered by HttpCase tests."
            )
        result = self._call('export_records', {
            'model': 'res.partner',
            'fields': ['name'],
            'ids': [self.partner_a.id],
            'format': 'xlsx',
        })
        self.assertTrue(result['filename'].endswith('.xlsx'))
        self.assertIn('spreadsheetml', result['mimetype'])
        content = base64.b64decode(result['content_base64'])
        self.assertEqual(content[:2], b'PK')

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
