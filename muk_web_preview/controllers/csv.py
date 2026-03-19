import csv
import io

from markupsafe import Markup, escape

from odoo import http
from odoo.http import request


MAX_PREVIEW_ROWS = 500
MAX_PREVIEW_COLS = 50


class CSVPreviewController(http.Controller):

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
        model='ir.attachment',
        id=None,
        field='raw',
        filename=None,
        filename_field='name',
        mimetype=None,
        unique=False,
        access_token=None,
        **kw,
    ):
        record = request.env['ir.binary']._find_record(
            res_model=model,
            res_id=id and int(id),
            access_token=access_token,
            field=field,
        )
        stream = request.env['ir.binary']._get_stream_from(
            record, field, filename, filename_field, mimetype,
        )
        raw = stream.read()
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = raw.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            text = raw.decode('utf-8', errors='replace')
        dialect = csv.Sniffer().sniff(text[:8192])
        reader = csv.reader(io.StringIO(text), dialect)
        parts = [
            '<!DOCTYPE html>',
            '<html><head><meta charset="utf-8">',
            '<style>',
            'body { font-family: Arial, sans-serif; margin: 0; padding: 16px; }',
            'table { border-collapse: collapse; width: 100%; font-size: 13px; }',
            'th, td { border: 1px solid #dee2e6; padding: 6px 10px;',
            '  text-align: left; white-space: nowrap; max-width: 300px;',
            '  overflow: hidden; text-overflow: ellipsis; }',
            'th { background: #f8f9fa; position: sticky; top: 0; font-weight: 600; }',
            'tr:nth-child(even) td { background: #f8f9fa; }',
            'tr:hover td { background: #e9ecef; }',
            '.muk_truncated { padding: 8px 16px; color: #6c757d;',
            '  font-style: italic; font-size: 13px; }',
            '</style></head><body><table>',
        ]
        row_count = 0
        for row in reader:
            cols = row[:MAX_PREVIEW_COLS]
            tag = 'th' if row_count == 0 else 'td'
            cells = ''.join(
                f'<{tag}>{escape(cell)}</{tag}>' for cell in cols
            )
            if len(row) > MAX_PREVIEW_COLS:
                cells += f'<{tag}>\u2026</{tag}>'
            parts.append(f'<tr>{cells}</tr>')
            row_count += 1
            if row_count > MAX_PREVIEW_ROWS:
                break
        parts.append('</table>')
        if row_count > MAX_PREVIEW_ROWS:
            parts.append(
                '<div class="muk_truncated">'
                f'Showing first {MAX_PREVIEW_ROWS} rows\u2026'
                '</div>'
            )
        parts.append('</body></html>')
        return Markup('\n'.join(parts))
