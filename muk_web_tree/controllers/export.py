from __future__ import annotations

import json

from xlsxwriter.format import Format

from odoo.fields import Domain
from odoo.http import Response, request

from odoo.addons.web.controllers.export import ExcelExport, ExportXlsxWriter

TREE_LEVELS = 'tree_levels'
TREE_CONTEXT = 'tree_context'
MAX_OUTLINE_LEVEL = 7
HEADER_STYLE = {'bold': True, 'bg_color': '#e9ecef'}


class TreeExportXlsxWriter(ExportXlsxWriter):
    """Excel writer that indents and outlines the rows of a tree by level."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def __init__(self, fields: list[dict], columns_headers: list[str], row_count: int):
        """Prepare the indentation styles next to the default ones."""
        super().__init__(fields, columns_headers, row_count)
        self.indent_styles = {}

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_indent_style(self, level: int, header: bool) -> Format:
        """Return the style of a first cell on the given level."""
        if (level, header) not in self.indent_styles:
            self.indent_styles[level, header] = self.workbook.add_format(
                {'text_wrap': True, 'indent': level, **(HEADER_STYLE if header else {})}
            )
        return self.indent_styles[level, header]

    def _write_header_cell(self, row: int, column: int, value) -> None:
        """Write a cell of a header row in the style of a group header."""
        field_type = self.fields[column]['type']
        if field_type == 'monetary':
            self.write(row, column, value, self.header_bold_style_monetary)
        elif field_type == 'float':
            self.write(row, column, value, self.header_bold_style_float)
        elif isinstance(value, int) and not isinstance(value, bool):
            self.write(row, column, value, self.header_bold_style)
        else:
            self.write(row, column, str(value or ''), self.header_bold_style)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def write_header(self) -> None:
        """Write the header and show the outline buttons above the children."""
        super().write_header()
        self.worksheet.outline_settings(symbols_below=False)

    def write_tree_row(
        self, row: int, level: int, values: list, header: bool = False
    ) -> None:
        """Write a row indented and outlined by its level, as a header or a record."""
        first, *others = values
        if header or (level and isinstance(first, str)):
            self.write(row, 0, first, self._get_indent_style(level, header))
        else:
            self.write_cell(row, 0, first)
        for column, value in enumerate(others, 1):
            if header:
                self._write_header_cell(row, column, value)
            else:
                self.write_cell(row, column, value)
        self.worksheet.set_row(
            row, None, None, {'level': min(level, MAX_OUTLINE_LEVEL)}
        )


class TreeExcelExport(ExcelExport):
    """Export the records of a treelist to Excel parent by parent."""

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def base(self, data: str) -> Response:
        """Order the records of a treelist export as a tree, with their levels.

        A search also exports the parents of the matches, as header rows.
        """
        params = json.loads(data)
        parent_field = params.get('context', {}).get('treelist_parent_field')
        if not parent_field or params.get('groupby') or params['import_compat']:
            return super().base(data)
        model = request.env[params['model']].with_context(**params['context'])
        if params['ids']:
            model = model.with_context(active_test=False)
            domain = Domain('id', 'in', params['ids'])
        else:
            domain = Domain(params['domain'])
        if params['context'].get('treelist_search'):
            nodes, context = model._tree_nodes(domain, parent_field)
            records = model.search(Domain('id', 'in', list(nodes)))
        else:
            records, context = model.search(domain), {}
        levels = records._tree_export_levels(parent_field)
        tree_field = {
            'name': '.id',
            'label': 'ID',
            TREE_LEVELS: levels,
            TREE_CONTEXT: list(context),
        }
        return super().base(
            json.dumps(
                {
                    **params,
                    'ids': list(levels),
                    'fields': [tree_field, *params['fields']],
                }
            )
        )

    def from_data(
        self, fields: list[dict], columns_headers: list[str], rows: list[list]
    ) -> bytes:
        """Write the rows of a treelist export indented and outlined by level."""
        if not fields or TREE_LEVELS not in fields[0]:
            return super().from_data(fields, columns_headers, rows)
        levels = fields[0][TREE_LEVELS]
        context_ids = {str(record_id) for record_id in fields[0][TREE_CONTEXT]}
        with TreeExportXlsxWriter(
            fields[1:], columns_headers[1:], len(rows)
        ) as xlsx_writer:
            level, header = 0, False
            for row_index, (record_id, *values) in enumerate(rows, 1):
                if record_id:
                    level = levels[str(record_id)]
                    header = str(record_id) in context_ids
                xlsx_writer.write_tree_row(row_index, level, values, header)
        return xlsx_writer.value
