from __future__ import annotations

import csv
import io

from markupsafe import Markup, escape

from odoo import http
from odoo.http import request


class CSVPreviewController(http.Controller):
    """Render CSV and TSV attachments as a styled HTML table preview."""

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def _max_preview_rows(self) -> int:
        return 500

    @property
    def _max_preview_cols(self) -> int:
        return 50

    @property
    def _preview_css(self) -> str:
        return (
            'body { font-family: Arial, sans-serif; margin: 0; padding: 16px; }'
            'table { border-collapse: collapse; width: 100%; font-size: 13px; }'
            'th, td {'
            '  border: 1px solid #dee2e6; padding: 6px 10px;'
            '  text-align: left; white-space: nowrap;'
            '  max-width: 300px; overflow: hidden; text-overflow: ellipsis;'
            '}'
            'th { background: #f8f9fa; position: sticky; top: 0; font-weight: 600; }'
            'tr:nth-child(even) td { background: #f8f9fa; }'
            'tr:hover td { background: #e9ecef; }'
            '.muk_truncated {'
            '  padding: 8px 16px; color: #6c757d;'
            '  font-style: italic; font-size: 13px;'
            '}'
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _decode_raw(self, raw: bytes) -> str:
        """Decode raw bytes trying a set of encodings, replacing on failure."""
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        return raw.decode('utf-8', errors='replace')

    def _sniff_dialect(self, text: str) -> type[csv.Dialect] | csv.Dialect:
        """Detect the CSV dialect from a text sample, defaulting to Excel."""
        try:
            return csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            return csv.excel

    def _render_row(self, row: list[str], tag: str) -> str:
        """Render a CSV row as an HTML table row, truncating extra columns."""
        cols = row[: self._max_preview_cols]
        cells = ''.join(f'<{tag}>{escape(cell)}</{tag}>' for cell in cols)
        if len(row) > self._max_preview_cols:
            cells += f'<{tag}>…</{tag}>'
        return f'<tr>{cells}</tr>'

    def _render_table(self, text: str) -> str:
        """Render the decoded CSV text as an HTML table, capping the row count."""
        dialect = self._sniff_dialect(text)
        reader = csv.reader(io.StringIO(text), dialect)
        rows = []
        truncated = False
        for index, row in enumerate(reader):
            if index > self._max_preview_rows:
                truncated = True
                break
            tag = 'th' if index == 0 else 'td'
            rows.append(self._render_row(row, tag))
        table = f'<table>{"".join(rows)}</table>'
        if truncated:
            table += (
                '<div class="muk_truncated">'
                f'Showing first {self._max_preview_rows} rows…'
                '</div>'
            )
        return table

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        [
            '/muk_web_preview/preview/csv',
            '/muk_web_preview/preview/csv/<string:xmlid>',
            '/muk_web_preview/preview/csv/<string:xmlid>/<string:filename>',
            '/muk_web_preview/preview/csv/<int:id>',
            '/muk_web_preview/preview/csv/<int:id>/<string:filename>',
            '/muk_web_preview/preview/csv/<string:model>/<int:id>/<string:field>',
            '/muk_web_preview/preview/csv/<string:model>/<int:id>/<string:field>/<string:filename>',
        ],
        auth='user',
        type='http',
    )
    def preview_csv(
        self,
        xmlid: str | None = None,
        model: str = 'ir.attachment',
        id=None,
        field: str = 'raw',
        filename: str | None = None,
        filename_field: str = 'name',
        mimetype: str | None = None,
        unique: bool = False,
        access_token: str | None = None,
        **kw,
    ) -> Markup:
        """Serve an HTML table preview of a CSV/TSV attachment field."""
        record = request.env['ir.binary']._find_record(
            xmlid=xmlid,
            res_model=model,
            res_id=id and int(id),
            access_token=access_token,
            field=field,
        )
        stream = request.env['ir.binary']._get_stream_from(
            record,
            field,
            filename,
            filename_field,
            mimetype,
        )
        text = self._decode_raw(stream.read())
        table = self._render_table(text)
        return Markup(
            f'<!DOCTYPE html>'
            f'<html><head><meta charset="utf-8">'
            f'<style>{self._preview_css}</style>'
            f'</head><body>{table}</body></html>'
        )
