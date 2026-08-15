from __future__ import annotations

from odoo import api, models


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    """Keep contact numbers unique while partners are merged."""

    _inherit = 'base.partner.merge.automatic.wizard'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _update_values(
        self, src_partners: models.Model, dst_partner: models.Model
    ) -> None:
        """Release the source contact number before the destination claims it."""
        contact_number = False
        if not dst_partner.contact_number:
            numbered = src_partners.filtered('contact_number')
            contact_number = numbered[-1:].contact_number
            numbered.write({'contact_number': False})
            numbered.flush_recordset(['contact_number'])
        super()._update_values(src_partners, dst_partner)
        if contact_number and not dst_partner.contact_number:
            dst_partner.write({'contact_number': contact_number})
