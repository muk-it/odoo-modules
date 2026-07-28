from odoo import fields, models


class Country(models.Model):
    """Extend ``res.country`` with the partner properties definition."""

    _inherit = 'res.country'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    partner_properties_definition = fields.PropertiesDefinition(
        string='Partner Properties',
    )
