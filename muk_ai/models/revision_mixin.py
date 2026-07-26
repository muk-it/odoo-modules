from __future__ import annotations

import difflib

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AIRevisionMixin(models.AbstractModel):
    """Track and restore historical revisions of prompt fields."""

    _name = 'muk_ai.revision.mixin'
    _description = 'AI Revision Mixin'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    prompt_history = fields.Json(
        string='Prompt History',
        prefetch=False,
        readonly=True,
    )

    prompt_history_metadata = fields.Json(
        string='Prompt History Metadata',
        compute='_compute_prompt_history_metadata',
    )

    prompt_history_count = fields.Integer(
        string='Revisions',
        compute='_compute_prompt_history_count',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_prompt_fields(self) -> list[str]:
        """Return the names of the fields whose history is tracked."""
        return []

    def _prompt_history_entries(self, field_name: str) -> list[dict]:
        """Return the stored revision entries for a field."""
        return list((self.prompt_history or {}).get(field_name, []))

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def prompt_history_get_content(self, field_name: str, index: int) -> str:
        """Return the stored body of a revision.

        :raise UserError: when the revision index is out of range
        """
        entries = self._prompt_history_entries(field_name)
        if index < 0 or index >= len(entries):
            raise UserError(_('Revision not found.'))
        return entries[index].get('body') or ''

    def prompt_history_unified_diff(self, field_name: str, index: int) -> str:
        """Return a unified diff between a revision and the current value."""
        old_body = self.prompt_history_get_content(field_name, index)
        new_body = self[field_name] or ''
        return '\n'.join(
            difflib.unified_diff(
                old_body.splitlines(),
                new_body.splitlines(),
                fromfile=_('Revision %d', index + 1),
                tofile=_('Current'),
                lineterm='',
            )
        )

    def prompt_history_restore(self, field_name: str, index: int) -> dict:
        """Restore a field from a revision and return a notification action."""
        body = self.prompt_history_get_content(field_name, index)
        self[field_name] = body
        field_label = self._fields[field_name].string
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _(
                    '%(field)s restored from revision %(index)d.',
                    field=field_label,
                    index=index + 1,
                ),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_prompt_history(self, field_name: str | None = None) -> dict:
        """Open the prompt-history dialog for a field.

        :raise UserError: when the record has no prompt field
        """
        prompt_fields = self._get_prompt_fields()
        target = field_name or (prompt_fields[0] if prompt_fields else None)
        if not target:
            raise UserError(_('This record has no prompt field.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'muk_ai.prompt_history_dialog',
            'name': _('History'),
            'params': {
                'res_model': self._name,
                'res_id': self.id,
                'field_name': target,
                'field_label': self._fields[target].string,
            },
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('prompt_history')
    def _compute_prompt_history_metadata(self) -> None:
        """Project the history into metadata without revision bodies."""
        for record in self:
            history = record.prompt_history or {}
            metadata = {}
            for field_name, entries in history.items():
                metadata[field_name] = [
                    {k: v for k, v in entry.items() if k != 'body'} for entry in entries
                ]
            record.prompt_history_metadata = metadata or None

    @api.depends('prompt_history')
    def _compute_prompt_history_count(self) -> None:
        """Count the total number of stored revisions."""
        for record in self:
            history = record.prompt_history or {}
            record.prompt_history_count = sum(
                len(entries) for entries in history.values()
            )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Snapshot prompt fields into the history before they change."""
        vals.pop('prompt_history', None)
        affected = set(vals).intersection(self._get_prompt_fields())
        if not affected:
            return super().write(vals)
        snapshots = {r.id: {f: r[f] or '' for f in affected} for r in self}
        result = super().write(vals)
        for record in self:
            history = dict(record.prompt_history or {})
            changed = False
            for name in affected:
                old = snapshots[record.id][name]
                if old and old != (record[name] or ''):
                    history[name] = [
                        {
                            'body': old,
                            'create_date': self.env.cr.now().isoformat(),
                            'create_uid': self.env.uid,
                            'create_user_name': self.env.user.name,
                        },
                        *history.get(name, []),
                    ]
                    changed = True
            if changed:
                super(AIRevisionMixin, record).write({'prompt_history': history})
        return result
