from __future__ import annotations

import base64
import csv
import datetime
import io
import zipfile

from odoo.exceptions import UserError

from odoo.addons.muk_mcp.tests.common import MCPToolCase
from odoo.addons.muk_mcp.tools.xlsx import build_xlsx


def read_xlsx(raw: bytes, part: str = 'xl/sharedStrings.xml') -> str:
    """Return one XML part of an XLSX payload."""
    with zipfile.ZipFile(io.BytesIO(raw)) as book:
        return book.read(part).decode()


class TestMcpExport(MCPToolCase):
    """Cover ``export_records`` and the XLSX writer it uses outside a request."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the partners every export selects."""
        super().setUpClass()
        cls.partners = cls.env['res.partner'].create(
            [
                {
                    'name': 'MCP Export A',
                    'email': 'a@example.com',
                    'country_id': cls.env.ref('base.at').id,
                },
                {'name': 'MCP Export B', 'email': 'b@example.com'},
            ],
        )
        cls.domain = [['name', 'like', 'MCP Export']]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_csv_export_selects_by_ids_or_domain(self):
        for selection, rows in (
            (
                {'ids': self.partners.ids, 'fields': ['name', 'email']},
                [
                    ['name', 'email'],
                    ['MCP Export A', 'a@example.com'],
                    ['MCP Export B', 'b@example.com'],
                ],
            ),
            (
                {
                    'domain': self.domain,
                    'order': 'name desc',
                    'limit': 1,
                    'fields': ['name'],
                },
                [['name'], ['MCP Export B']],
            ),
            (
                {'ids': self.partners[0].id, 'fields': ['name', 'country_id/code']},
                [['name', 'country_id/code'], ['MCP Export A', 'AT']],
            ),
            ({'domain': [['name', '=', 'nobody']], 'fields': ['name']}, [['name']]),
        ):
            with self.subTest(selection):
                result = self.call_tool(
                    'export_records', {'model': 'res.partner', **selection}
                )
                self.assertEqual(result['filename'], 'res_partner.csv')
                self.assertEqual(result['row_count'], len(rows) - 1)
                content = base64.b64decode(result['content_base64']).decode('utf-8-sig')
                self.assertEqual(list(csv.reader(io.StringIO(content))), rows)

    def test_xlsx_export_builds_a_workbook(self):
        result = self.call_tool(
            'export_records',
            {
                'model': 'res.partner',
                'ids': self.partners.ids,
                'fields': ['name', 'email'],
                'format': 'xlsx',
            },
        )
        self.assertEqual(result['filename'], 'res_partner.xlsx')
        self.assertIn('spreadsheetml', result['mimetype'])
        shared = read_xlsx(base64.b64decode(result['content_base64']))
        for value in ('name', 'MCP Export A', 'b@example.com'):
            self.assertIn(value, shared)

    def test_invalid_exports_raise(self):
        for arguments in (
            {'model': 'res.partner', 'fields': [], 'ids': self.partners.ids},
            {'model': 'no.such.model', 'fields': ['name']},
        ):
            with self.subTest(arguments), self.assertRaises(UserError):
                self.call_tool('export_records', arguments)

    def test_xlsx_cells_keep_their_types(self):
        raw = build_xlsx(
            self.env,
            ['flag', 'off', 'day', 'at', 'amount', 'blob', 'list', 'empty', 'note'],
            [
                [
                    True,
                    False,
                    datetime.date(2026, 7, 27),
                    datetime.datetime(2026, 7, 27, 14, 30),
                    1234.5,
                    b'from-bytes',
                    [1, 2],
                    None,
                    'a\rb' + 'x' * 40000,
                ],
            ],
        )
        sheet = read_xlsx(raw, 'xl/worksheets/sheet1.xml')
        self.assertIn('t="b"><v>1<', sheet)
        self.assertIn('t="b"><v>0<', sheet)
        self.assertIn('<v>1234.5</v>', sheet)
        shared = read_xlsx(raw)
        for value in ('from-bytes', '[1, 2]', 'a b' + 'x' * 32764):
            self.assertIn(value, shared)
        self.assertNotIn('x' * 32765, shared)

    def test_xlsx_refuses_more_rows_than_the_format_holds(self):
        with self.assertRaisesRegex(UserError, 'too many rows'):
            build_xlsx(self.env, ['name'], [['x']] * 1048576)
