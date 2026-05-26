from odoo import _, api, fields, models


class MCPModelSelectionWizard(models.TransientModel):

    _name = 'muk_mcp_access.model.selection'
    _description = "MCP Model Selection Wizard"

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    _existing_model_ids = fields.Many2many(
        comodel_name='ir.model',
        compute='_compute_existing_model_ids',
    )

    model_ids = fields.Many2many(
        comodel_name='ir.model',
        string="Models",
        required=True,
        domain="[('transient', '=', False), ('id', 'not in', _existing_model_ids)]",
    )

    allow_read = fields.Boolean(
        string="Read",
        default=True,
    )

    allow_write = fields.Boolean(
        string="Write",
        default=False,
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_enable_models(self):
        access_model = self.env['muk_mcp_access.model']
        existing = set(
            access_model.search([]).mapped('model_id').ids
        )
        vals_list = [
            {
                'model_id': model.id,
                'allow_read': self.allow_read,
                'allow_write': self.allow_write,
            }
            for model in self.model_ids
            if model.id not in existing
        ]
        if vals_list:
            access_model.create(vals_list)
        return {'type': 'ir.actions.act_window_close'}

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends_context('uid')
    def _compute_existing_model_ids(self):
        existing = self.env['muk_mcp_access.model'].search([])
        ids = existing.mapped('model_id').ids
        for record in self:
            record._existing_model_ids = ids
