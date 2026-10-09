from __future__ import annotations

import base64
import mimetypes
from collections.abc import Callable
from typing import Any

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools import BinaryBytes

from odoo.addons.muk_mcp.tools.content import make_resource_entry, normalize_mimetype
from odoo.addons.muk_mcp.tools.parser import normalize_ids
from odoo.addons.muk_mcp.tools.uri import parse_uri


class MCPMixin(models.AbstractModel):
    """Base mixin carrying the shared helpers for MCP endpoints."""

    _name = 'muk_mcp.mixin'
    _description = 'MCP Tool Mixin'
    _explanation = (
        'The abstract model the built-in MCP tools live on. Each tool is a '
        'method decorated with mcp_tool; other modules add tools by '
        'inheriting it.'
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_model(self, model: str) -> models.BaseModel:
        """Return the recordset for the given model name."""
        if not model or model not in self.env:
            raise UserError(self.env._('Model %r not found', model))
        return self.env[model]

    @api.model
    def _mcp_records(self, model: str, ids) -> models.BaseModel:
        """Return the records a tool targets by id, checked against the record hook.

        :raise UserError: when the model is unknown or no id is given.
        """
        target = self._resolve_model(model)
        if not (target_ids := normalize_ids(ids)):
            raise UserError(self.env._('No record IDs provided'))
        self._mcp_assert_records_allowed(model, target_ids)
        return target.browse(target_ids)

    @api.model
    def _mcp_record(self, model: str, res_id: int | None) -> models.BaseModel:
        """Return the existing record a tool targets, checked against the record hook.

        :raise UserError: when the model is unknown, the id is missing or the
            record does not exist.
        """
        if not res_id:
            raise UserError(self.env._('A record ID is required with a model.'))
        if not (record := self._mcp_records(model, res_id).exists()):
            raise UserError(
                self.env._('Record %(model)s/%(id)s not found', model=model, id=res_id)
            )
        return record

    @api.model
    def _mcp_file_result(
        self, filename: str, mimetype: str, content: bytes, delivery: str
    ) -> dict[str, Any]:
        """Return a produced file as base64, or stored with a one-time download link.

        Links go only to clients calling over the MCP endpoint; callers inside
        Odoo get the file inline and keep it themselves.
        """
        result = {'filename': filename, 'mimetype': mimetype}
        if delivery != 'link' or not (request and getattr(request, '_mcp_key', None)):
            return {**result, 'content_base64': base64.b64encode(content).decode()}
        attachment = self.env['ir.attachment'].create(
            {'name': filename, 'raw': BinaryBytes(content, filename=filename)}
        )
        uri = f'odoo://attachment/{attachment.id}'
        _transfer, url = self.env['muk_mcp.transfer']._issue(
            'download', uri=uri, attachment_id=attachment.id
        )
        return {**result, 'file': uri, 'download_url': url}

    @api.model
    def _mcp_apply_domain(self, model: str, domain) -> list:
        """Hook to merge a configured record domain into the caller domain."""
        return domain

    @api.model
    def _mcp_assert_records_allowed(self, model: str, ids) -> None:
        """Hook to assert the records may be exposed via MCP."""

    @api.model
    def _mcp_call_model_method(
        self,
        target: models.BaseModel,
        method: str,
        unbound: Callable,
        args: list,
        kwargs: dict,
    ) -> Any:
        """Hook invoking an ``@api.model`` method reached through MCP.

        Such a method carries no record ids, so the record hook never fires
        for it and any narrowing has to happen around the call itself.
        """
        return unbound(target, *args, **kwargs)

    @api.model
    def _mcp_attachment_exempt_models(self) -> frozenset[str]:
        """Return the models whose attachments are MCP payloads, not business documents.

        Empty here. A module that keeps the files it hands to the agent on its
        own records adds those models, so access layers leave them readable.
        """
        return frozenset()

    @api.model
    def _resolve_resource_target(self, uri: str) -> tuple[models.BaseModel, str]:
        """Return the record and binary field an ``odoo://`` URI names, checked for reading.

        :raise UserError: if the URI is unsupported, the field not binary or the
            record missing.
        :raise AccessError: without read access on the record or the field.
        """
        kind, params = parse_uri(uri) or (None, {})
        if kind == 'attachment':
            record = self.env['ir.attachment'].browse(params['attachment_id'])
            field = 'raw'
        elif kind == 'record_field':
            target = self._resolve_model(params['model'])
            field = params['field']
            if (
                target._fields.get(field) is None
                or target._fields[field].type != 'binary'
            ):
                raise UserError(
                    self.env._(
                        'Field %(f)r is not a readable binary field on %(m)s.',
                        f=field,
                        m=target._name,
                    ),
                )
            record = target.browse(params['record_id'])
        else:
            raise UserError(self.env._('Unsupported resource URI: %r', uri))
        if not record.exists():
            raise UserError(self.env._('Resource %s does not exist.', uri))
        record.check_access('read')
        record.check_field_access(record._fields[field], 'read')
        return record, field

    @api.model
    def _resolve_resource_uri(self, uri: str) -> tuple[str, bytes, str]:
        """Load the file an ``odoo://`` URI names and refine its mimetype.

        :return: a ``(mimetype, raw_bytes, name)`` tuple.
        :raise UserError: as ``_resolve_resource_target``, or when a record's
            binary field is empty.
        """
        record, field = self._resolve_resource_target(uri)
        value = record[field]
        if record._name == 'ir.attachment':
            mimetype = record.mimetype or ''
            raw, name = value.content if value else b'', record.name or ''
        elif not value:
            raise UserError(self.env._('Resource %s is empty.', uri))
        else:
            mimetype, raw, name = value.mimetype, value.content, value.filename or field
        if normalize_mimetype(mimetype) in ('', 'application/octet-stream'):
            mimetype = mimetypes.guess_type(name)[0] or mimetype
        return mimetype, raw, name

    @api.model
    def _dispatch_resources_read(self, uri: str) -> dict[str, Any] | None:
        """Build the ``resources/read`` entry of a URI, or ``None`` when unresolvable."""
        try:
            mimetype, raw, name = self._resolve_resource_uri(uri)
        except (UserError, AccessError):
            return None
        return make_resource_entry(uri, mimetype, raw or b'', name)
