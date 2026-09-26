from __future__ import annotations

from odoo import api, fields, models


class Honorific(models.Model):
    """Store honorific titles shown before or after a partner name."""

    _name = 'muk_contacts_vcard.honorific'
    _description = 'Honorific'
    _explanation = (
        'An honorific title such as Dr. or MBA, shown before or after the name of '
        'a contact and exported in its vCard. Use it to see which titles a '
        'contact may carry and whether they precede or follow the name.'
    )
    _order = 'sequence ASC'
    _rec_names_search = ('name', 'shortcut')

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Title',
        required=True,
        translate=True,
    )

    shortcut = fields.Char(
        compute='_compute_shortcut',
        string='Abbreviation',
        required=True,
        translate=True,
        precompute=True,
        readonly=False,
        store=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    position = fields.Selection(
        selection=[
            ('preceding', 'Preceding'),
            ('following', 'Following'),
        ],
        required=True,
        default='preceding',
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('name')
    def _compute_shortcut(self) -> None:
        """Default the abbreviation to the title when none is set."""
        for record in self.filtered(lambda r: not r.shortcut):
            record.shortcut = record.name
