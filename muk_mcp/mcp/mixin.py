from __future__ import annotations

import base64
from typing import Any

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.content import (
    is_textual_mimetype,
    normalize_mimetype,
)
from odoo.addons.muk_mcp.tools.uri import parse_uri


class MCPMixin(models.AbstractModel):
    """Base mixin carrying the shared helpers and tools for MCP endpoints."""

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
    def _mcp_apply_domain(self, model: str, domain) -> list:
        """Hook to merge a configured record domain into the caller domain."""
        return domain

    @api.model
    def _mcp_assert_records_allowed(self, model: str, ids) -> None:
        """Hook to assert the records may be exposed via MCP."""

    @api.model
    def _resolve_resource_uri(self, uri: str) -> tuple[str, bytes, str]:
        """Parse an MCP resource URI and dispatch to its handler.

        :return: a ``(mimetype, raw_bytes, name)`` tuple.
        :raise UserError: if the URI is malformed or its scheme is unsupported.
        """
        handlers = {
            'attachment': self._resolve_resource_attachment,
            'record_field': self._resolve_resource_record_field,
        }
        if not (parsed := parse_uri(uri)) or parsed[0] not in handlers:
            raise UserError(_('Unsupported resource URI: %r', uri))
        return handlers[parsed[0]](**parsed[1])

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

    @api.model
    def _resolve_resource_attachment(
        self, attachment_id: int
    ) -> tuple[str, bytes, str]:
        """Load an ``ir.attachment`` as ``(mimetype, raw, name)``.

        Enforces read access via :meth:`ir.attachment.check_access`.

        :raise UserError: if the attachment does not exist.
        """
        attachment = self.env['ir.attachment'].browse(attachment_id)
        if not attachment.exists():
            raise UserError(
                _(
                    'Attachment %(aid)s does not exist.',
                    aid=attachment_id,
                ),
            )
        attachment.check_access('read')
        return (
            attachment.mimetype or '',
            attachment.raw or b'',
            attachment.name or '',
        )

    @api.model
    def _resolve_resource_record_field(
        self,
        model: str,
        record_id: int,
        field: str,
    ) -> tuple[str, bytes, str]:
        """Read a binary field of a record as ``(mimetype, raw, name)``.

        Enforces record read access and field-level (``groups``) access,
        then prefers the backing ``ir.attachment`` (for attachment-stored
        fields), falling back to the decoded field value with a guessed
        mimetype.

        :raise UserError: if the field is not a binary field, the record is
            missing, or the value is empty.
        :raise AccessError: if the user lacks read access on the record or
            the field.
        """
        target = self._resolve_model(model)
        if target._fields.get(field) is None or target._fields[field].type != 'binary':
            raise UserError(
                _(
                    'Field %(f)r is not a readable binary field on %(m)s.',
                    f=field,
                    m=model,
                ),
            )
        if not (record := target.browse(record_id)) or not record.exists():
            raise UserError(
                _(
                    '%(m)s(%(id)s) does not exist.',
                    m=model,
                    id=record_id,
                ),
            )
        record.check_access('read')
        record._check_field_access(target._fields[field], 'read')
        attachment = (
            self.env['ir.attachment']
            .sudo()
            .search(
                [
                    ('res_model', '=', model),
                    ('res_id', '=', record_id),
                    ('res_field', '=', field),
                ],
                limit=1,
            )
        )
        if attachment:
            raw = attachment.raw or b''
            mimetype, name = (
                attachment.mimetype,
                attachment.name or field,
            )
        else:
            value = record.with_context(bin_size=False)[field]
            if not value:
                raise UserError(
                    _(
                        'Field %(f)s is empty on %(m)s(%(id)s).',
                        f=field,
                        m=model,
                        id=record_id,
                    ),
                )
            if isinstance(value, str):
                value = value.encode('ascii')
            try:
                raw = base64.b64decode(value)
            except (ValueError, TypeError):
                raw = value
            mimetype, name = None, field
        return (mimetype or guess_mimetype(raw), raw, name)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='list_modules',
        description=(
            'List installed Odoo modules with their names, versions, and '
            'descriptions. Use "search" to filter. This helps understand '
            'which apps and features are active in the system (e.g. is '
            '"sale" installed? is "stock" installed?).'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'search': {
                    'type': 'string',
                    'description': 'Filter module names by substring.',
                },
                'state': {
                    'type': 'string',
                    'description': "Filter by state. Default: 'installed'.",
                    'enum': [
                        'installed',
                        'uninstalled',
                        'to upgrade',
                        'to install',
                    ],
                    'default': 'installed',
                },
            },
        },
        category='read',
    )
    def _mcp_list_modules(
        self,
        search: str = '',
        state: str = 'installed',
    ) -> list[dict[str, Any]]:
        """List modules in a given state, optionally filtered by name.

        Returns name, label, installed version and state for each matching
        ``ir.module.module`` record, ordered by name.
        """
        domain = [('state', '=', state)]
        if search:
            domain.append(('name', 'ilike', search))
        modules = (
            self.env['ir.module.module']
            .sudo()
            .search_read(
                domain,
                fields=['name', 'shortdesc', 'state', 'installed_version'],
                order='name asc',
            )
        )
        return [
            {
                'name': m['name'],
                'label': m['shortdesc'],
                'version': m['installed_version'] or '',
                'state': m['state'],
            }
            for m in modules
        ]
