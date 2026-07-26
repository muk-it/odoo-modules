from __future__ import annotations

import base64
import csv
import io
import json
from typing import Any

from odoo.exceptions import UserError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMcpExportRecords(common.TransactionCase):
    """Covers export_records by ids/domain, relation traversal, limits, and errors."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.tool_model = cls.env['muk_mcp.tool']
        cls.partner_a = cls.env['res.partner'].create(
            {
                'name': 'MCP Export A',
                'email': 'a@example.com',
                'company_id': cls.env.company.id,
            },
        )
        cls.partner_b = cls.env['res.partner'].create(
            {
                'name': 'MCP Export B',
                'email': 'b@example.com',
                'company_id': cls.env.company.id,
            },
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run the ``name`` tool in-process and return its decoded JSON result."""
        text, _info = self.tool_model._call(name, arguments, self.env)
        return json.loads(text)

    def _decode_csv(self, result: dict[str, Any]) -> list[list[str]]:
        """Decode the base64 CSV payload of ``result`` into a list of rows."""
        content = base64.b64decode(result['content_base64']).decode('utf-8-sig')
        reader = csv.reader(io.StringIO(content))
        return list(reader)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_export_csv_by_ids(self):
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name', 'email'],
                'ids': [self.partner_a.id, self.partner_b.id],
            },
        )
        self.assertEqual(result['mimetype'], 'text/csv;charset=utf8')
        self.assertTrue(result['filename'].endswith('.csv'))
        self.assertEqual(result['row_count'], 2)
        rows = self._decode_csv(result)
        self.assertEqual(rows[0], ['name', 'email'])
        values = {row[0] for row in rows[1:]}
        self.assertIn('MCP Export A', values)
        self.assertIn('MCP Export B', values)

    def test_export_csv_by_domain(self):
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name'],
                'domain': [['name', 'in', ['MCP Export A', 'MCP Export B']]],
                'order': 'name asc',
            },
        )
        rows = self._decode_csv(result)
        self.assertEqual(result['row_count'], 2)
        self.assertEqual(rows[1][0], 'MCP Export A')
        self.assertEqual(rows[2][0], 'MCP Export B')

    def test_export_csv_traverses_relation(self):
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name', 'company_id/name'],
                'ids': [self.partner_a.id],
            },
        )
        rows = self._decode_csv(result)
        self.assertEqual(rows[0], ['name', 'company_id/name'])
        self.assertEqual(rows[1][0], 'MCP Export A')
        self.assertTrue(rows[1][1])

    def test_export_csv_limits_records(self):
        for i in range(3):
            self.env['res.partner'].create({'name': 'MCP Bulk %d' % i})
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name'],
                'domain': [['name', 'like', 'MCP Bulk']],
                'limit': 2,
            },
        )
        self.assertEqual(result['row_count'], 2)

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
            self._call(
                'export_records',
                {
                    'model': 'res.partner',
                    'fields': [],
                    'ids': [self.partner_a.id],
                },
            )

    def test_export_unknown_model_raises(self):
        with self.assertRaises(UserError):
            self._call(
                'export_records',
                {
                    'model': 'nonexistent.model',
                    'fields': ['name'],
                },
            )

    def test_export_empty_domain_returns_zero_rows(self):
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'fields': ['name'],
                'domain': [['name', '=', '__never_matches__']],
            },
        )
        self.assertEqual(result['row_count'], 0)
        rows = self._decode_csv(result)
        self.assertEqual(rows, [['name']])
