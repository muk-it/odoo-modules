from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Partner(models.Model):
    """Extend ``res.partner`` with contact numbers and address defaults."""

    _inherit = 'res.partner'
    _rec_names_search = [
        'complete_name',
        'email',
        'ref',
        'vat',
        'company_registry',
        'contact_number',
    ]

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    contact_number = fields.Char(
        string='Contact Number',
        tracking=True,
        copy=False,
        index=True,
    )

    linked_user_id = fields.Many2one(
        compute='_compute_linked_user_id',
        search='_search_linked_user_id',
        comodel_name='res.users',
        string='Linked User',
        readonly=True,
        store=False,
    )

    linked_user_state = fields.Selection(
        compute='compute_linked_user_state',
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
    # Index
    # ----------------------------------------------------------

    _unique_contact_number = models.UniqueIndex(
        '(contact_number) WHERE contact_number IS NOT NULL AND parent_id IS NULL',
        'Another entry with the same contact number already exists.',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _commercial_fields(self) -> list[str]:
        """Add ``contact_number`` to the commercial fields propagated to children."""
        return super()._commercial_fields() + ['contact_number']

    @api.model
    def _get_next_contact_number(self, raise_exception: bool = False) -> str | bool:
        """Draw the next contact number from its sequence.

        :raise UserError: when ``raise_exception`` is set and the sequence
            cannot be found
        """
        contact_number = self.env['ir.sequence'].next_by_code('contact.number')
        if not contact_number and raise_exception:
            raise UserError(_("The contact number sequence couldn't be found."))
        return contact_number

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

    def _search_linked_user_id(self, operator: str, value) -> list:
        """Map a ``linked_user_id`` search onto the ``user_ids`` relation."""
        return [('user_ids', operator, value)]

    @api.depends('user_ids')
    def _compute_linked_user_id(self) -> None:
        """Expose the first linked user, including archived ones."""
        for record in self.with_context(active_test=False):
            record.linked_user_id = record.user_ids[0] if record.user_ids else False

    @api.depends('linked_user_id', 'linked_user_id.share')
    def compute_linked_user_state(self) -> None:
        """Derive whether the linked user is internal or portal."""
        self.linked_user_state = None
        for record in self.filtered('linked_user_id'):
            record.linked_user_state = (
                'internal' if record.linked_user_id._is_internal() else 'portal'
            )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model
    @api.readonly
    def web_name_search(
        self,
        name: str,
        specification: dict,
        domain: list | None = None,
        operator: str = 'ilike',
        limit: int = 100,
    ) -> list[dict]:
        """Augment name-search results with partner type icons."""
        result = super().web_name_search(name, specification, domain, operator, limit)
        if isinstance(result, list):
            partners = self.browse(
                [values['id'] for values in result if values.get('id')]
            )
            icon_vals = {
                partner.id: (partner.company_type, partner.type) for partner in partners
            }
            for values in result:
                company_type, partner_type = icon_vals.get(
                    values.get('id'), (False, False)
                )
                values.setdefault('company_type', company_type)
                values.setdefault('type', partner_type)
        return result

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> Partner:
        """Assign a contact number to new top-level partners lacking one."""
        for vals in vals_list:
            if not vals.get('contact_number', False) and not vals.get(
                'parent_id', False
            ):
                vals['contact_number'] = self._get_next_contact_number()
        return super().create(vals_list)
