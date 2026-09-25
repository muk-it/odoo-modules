from __future__ import annotations

import json

from xlsxwriter.format import Format

from odoo.http import Response, request

from odoo.addons.web.controllers.export import ExcelExport, ExportXlsxWriter

TREE_LEVELS = 'tree_levels'
MAX_OUTLINE_LEVEL = 7


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

    def _get_indent_style(self, level: int) -> Format:
        """Return the style of a first cell text on the given level."""
        if level not in self.indent_styles:
            self.indent_styles[level] = self.workbook.add_format(
                {'text_wrap': True, 'indent': level}
            )
        return self.indent_styles[level]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def write_header(self) -> None:
        """Write the header and show the outline buttons above the children."""
        super().write_header()
        self.worksheet.outline_settings(symbols_below=False)

    def write_tree_row(self, row: int, level: int, values: list) -> None:
        """Write a row indented and outlined by its level in the tree."""
        first, *others = values
        if level and isinstance(first, str):
            self.write(row, 0, first, self._get_indent_style(level))
        else:
            self.write_cell(row, 0, first)
        for column, value in enumerate(others, 1):
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
        """Order the records of a treelist export as a tree, with their levels."""
        params = json.loads(data)
        parent_field = params.get('context', {}).get('treelist_parent_field')
        if not parent_field or params.get('groupby') or params['import_compat']:
            return super().base(data)
        model = request.env[params['model']].with_context(**params['context'])
        if params['ids']:
            records = model.with_context(active_test=False).search(
                [('id', 'in', params['ids'])]
            )
        else:
            records = model.search(params['domain'])
        levels = records._tree_export_levels(parent_field)
        return super().base(
            json.dumps(
                {
                    **params,
                    'ids': list(levels),
                    'fields': [
                        {'name': '.id', 'label': 'ID', TREE_LEVELS: levels},
                        *params['fields'],
                    ],
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
        with TreeExportXlsxWriter(
            fields[1:], columns_headers[1:], len(rows)
        ) as xlsx_writer:
            level = 0
            for row_index, (record_id, *values) in enumerate(rows, 1):
                if record_id:
                    level = levels[str(record_id)]
                xlsx_writer.write_tree_row(row_index, level, values)
        return xlsx_writer.value
