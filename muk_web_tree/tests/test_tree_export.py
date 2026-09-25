from __future__ import annotations

import io
import json
import zipfile

from lxml import etree

from odoo.tests import HttpCase

XLSX_NAMESPACE = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


class TestTreeExport(HttpCase):
    """Export the records of a treelist to Excel as a tree."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create a small tree of partners."""
        super().setUpClass()
        partner = cls.env['res.partner']
        cls.alpha = partner.create({'name': 'Tree Export Alpha'})
        cls.alpha_one = partner.create(
            {'name': 'Tree Export Alpha One', 'parent_id': cls.alpha.id}
        )
        cls.alpha_two = partner.create(
            {'name': 'Tree Export Alpha Two', 'parent_id': cls.alpha.id}
        )
        cls.leaf = partner.create(
            {'name': 'Tree Export Leaf', 'parent_id': cls.alpha_two.id}
        )
        cls.beta = partner.create({'name': 'Tree Export Beta'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _export(self, **params: object) -> list[tuple[str, int, int, bool]]:
        """Export the partner names, return each row's name, outline, indent and fill."""
        self.authenticate('admin', 'admin')
        data = {
            'model': 'res.partner',
            'fields': [{'name': 'name', 'label': 'Name', 'type': 'char'}],
            'domain': [('name', 'like', 'Tree Export')],
            'ids': False,
            'groupby': [],
            'import_compat': False,
            'context': {'treelist_parent_field': 'parent_id'},
            **params,
        }
        response = self.url_open(
            '/web/export/xlsx',
            data={'data': json.dumps(data), 'csrf_token': self.csrf_token()},
        )
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
            sheet = etree.fromstring(workbook.read('xl/worksheets/sheet1.xml'))
            strings = etree.fromstring(workbook.read('xl/sharedStrings.xml'))
            styles = etree.fromstring(workbook.read('xl/styles.xml'))
        texts = [node.text for node in strings.iterfind('x:si/x:t', XLSX_NAMESPACE)]
        cell_styles = [
            (
                int(alignment.get('indent', 0))
                if (alignment := node.find('x:alignment', XLSX_NAMESPACE)) is not None
                else 0,
                int(node.get('fillId', 0)) > 1,
            )
            for node in styles.iterfind('x:cellXfs/x:xf', XLSX_NAMESPACE)
        ]
        rows = []
        for row in sheet.findall('x:sheetData/x:row', XLSX_NAMESPACE)[1:]:
            cell = row.find('x:c', XLSX_NAMESPACE)
            rows.append(
                (
                    texts[int(cell.findtext('x:v', namespaces=XLSX_NAMESPACE))],
                    int(row.get('outlineLevel', 0)),
                    *cell_styles[int(cell.get('s', 0))],
                )
            )
        return rows

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_levels_put_parents_before_children(self):
        records = self.env['res.partner'].search(
            [('name', 'like', 'Tree Export')], order='id desc'
        )
        self.assertEqual(
            list(records._tree_export_levels('parent_id').items()),
            [
                (self.beta.id, 0),
                (self.alpha.id, 0),
                (self.alpha_two.id, 1),
                (self.leaf.id, 2),
                (self.alpha_one.id, 1),
            ],
        )

    def test_levels_make_orphans_roots(self):
        records = self.alpha_one | self.alpha_two | self.leaf
        self.assertEqual(
            records._tree_export_levels('parent_id'),
            {self.alpha_one.id: 0, self.alpha_two.id: 0, self.leaf.id: 1},
        )

    def test_export_writes_the_tree_outlined(self):
        self.assertEqual(
            self._export(),
            [
                ('Tree Export Alpha', 0, 0, False),
                ('Tree Export Alpha One', 1, 1, False),
                ('Tree Export Alpha Two', 1, 1, False),
                ('Tree Export Leaf', 2, 2, False),
                ('Tree Export Beta', 0, 0, False),
            ],
        )

    def test_export_of_selected_records_keeps_their_tree(self):
        self.assertEqual(
            self._export(ids=[self.beta.id, self.leaf.id, self.alpha_two.id]),
            [
                ('Tree Export Alpha Two', 0, 0, False),
                ('Tree Export Leaf', 1, 1, False),
                ('Tree Export Beta', 0, 0, False),
            ],
        )

    def test_export_without_the_parent_field_stays_flat(self):
        rows = self._export(context={})
        self.assertEqual({outline for _name, outline, _indent, _fill in rows}, {0})

    def test_search_export_writes_the_parents_as_headers(self):
        self.assertEqual(
            self._export(
                domain=[('name', '=', 'Tree Export Leaf')],
                context={'treelist_parent_field': 'parent_id', 'treelist_search': True},
            ),
            [
                ('Tree Export Alpha', 0, 0, True),
                ('Tree Export Alpha Two', 1, 1, True),
                ('Tree Export Leaf', 2, 2, False),
            ],
        )
