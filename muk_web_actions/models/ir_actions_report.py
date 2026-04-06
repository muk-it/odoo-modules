
from odoo import api, fields, models, tools


class IrActionsReport(models.Model):

    _inherit = 'ir.actions.report'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------

    execute_in_batch = fields.Boolean(
        compute='_compute_execute_in_batch',
        string="Execute in Batch",
        default=False,
        readonly=False,
        store=True,
        help="If this flag is active, the reports are generated and downloaded one by one."
    )

    #----------------------------------------------------------
    # Compute
    #----------------------------------------------------------

    @api.depends('report_type')
    def _compute_execute_in_batch(self):
        for record in self:
            if record.report_type == 'qweb-html':
                record.execute_in_batch = False

    #----------------------------------------------------------
    # ORM
    #----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self.env.registry.clear_cache()
        return res

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res
