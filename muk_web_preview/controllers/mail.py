import base64
import email
import email.policy

import lxml.html
import lxml.etree

from markupsafe import Markup, escape

from odoo import http
from odoo.http import request
from odoo.tools.mail import html_sanitize


class MailPreviewController(http.Controller):

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def _preview_css(self):
        return (
            'body {'
            '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",'
            '    Roboto, Helvetica, Arial, sans-serif;'
            '  margin: 0; padding: 0; color: #333; background: #fff;'
            '}'
            '.muk_mail_header {'
            '  padding: 12px 20px; background: #f8f9fa;'
            '  border-bottom: 1px solid #dee2e6; font-size: 13px;'
            '}'
            '.muk_mail_header td { padding: 2px 8px 2px 0; vertical-align: top; }'
            '.muk_mail_header .muk_label {'
            '  font-weight: 600; color: #6c757d; white-space: nowrap;'
            '}'
            '.muk_mail_body { padding: 20px; }'
            '.muk_mail_attachments {'
            '  padding: 12px 20px; border-top: 1px solid #dee2e6;'
            '  background: #f8f9fa; font-size: 13px;'
            '}'
            '.muk_mail_attachments .muk_label { font-weight: 600; margin-bottom: 6px; }'
            '.muk_mail_attachments ul { margin: 4px 0; padding-left: 20px; }'
            '.muk_mail_attachments li { margin: 2px 0; }'
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _parse_email(self, raw_bytes):
        return email.message_from_bytes(
            raw_bytes, policy=email.policy.SMTP,
        )

    def _extract_body(self, msg):
        body = msg.get_body(preferencelist=('html', 'plain'))
        if body is None:
            return ''
        content = body.get_content()
        if body.get_content_type() != 'text/html':
            content = f'<pre>{escape(content)}</pre>'
        return html_sanitize(content)

    def _extract_inline_images(self, msg):
        images = {}
        for part in msg.walk():
            content_type = part.get_content_type()
            if not content_type.startswith('image/'):
                continue
            cid = part.get('Content-ID', '').strip('<> ')
            if not cid:
                continue
            raw = part.get_content()
            if isinstance(raw, str):
                raw = raw.encode()
            b64 = base64.b64encode(raw).decode()
            images[cid] = f'data:{content_type};base64,{b64}'
        return images

    def _extract_attachments(self, msg):
        attachments = []
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            disposition = part.get('Content-Disposition', '')
            filename = part.get_filename()
            cid = part.get('Content-ID', '').strip('<> ')
            if cid and part.get_content_type().startswith('image/'):
                continue
            if not filename and not disposition.startswith('attachment'):
                continue
            raw = part.get_content()
            size = len(raw) if isinstance(raw, bytes) else len(
                raw.encode(),
            )
            attachments.append({
                'name': filename or 'attachment',
                'size': size,
            })
        return attachments

    def _resolve_cid_images(self, html_body, inline_images):
        if not inline_images or not html_body:
            return html_body
        try:
            root = lxml.html.fromstring(html_body)
        except (lxml.etree.ParserError, ValueError):
            return html_body
        for node in root.iter('img'):
            src = node.get('src', '')
            if src.startswith('cid:'):
                cid = src[4:]
                if cid in inline_images:
                    node.set('src', inline_images[cid])
        return lxml.etree.tostring(
            root, pretty_print=False, encoding='unicode',
        )

    def _render_header(self, msg):
        rows = []
        for label, header in [
            ('From', 'From'), ('To', 'To'),
            ('Cc', 'Cc'), ('Date', 'Date'),
            ('Subject', 'Subject'),
        ]:
            value = msg.get(header, '')
            if value:
                rows.append(
                    f'<tr><td class="muk_label">{label}:</td>'
                    f'<td>{escape(value)}</td></tr>'
                )
        if not rows:
            return ''
        return (
            f'<div class="muk_mail_header">'
            f'<table>{"".join(rows)}</table></div>'
        )

    def _render_attachments(self, attachments):
        if not attachments:
            return ''
        items = []
        for att in attachments:
            size_kb = max(1, att['size'] // 1024)
            items.append(
                f'<li>{escape(att["name"])} ({size_kb} KB)</li>'
            )
        return (
            '<div class="muk_mail_attachments">'
            '<div class="muk_label">Attachments:</div>'
            f'<ul>{"".join(items)}</ul>'
            '</div>'
        )

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @http.route(
        [
            '/muk_web_preview/preview/mail',
            '/muk_web_preview/preview/mail/<string:xmlid>',
            '/muk_web_preview/preview/mail/<string:xmlid>/<string:filename>',
            '/muk_web_preview/preview/mail/<int:id>',
            '/muk_web_preview/preview/mail/<int:id>/<string:filename>',
            '/muk_web_preview/preview/mail/<string:model>/<int:id>/<string:field>',
            '/muk_web_preview/preview/mail/<string:model>/<int:id>/<string:field>/<string:filename>',
        ],
        auth='user',
        type='http',
    )
    def preview_mail(
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
        msg = self._parse_email(stream.read())
        body = self._extract_body(msg)
        inline_images = self._extract_inline_images(msg)
        body = self._resolve_cid_images(body, inline_images)
        attachments = self._extract_attachments(msg)
        header = self._render_header(msg)
        att_html = self._render_attachments(attachments)
        return Markup(
            f'<!DOCTYPE html>'
            f'<html><head><meta charset="utf-8">'
            f'<style>{self._preview_css}</style>'
            f'</head><body>'
            f'{header}'
            f'<div class="muk_mail_body">{body}</div>'
            f'{att_html}'
            f'</body></html>'
        )
