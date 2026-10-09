import base64
import binascii
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.models.transfer import TRANSFER_MINUTES
from odoo.addons.muk_mcp.tools.descriptions import HTTP_HINT
from odoo.addons.muk_mcp.tools.uri import attachment_uri, record_field_uri

DEFAULT_MAX_UPLOAD_SIZE = 128 * 1024 * 1024
DATA_URI = re.compile(r'^data:(?P<mimetype>[\w.+-]+/[\w.+-]+)?(?:;[^,]*)?;base64,')


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_check_upload_size(self, size):
        """Refuse a file larger than the web client would accept.

        :raise UserError: when ``size`` exceeds ``web.max_file_upload_size``.
        """
        limit = int(self.env['ir.config_parameter'].sudo().get_param(
            'web.max_file_upload_size', DEFAULT_MAX_UPLOAD_SIZE,
        ))
        if size > limit:
            raise UserError(_(
                "The file is %(size)s bytes, more than the upload limit of %(limit)s.",
                size=size,
                limit=limit,
            ))

    @api.model
    def _mcp_decode_upload(self, data):
        """Decode base64 ``data``, or a ``data:`` URI, into bytes and a mimetype.

        :raise UserError: when the data is not base64 or exceeds the upload limit.
        """
        mimetype = None
        if match := DATA_URI.match(data):
            mimetype = match['mimetype']
            data = data[match.end():]
        try:
            raw = base64.b64decode(re.sub(r'\s+', '', data), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise UserError(_("The file data is not valid base64.")) from exc
        self._mcp_check_upload_size(len(raw))
        return raw, mimetype

    @api.model
    def _mcp_upload_to_field(self, record, field, raw):
        """Write ``raw`` into the binary ``field`` of ``record``.

        :raise UserError: when ``field`` is not a binary field of the model.
        """
        binary = [
            fname for fname, spec in record._fields.items() if spec.type == 'binary'
        ]
        if field not in binary:
            raise UserError(_(
                "%(field)s is not a binary field of %(model)s. Binary fields: %(fields)s",
                field=field,
                model=record._name,
                fields=', '.join(sorted(binary)) or '-',
            ))
        record.write({field: base64.b64encode(raw)})
        return {
            'model': record._name,
            'id': record.id,
            'field': field,
            'file_size': len(raw),
            'uri': record_field_uri(record._name, record.id, field),
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='authorize_upload',
        description=(
            'Get a one-time link to upload a file over plain HTTP: PUT the raw '
            f'bytes to upload_url (curl -T <path> <url>) within {TRANSFER_MINUTES} '
            'minutes, then pass the returned file uri to upload_file. ' + HTTP_HINT
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'name': {
                    'type': 'string',
                    'description': 'File name with extension, e.g. "offer.pdf".',
                },
                'size': {
                    'type': 'integer',
                    'description': 'Size in bytes; the upload must match it.',
                },
                'sha256': {
                    'type': 'string',
                    'description': 'Hex SHA-256 of the file; the upload must match it.',
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['name'],
        },
        category='write',
        registry='mcp',
    )
    def _mcp_authorize_upload(self, name, size=None, sha256=None):
        """Stage an empty attachment and issue the link that fills it."""
        if size:
            self._mcp_check_upload_size(size)
        attachment = self.env['ir.attachment'].create({'name': name})
        transfer, url = self.env['muk_mcp.transfer']._issue(
            'upload',
            attachment_id=attachment.id,
            file_size=size or 0,
            sha256=sha256 or False,
        )
        return {
            'file': attachment_uri(attachment.id),
            'upload_url': url,
            'method': 'PUT',
            'expires_at': fields.Datetime.to_string(transfer.expires_at),
            'example': f'curl -T "{name}" "{url}"',
        }

    @api.model
    @mcp_tool(
        name='upload_file',
        description=(
            'Put a file into Odoo from "file", an odoo:// uri (a chat attachment, '
            'a generated image, what authorize_upload returned), "text", the '
            'content of a text file as is (.txt, .md, .csv, .json), or "data", '
            'binary content as base64 for small files. With model, id and field it is '
            'written into that binary field (an image, a document); with model '
            'and id only it becomes an attachment of the record; with neither, '
            'a standalone attachment.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'file': {
                    'type': 'string',
                    'description': 'An odoo:// uri, e.g. the one authorize_upload returned.',
                },
                'text': {
                    'type': 'string',
                    'description': 'The content of a text file, as plain text.',
                },
                'data': {
                    'type': 'string',
                    'contentEncoding': 'base64',
                    'description': 'The file content, base64 encoded.',
                },
                'name': {
                    'type': 'string',
                    'description': (
                        'File name with extension, e.g. "offer.pdf". Required '
                        'with text or data; with file it defaults to its name.'
                    ),
                },
                'model': {
                    'type': 'string',
                    'description': 'Technical model of the record to upload to.',
                },
                'id': {
                    'type': 'integer',
                    'description': 'ID of the record to upload to.',
                },
                'field': {
                    'type': 'string',
                    'description': (
                        'Binary field to write, e.g. "image_1920". Omit it to '
                        'attach the file to the record instead.'
                    ),
                },
                'mimetype': {
                    'type': 'string',
                    'description': (
                        'Mimetype of the attachment. Default: guessed from the '
                        'content and the name.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
        },
        category='write',
    )
    def _mcp_upload_file(
        self, file=None, text=None, data=None, name=None, model=None, id=None,
        field=None, mimetype=None,
    ):
        """Store a file in a binary field or as an attachment.

        :raise UserError: when not exactly one of file, text and data is given, or a
            field comes without a model, or a model without its record.
        """
        if [bool(file), bool(text), bool(data)].count(True) != 1:
            raise UserError(_("Pass exactly one of file, text or data."))
        if file:
            source_mimetype, raw, source_name = self._resolve_resource_uri(file)
            if not raw:
                raise UserError(_(
                    "%s is empty: upload the file to its link first.", file,
                ))
        elif text:
            raw, source_mimetype, source_name = text.encode(), None, None
            self._mcp_check_upload_size(len(raw))
        else:
            raw, source_mimetype = self._mcp_decode_upload(data)
            source_name = None
        if not (name := name or source_name):
            raise UserError(_("A file name is required with text or data."))
        if field and not model:
            raise UserError(_("A model and record ID are required with a field."))
        record = self._mcp_record(model, id) if model else None
        if field:
            return self._mcp_upload_to_field(record, field, raw)
        values = {'name': name, 'raw': raw}
        if mimetype or source_mimetype:
            values['mimetype'] = mimetype or source_mimetype
        if record:
            values.update(res_model=record._name, res_id=record.id)
        attachment = self.env['ir.attachment'].create(values)
        return {
            'id': attachment.id,
            'name': attachment.name,
            'mimetype': attachment.mimetype,
            'file_size': attachment.file_size,
            'uri': attachment_uri(attachment.id),
        }
