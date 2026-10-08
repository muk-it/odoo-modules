from __future__ import annotations

import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Field
from odoo.tools import formatLang

from odoo.addons.muk_ai.tools.runtime import coerce_ids


class AIApproval(models.Model):
    """Audit record of an AI tool-call approval decision."""

    _name = 'muk_ai.approval'
    _description = 'AI Approval Audit'
    _explanation = (
        'The audit trail of risky tool calls an AI agent asked to run: who '
        'approved or rejected it, when, on which model and records, and the '
        'arguments proposed and executed. Use it to check what an assistant was '
        'allowed to change.'
    )
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        compute='_compute_name',
        string='Name',
        store=True,
    )

    session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Session',
        readonly=True,
        required=True,
        index=True,
        ondelete='cascade',
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Agent',
        readonly=True,
        ondelete='set null',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Decided By',
        readonly=True,
        required=True,
        default=lambda self: self.env.user,
    )

    decision = fields.Selection(
        selection=[
            ('approved', 'Approved'),
            ('approved_session', 'Allow for Session'),
            ('rejected', 'Rejected'),
            ('auto_approved', 'Approved by Rule'),
        ],
        string='Decision',
        readonly=True,
        required=True,
    )

    tool_name = fields.Char(
        string='Tool',
        readonly=True,
        required=True,
        index=True,
    )

    res_model = fields.Char(
        string='Model',
        readonly=True,
        index=True,
    )

    res_ids = fields.Json(
        string='Record IDs',
        readonly=True,
    )

    method = fields.Char(
        string='Method',
        readonly=True,
    )

    reason = fields.Text(
        string='Risk Reason',
        readonly=True,
    )

    signature = fields.Char(
        string='Signature',
        readonly=True,
        index=True,
    )

    args_proposed = fields.Json(
        string='Proposed Arguments',
        readonly=True,
    )

    args_executed = fields.Json(
        string='Executed Arguments',
        readonly=True,
    )

    reject_reason = fields.Char(
        string='Rejection Reason',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _is_sensitive_model(self, model_name: str) -> bool:
        """Return whether the named model is flagged sensitive for AI."""
        return self.env['ir.model']._get(model_name).ai_sensitive

    @api.model
    def _signature(
        self, tool_name: str, model_name: str, method: str | None = None
    ) -> str:
        """Return a stable short hash identifying a tool/model/method tuple."""
        parts = [tool_name, model_name or '']
        if method:
            parts.append(method)
        return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:32]

    @api.model
    def _assess_risk(self, tool_name: str, arguments: dict) -> dict | None:
        """Return a risk descriptor when a tool call needs approval, else ``None``."""
        model_name = arguments.get('model') or ''
        if not self._is_sensitive_model(model_name):
            return None
        ids = coerce_ids(arguments.get('ids'))
        method = (
            (arguments.get('method') or '').strip()
            if tool_name == 'call_method'
            else ''
        )
        verbs = {
            'delete_records': f'unlink {len(ids)} record(s)',
            'call_method': f'call {method or "?"} on {len(ids)} record(s)',
            'update_records': f'update {len(ids)} record(s)',
            'create_records': 'create a new record',
        }
        if tool_name not in verbs:
            return None
        return {
            'tool': tool_name,
            'model': model_name,
            'ids': ids,
            'method': method,
            'reason': f'{model_name} is flagged sensitive. Approve to let the agent {verbs[tool_name]}.',
            'signature': self._signature(tool_name, model_name, method=method or None),
        }

    @api.model
    def _fmt_value(self, field: Field | None, value) -> str:
        """Render a field value as human-readable text per its field type.

        Without a field the value is rendered as a scalar, containers as JSON.
        """
        kind = field.type if field is not None else None
        if value is False or value is None:
            return ''
        if kind == 'selection':
            return dict(field._description_selection(self.env) or []).get(
                value, str(value)
            )
        if kind == 'boolean':
            return self.env._('Yes') if value else self.env._('No')
        if kind in ('integer', 'float', 'monetary') and isinstance(value, int | float):
            digits = field.get_digits(self.env) if kind == 'float' else None
            scale = digits[1] if digits else 0 if kind == 'integer' else 2
            return formatLang(self.env, value, digits=scale)
        if kind == 'many2one':
            if isinstance(value, (list, tuple)) and len(value) == 2:
                return str(value[1])
            if isinstance(value, int):
                try:
                    rec = self.env[field.comodel_name].browse(value).exists()
                    return rec.display_name or f'#{value}'
                except KeyError:
                    return f'#{value}'
                except (AccessError, MissingError):
                    return self.env._('(no access)')
            return str(value)
        if kind in ('many2many', 'one2many'):
            if not isinstance(value, list) or not value:
                return '' if value == [] else str(value)
            if isinstance(value[0], (list, tuple)):
                return '\n'.join(
                    ', '.join(
                        [line['title']]
                        + [
                            f'{item["label"]} {item["value"]}'
                            for item in line['details']
                        ]
                    )
                    for line in self._fmt_lines(field, value)
                )
            try:
                recs = self.env[field.comodel_name].browse(value).exists()
                return ', '.join(r.display_name or f'#{r.id}' for r in recs)
            except KeyError:
                return str(value)
            except (AccessError, MissingError):
                return self.env._('(%(count)s record(s), no access)', count=len(value))
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @api.model
    def _fmt_lines(self, field: Field | None, value) -> list[dict] | None:
        """Render x2many commands as lines of a title and details, else ``None``.

        A new line is titled by its name and details its other values; a command
        linking records is titled by the records it links.
        """
        if not (
            field is not None
            and field.type in ('many2many', 'one2many')
            and isinstance(value, list)
            and value
            and isinstance(value[0], (list, tuple))
        ):
            return None
        comodel = self.env[field.comodel_name]
        lines = []
        for command in value:
            title, details = json.dumps(command, ensure_ascii=False), []
            if len(command) == 3 and command[0] == 0 and isinstance(command[2], dict):
                texts = {
                    fname: text
                    for fname, raw in command[2].items()
                    if (text := self._fmt_value(comodel._fields.get(fname), raw))
                }
                title = texts.pop(comodel._rec_name, '') or next(
                    iter(texts.values()), ''
                )
                details = [
                    {'label': self._field_with_label(comodel, fname)[1], 'value': text}
                    for fname, text in texts.items()
                    if text != title
                ]
            elif len(command) == 3 and command[0] == 6:
                title = self._fmt_value(field, command[2])
            elif len(command) >= 2 and command[0] == 4:
                title = self._fmt_value(field, [command[1]])
            lines.append({'title': title, 'details': details})
        return lines

    @api.model
    def _targets_display_names(self, model_name: str, ids: list[int]) -> list[dict]:
        """Return id and display name for each target the caller may read.

        Names of records the caller cannot read are masked rather than resolved
        with elevated rights, so the approval card never leaks protected data.
        """
        if not model_name or model_name not in self.env or not ids:
            return []
        result = []
        for record in self.env[model_name].browse(ids):
            try:
                record.check_access('read')
                name = record.display_name or f'#{record.id}'
            except (AccessError, MissingError):
                name = self.env._('(no access)')
            result.append({'id': record.id, 'display_name': name})
        return result

    @api.model
    def _field_with_label(
        self, model: models.BaseModel | None, fname: str
    ) -> tuple[Field | None, str]:
        """Return a field and its label, falling back to the field name."""
        field = model._fields.get(fname) if model is not None else None
        return field, (field.string if field else fname) or fname

    @api.model
    def _read_current(
        self, model: models.BaseModel | None, ids: list[int], names: list[str]
    ) -> dict:
        """Read the current values of named fields, keyed by record id."""
        if model is None or not ids:
            return {}
        try:
            return {row['id']: row for row in model.browse(ids).read(names)}
        except (AccessError, MissingError):
            return {}

    @api.model
    def _build_change(
        self,
        model: models.BaseModel | None,
        ids: list[int],
        current: dict,
        fname: str,
        new_value,
    ) -> dict:
        """Return a before/after change descriptor for an update preview."""
        field, label = self._field_with_label(model, fname)
        froms = [self._fmt_value(field, current.get(rid, {}).get(fname)) for rid in ids]
        return {
            'field': fname,
            'label': label,
            'from': froms[0] if len(set(froms)) == 1 else '(varies)',
            'to': self._fmt_value(field, new_value),
            'lines': self._fmt_lines(field, new_value),
        }

    @api.model
    def _build_property(
        self, model: models.BaseModel | None, fname: str, new_value
    ) -> dict:
        """Return a property descriptor for a create preview."""
        field, label = self._field_with_label(model, fname)
        return {
            'field': fname,
            'label': label,
            'value': self._fmt_value(field, new_value),
            'lines': self._fmt_lines(field, new_value),
        }

    @api.model
    def _build_preview(self, tool_name: str, arguments: dict) -> dict | None:
        """Build a human-readable preview of a tool call's effect, or ``None``."""
        model_name = arguments.get('model') or ''
        model_label = self.env['ir.model']._get(model_name).name or model_name
        display = model_label or model_name
        ids = coerce_ids(arguments.get('ids'))
        base = {'model': model_name, 'model_label': model_label}

        def targets() -> list[dict]:
            """Return the display names of the records the call targets."""
            return self._targets_display_names(model_name, ids)

        if tool_name == 'delete_records':
            return {
                **base,
                'kind': 'delete',
                'title': f'Delete {len(ids)} {display} record(s)',
                'targets': targets(),
            }
        if tool_name == 'call_method':
            method = (arguments.get('method') or '').strip()
            return {
                **base,
                'kind': 'call',
                'title': f'Run {method or "?"} on {display}',
                'method': method,
                'targets': targets(),
            }
        values = arguments.get('values')
        model = self.env[model_name] if model_name in self.env else None
        if tool_name == 'create_records':
            records = values if isinstance(values, list) else [values]
            if not records or not all(isinstance(vals, dict) for vals in records):
                return None
            several = len(records) > 1
            return {
                **base,
                'kind': 'create',
                'title': f'New {len(records)} {display} records'
                if several
                else f'New {display}',
                'properties': [
                    {
                        **self._build_property(model, fname, new_value),
                        **({'record': index} if several else {}),
                    }
                    for index, vals in enumerate(records, 1)
                    for fname, new_value in vals.items()
                ],
            }
        if not isinstance(values, dict):
            return None
        if tool_name == 'update_records':
            current = self._read_current(model, ids, list(values))
            return {
                **base,
                'kind': 'update',
                'title': f'Update {len(ids)} {display} record(s)',
                'targets': targets(),
                'changes': [
                    self._build_change(model, ids, current, fname, new_value)
                    for fname, new_value in values.items()
                ],
            }
        return None

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('tool_name', 'res_model', 'decision')
    def _compute_name(self) -> None:
        """Build a readable name from the decision, tool, and model."""
        for record in self:
            parts = [
                p
                for p in (record.decision or 'new', record.tool_name, record.res_model)
                if p
            ]
            record.name = ' / '.join(parts)
