from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_mcp.tools.content import (
    is_textual_mimetype,
    normalize_mimetype,
)
from odoo.addons.muk_mcp.tools.uri import parse_uri


class MCPMixin(models.AbstractModel):
    """Base mixin carrying the shared helpers for MCP endpoints."""

    _name = 'muk_mcp.mixin'
    _description = 'MCP Tool Mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_model(self, model: str) -> models.BaseModel:
        """Return the recordset for the given model name."""
        if not model or model not in self.env:
            raise UserError(_('Model %r not found', model))
        return self.env[model]

    @api.model
    def _mcp_record(self, model: str, res_id: int | None) -> models.BaseModel:
        """Return the existing record a tool targets, checked against the record hook.

        :raise UserError: when the model is unknown, the id is missing or the
            record does not exist.
        """
        target = self._resolve_model(model)
        if not res_id:
            raise UserError(_('A record ID is required with a model.'))
        self._mcp_assert_records_allowed(model, [res_id])
        if not (record := target.browse(res_id).exists()):
            raise UserError(
                _('Record %(model)s/%(id)s not found', model=model, id=res_id)
            )
        return record

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

        Empty here. A module parking agent files on its own records adds its
        models, so they stay readable under access restrictions layered on MCP.
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
                    _(
                        'Field %(f)r is not a readable binary field on %(m)s.',
                        f=field,
                        m=target._name,
                    ),
                )
            record = target.browse(params['record_id'])
        else:
            raise UserError(_('Unsupported resource URI: %r', uri))
        if not record.exists():
            raise UserError(_('Resource %s does not exist.', uri))
        record.check_access('read')
        record._check_field_access(record._fields[field], 'read')
        return record, field

    @api.model
    def _resolve_resource_uri(self, uri: str) -> tuple[str, bytes, str]:
        """Load the file an ``odoo://`` URI names, guessing a missing mimetype.

        :return: a ``(mimetype, raw_bytes, name)`` tuple.
        :raise UserError: as ``_resolve_resource_target``, or when a record's
            binary field is empty.
        """
        record, field = self._resolve_resource_target(uri)
        if record._name == 'ir.attachment':
            return record.mimetype or '', record.raw or b'', record.name or ''
        attachment = (
            self.env['ir.attachment']
            .sudo()
            .search(
                [
                    ('res_model', '=', record._name),
                    ('res_id', '=', record.id),
                    ('res_field', '=', field),
                ],
                limit=1,
            )
        )
        if attachment:
            raw, mimetype, name = (
                attachment.raw or b'',
                attachment.mimetype,
                attachment.name or field,
            )
        else:
            if not (value := record.with_context(bin_size=False)[field]):
                raise UserError(_('Resource %s is empty.', uri))
            if isinstance(value, str):
                value = value.encode('ascii')
            try:
                raw = base64.b64decode(value)
            except (ValueError, TypeError):
                raw = value
            mimetype, name = None, field
        return mimetype or guess_mimetype(raw), raw, name

    @api.model
    def _dispatch_resources_read(self, uri: str) -> dict[str, Any] | None:
        """Build an MCP ``resources/read`` entry for a URI.

        Resolves the URI, then returns the content inline as ``text`` for
        textual mimetypes or as base64 ``blob`` otherwise. Returns ``None`` when
        the URI is empty or cannot be resolved.
        """
        if not uri:
            return None
        try:
            mimetype, raw, name = self._resolve_resource_uri(
                uri,
            )
        except (UserError, AccessError):
            return None
        raw = raw or b''
        normalized = normalize_mimetype(mimetype)
        entry = {'uri': uri}
        if normalized:
            entry['mimeType'] = normalized
        if name:
            entry['name'] = name
        if is_textual_mimetype(normalized):
            try:
                entry['text'] = raw.decode('utf-8')
                return entry
            except UnicodeDecodeError:
                pass
        entry['blob'] = base64.b64encode(raw).decode(
            'ascii',
        )
        return entry
