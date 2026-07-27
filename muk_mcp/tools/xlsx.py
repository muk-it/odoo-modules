from __future__ import annotations

import datetime
import io

import xlsxwriter

from odoo import _
from odoo.exceptions import UserError

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
XLSX_EXTENSION = '.xlsx'
COLUMN_WIDTH = 30


def build_xlsx(columns_headers: list[str], rows: list[list]) -> bytes:
    """Return an XLSX workbook holding ``rows`` under ``columns_headers``.

    Built straight on ``xlsxwriter``, the way every server-side export in Odoo
    is: the web controller's ``ExportXlsxWriter`` resolves ``request.env`` for
    its currency precision and error messages, so it only works inside a web
    request and raises ``object is not bound`` anywhere else.

    :raise UserError: when the row count exceeds the XLSX format limit
    """
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    styles = {
        'header': workbook.add_format({'bold': True}),
        'base': workbook.add_format({'text_wrap': True}),
        'date': workbook.add_format({'text_wrap': True, 'num_format': 'yyyy-mm-dd'}),
        'datetime': workbook.add_format(
            {'text_wrap': True, 'num_format': 'yyyy-mm-dd hh:mm:ss'}
        ),
        'float': workbook.add_format({'text_wrap': True, 'num_format': '#,##0.00'}),
    }
    if len(rows) >= worksheet.xls_rowmax:
        workbook.close()
        raise UserError(
            _(
                'There are too many rows (%(count)s rows, limit: %(limit)s) to '
                'export as XLSX. Export as CSV instead, or narrow the selection.',
                count=len(rows),
                limit=worksheet.xls_rowmax - 1,
            )
        )
    for column, header in enumerate(columns_headers):
        worksheet.write(0, column, header, styles['header'])
    worksheet.set_column(0, max(0, len(columns_headers) - 1), COLUMN_WIDTH)
    for index, row in enumerate(rows, start=1):
        for column, value in enumerate(row):
            cell, style = _coerce_cell(value, worksheet.xls_strmax)
            worksheet.write(index, column, cell, styles[style])
    workbook.close()
    return output.getvalue()


def _coerce_cell(value, max_chars: int) -> tuple[object, str]:
    """Return the writable form of ``value`` and the style name it needs.

    ``export_data`` yields ``''`` for empty fields and real booleans only for
    Boolean ones, so booleans are written as booleans rather than blanked;
    ``xlsxwriter`` renders every remaining scalar, including ``None``.
    """
    if isinstance(value, bytes):
        value = value.decode(errors='replace')
    elif isinstance(value, (list, tuple, dict)):
        value = str(value)
    if isinstance(value, str):
        return value[:max_chars].replace('\r', ' '), 'base'
    if isinstance(value, datetime.datetime):
        return value, 'datetime'
    if isinstance(value, datetime.date):
        return value, 'date'
    if isinstance(value, float):
        return value, 'float'
    return value, 'base'


class XlsxExport:
    """Export handler producing an XLSX workbook outside a web request."""

    content_type = XLSX_MIMETYPE
    extension = XLSX_EXTENSION

    def from_data(self, columns_headers: list[str], rows: list[list]) -> bytes:
        """Return the XLSX payload for ``rows``, mirroring ``ExcelExport``.

        ≤17's ``web.controllers.export`` handlers take ``(fields, rows)``;
        the leading ``descriptors`` argument arrived in 18.0.
        """
        return build_xlsx(columns_headers, rows)
