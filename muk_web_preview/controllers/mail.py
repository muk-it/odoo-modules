import base64
import email

import lxml.html
import lxml.etree

from markupsafe import Markup

from odoo import http
from odoo.http import request
from odoo.tools.image import image_data_uri


class MailPreviewController(http.Controller):

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
        parsed_values = request.env['mail.thread'].message_parse(
            email.message_from_bytes(stream.read(), policy=email.policy.SMTP),
            False,
        )
        cids = {
            attachment[2]['cid']: base64.b64encode(attachment[1])
            for attachment in parsed_values.get('attachments', [])
            if len(attachment) == 3 and attachment[2].get('cid')
        }
        root = lxml.html.fromstring(parsed_values['body'])
        for node in root.iter('img'):
            if node.get('src', '').startswith('cid:'):
                cid = node.get('src').split('cid:')[1]
                if cid in cids:
                    node.set('src', image_data_uri(cids[cid]))
        return Markup(lxml.etree.tostring(
            root, pretty_print=False, encoding='unicode',
        ))
