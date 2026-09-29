from __future__ import annotations

from odoo import api, models
from odoo.tools import frozendict

BATCH_BINDINGS = (
    ('action', 'ir.actions.server'),
    ('report', 'ir.actions.report'),
)


class IrActionsActions(models.Model):
    """Expose batch-execution settings on action bindings."""

    _inherit = 'ir.actions.actions'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.ormcache('model_name', 'self.env.lang')
    def _get_bindings(self, model_name: str) -> frozendict:
        """Return the action bindings with the batch size of batch actions."""
        bindings = dict(super()._get_bindings(model_name))
        for binding_type, model in BATCH_BINDINGS:
            actions = bindings.get(binding_type, ())
            batch_sizes = {
                action.id: getattr(action, 'execution_batch_size', 1)
                for action in self.env[model]
                .sudo()
                .search(
                    [
                        ('id', 'in', [values['id'] for values in actions]),
                        ('execute_in_batch', '=', True),
                    ]
                )
            }
            bindings[binding_type] = tuple(
                frozendict(
                    values,
                    execute_in_batch=True,
                    execution_batch_size=batch_sizes[values['id']],
                )
                if values['id'] in batch_sizes
                else values
                for values in actions
            )
        return frozendict(bindings)
