from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import UserError


class Partner(models.Model):
    """Extend ``res.partner`` with contact numbers and address defaults."""

    _inherit = 'res.partner'
    _rec_names_search = ('complete_name', 'email', 'ref', 'vat', 'contact_number')

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    contact_number = fields.Char(
        string='Contact Number',
        tracking=True,
        copy=False,
        index=True,
    )

    contact_kind = fields.Selection(
        compute='_compute_contact_kind',
        selection=[
            ('company', 'Company'),
            ('person', 'Person'),
            ('invoice', 'Invoice Address'),
            ('delivery', 'Delivery Address'),
            ('other', 'Other Address'),
        ],
        string='Contact Kind',
    )

    linked_user_id = fields.Many2one(
        comodel_name='res.users',
        compute='_compute_linked_user_id',
        search='_search_linked_user_id',
        string='Linked User',
    )

    linked_user_state = fields.Selection(
        compute='_compute_linked_user_state',
        selection=[
            ('portal', 'Portal'),
            ('internal', 'Internal'),
        ],
        string='Linked User State',
    )

    default_invoice_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Default Invoice Address',
    )

    default_delivery_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Default Delivery Address',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _commercial_fields(self) -> list[str]:
        """Add ``contact_number`` to the commercial fields propagated to children."""
        return [*super()._commercial_fields(), 'contact_number']

    @api.model
    def _get_next_contact_number(self, raise_exception: bool = False) -> str | bool:
        """Draw the next contact number from its sequence.

        :raise UserError: when ``raise_exception`` is set and the sequence
            cannot be found
        """
        contact_number = self.env['ir.sequence'].next_by_code('contact.number')
        if not contact_number and raise_exception:
            raise UserError(
                self.env._("The contact number sequence couldn't be found.")
            )
        return contact_number

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_view_partner(self) -> dict:
        """Return a window action opening this partner's form view."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'name': self.name,
            'res_model': 'res.partner',
            'res_id': self.id,
            'views': [(self.env.ref('base.view_partner_form').id, 'form')],
            'context': self.env.context,
        }

    def action_generate_contact_number(self) -> None:
        """Assign a freshly drawn contact number to the record."""
        self.ensure_one()
        self.write(
            {'contact_number': self._get_next_contact_number(raise_exception=True)}
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def address_get(self, adr_pref: list[str] | None = None) -> dict[str, int]:
        """Resolve addresses, preferring the configured invoice/delivery defaults."""
        res = super().address_get(adr_pref=adr_pref)
        adr_pref = set(adr_pref or [])
        if self.default_invoice_partner_id and 'invoice' in adr_pref:
            res['invoice'] = self.default_invoice_partner_id.id
        if self.default_delivery_partner_id and 'delivery' in adr_pref:
            res['delivery'] = self.default_delivery_partner_id.id
        return res

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('contact_number')
    @api.depends_context('show_contact_number')
    def _compute_display_name(self) -> None:
        """Prefix the display name with the contact number when requested."""
        super()._compute_display_name()
        if self.env.context.get('show_contact_number'):
            for record in self.filtered('contact_number'):
                record.display_name = (
                    f'--[{record.contact_number}]-- {record.display_name}'
                    if self.env.context.get('formatted_display_name')
                    else f'[{record.contact_number}] {record.display_name}'
                )

    @api.depends('is_company', 'type')
    def _compute_contact_kind(self) -> None:
        """Classify the partner as an address by its type, else as company or person."""
        for record in self:
            if record.type in ('invoice', 'delivery', 'other'):
                record.contact_kind = record.type
            else:
                record.contact_kind = 'company' if record.is_company else 'person'

    @api.depends('user_ids')
    def _compute_linked_user_id(self) -> None:
        """Expose the first linked user, including archived ones."""
        for record in self.with_context(active_test=False):
            record.linked_user_id = record.user_ids[:1]

    def _search_linked_user_id(self, operator: str, value) -> list:
        """Map a ``linked_user_id`` search onto the ``user_ids`` relation."""
        return [('user_ids', operator, value)]

    @api.depends('linked_user_id', 'linked_user_id.share')
    def _compute_linked_user_state(self) -> None:
        """Derive whether the linked user is internal or portal."""
        self.linked_user_state = False
        for record in self.filtered('linked_user_id'):
            record.linked_user_state = (
                'internal' if record.linked_user_id._is_internal() else 'portal'
            )

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _unique_contact_number = models.UniqueIndex(
        '(contact_number) WHERE contact_number IS NOT NULL AND parent_id IS NULL',
        'Another entry with the same contact number already exists.',
    )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> Partner:
        """Assign a contact number to new top-level partners lacking one."""
        for vals in vals_list:
            if not vals.get('contact_number') and not vals.get('parent_id'):
                vals['contact_number'] = self._get_next_contact_number()
        return super().create(vals_list)

    def write(self, vals: dict) -> bool:
        """Renumber detached children still carrying an inherited contact number."""
        if (
            'parent_id' in vals
            and not vals.get('parent_id')
            and 'contact_number' not in vals
        ):
            for record in self:
                if (
                    record.parent_id
                    and record.contact_number
                    and record.commercial_partner_id != record
                    and record.contact_number
                    == record.commercial_partner_id.contact_number
                ):
                    record.contact_number = self._get_next_contact_number()
        return super().write(vals)
