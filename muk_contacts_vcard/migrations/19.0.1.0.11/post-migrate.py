from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env['res.partner'].search([])
    partners._compute_complete_name()
