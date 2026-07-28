from __future__ import annotations

from collections import defaultdict

from odoo import models, tools
from odoo.tools import frozendict


class IrActionsActions(models.Model):
    """Expose batch-execution metadata on action bindings."""

    _inherit = 'ir.actions.actions'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _update_bindings_batch_values(self, bindings: list[dict]) -> list[frozendict]:
        """Annotate binding values with their batch-execution settings."""
        binding_values_by_id = {v['id']: dict(v) for v in bindings}
        binding_ids_by_group = defaultdict(set)
        for record in self.sudo().browse(binding_values_by_id.keys()):
            if record.type in ('ir.actions.server', 'ir.actions.report'):
                binding_ids_by_group[record.type].add(record.id)

        for model, ids in binding_ids_by_group.items():
            recs = (
                self.env[model]
                .sudo()
                .browse(ids)
                .filtered(lambda r: r.execute_in_batch)
            )
            for rec in recs:
                binding_values_by_id[rec.id].update(
                    {
                        'execute_in_batch': True,
                        'execution_batch_size': (
                            rec.execution_batch_size
                            if model == 'ir.actions.server'
                            else 1
                        ),
                    }
                )
        return [frozendict(v) for v in binding_values_by_id.values()]

    @tools.ormcache('model_name', 'self.env.lang')
    def _get_bindings(self, model_name: str) -> frozendict:
        """Return action bindings enriched with batch-execution values."""
        res = dict(super()._get_bindings(model_name))
        if res.get('action'):
            res['action'] = self._update_bindings_batch_values(res['action'])
        if res.get('report'):
            res['report'] = self._update_bindings_batch_values(res['report'])
        return frozendict(res)
