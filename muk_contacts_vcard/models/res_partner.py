from __future__ import annotations

import uuid

from odoo import api, fields, models
from odoo.tools import format_date, html2plaintext

try:
    import vobject
except ImportError:
    vobject = None


class Partner(models.Model):
    """Extend partners with structured name, honorifics, and vCard fields."""

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

    name = fields.Char(
        compute='_compute_name',
        inverse='_inverse_name',
        readonly=False,
        store=True,
        precompute=True,
    )

    firstname = fields.Char(
        string='First Name',
        tracking=True,
        index=True,
    )

    middlename = fields.Char(
        string='Middle Name',
        tracking=True,
        index=True,
    )

    lastname = fields.Char(
        string='Last Name',
        tracking=True,
        index=True,
    )

    formatted_name = fields.Char(
        compute='_compute_formatted_name',
        string='Formatted Name',
        store=True,
        readonly=True,
        index=True,
    )

    department = fields.Char(
        string='Department',
    )

    role = fields.Char(
        string='Job Role',
    )

    gender = fields.Selection(
        selection=[
            ('m', 'Male'),
            ('f', 'Female'),
            ('o', 'Other'),
        ],
        string='Gender',
    )

    honorific_prefix_ids = fields.Many2many(
        comodel_name='muk_contacts_vcard.honorific',
        relation='partner_honorific_prefix_rel',
        column1='partner_id',
        column2='honorific_id',
        string='Honorific Prefixes',
        domain=[('position', '=', 'preceding')],
    )

    honorific_suffix_ids = fields.Many2many(
        comodel_name='muk_contacts_vcard.honorific',
        relation='partner_honorific_suffix_rel',
        column1='partner_id',
        column2='honorific_id',
        string='Honorific Suffixes',
        domain=[('position', '=', 'following')],
    )

    birthdate = fields.Date(
        string='Birthdate',
    )

    birthdate_day = fields.Integer(
        compute='_compute_birthdate_vals',
        string='Birthdate Day',
        readonly=True,
        store=True,
    )

    birthdate_month = fields.Integer(
        compute='_compute_birthdate_vals',
        string='Birthdate Month',
        readonly=True,
        store=True,
    )

    birthdate_placeholder = fields.Char(
        compute='_compute_birthdate_placeholder',
        string='Birthdate Placeholder',
    )

    birthday = fields.Char(
        compute='_compute_birthday',
        string='Birthday',
    )

    nickname = fields.Char(
        string='Nickname',
    )

    mobile = fields.Char(
        string='Phone (Mobile)',
    )

    email2 = fields.Char(
        string='Email (Private)',
    )

    phone2 = fields.Char(
        string='Phone (Private)',
    )

    vcard_uid = fields.Char(
        string='vCard UID',
        readonly=True,
        copy=False,
    )

    vcard_modified = fields.Datetime(
        compute='_compute_vcard_modified',
        string='vCard Modified',
        readonly=True,
        store=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _build_name(
        self,
        firstname: str | bool,
        middlename: str | bool,
        lastname: str | bool,
    ) -> str:
        """Join the name parts into a single space-separated string."""
        return ' '.join(value for value in (firstname, middlename, lastname) if value)

    @api.model
    def _split_name(
        self,
        name: str | bool,
        is_company: bool = False,
    ) -> tuple[str | bool, str | bool]:
        """Split a display name into ``(lastname, firstname)`` parts."""
        if is_company or not name:
            return name or False, False
        parts = name.split(' ')
        if len(parts) > 1:
            return ' '.join(parts[1:]), parts[0]
        return name, False

    def _fields_sync(self, values: dict) -> None:
        """Flush the recordset before syncing dependent address fields."""
        self.flush_recordset()
        return super()._fields_sync(values)

    def _get_complete_name(self) -> str:
        """Decorate the complete name with honorific shortcuts on request."""
        complete_name = super()._get_complete_name()
        if self.name and self.env.context.get('partner_display_name_show_honorific'):
            prefix = ' '.join(self.mapped('honorific_prefix_ids.shortcut'))
            suffix = ' '.join(self.mapped('honorific_suffix_ids.shortcut'))
            decorated = ' '.join(filter(None, [prefix, self.name, suffix]))
            complete_name = complete_name.replace(self.name, decorated, 1)
        return complete_name.strip()

    def _ensure_vcard_uid(self) -> str:
        """Assign and return a stable vCard UID, generating one if missing."""
        if not self.vcard_uid:
            self.sudo().vcard_uid = str(uuid.uuid4())
        return self.vcard_uid

    def _build_vcard(self) -> vobject.base.Component:
        """Enrich the base vCard with extra contact and address details."""
        vcard = super()._build_vcard()

        def get_vcard_content_element(name: str) -> vobject.base.ContentLine:
            elem = vcard.contents.get(name, False)
            return elem[0] if elem else vcard.add(name)

        fn = get_vcard_content_element('fn')
        fn.value = self.formatted_name
        n = get_vcard_content_element('n')
        n.value = vobject.vcard.Name(
            family=self.lastname or '',
            given=self.firstname or '',
            additional=self.middlename or '',
            prefix=' '.join(self.mapped('honorific_prefix_ids.shortcut')),
            suffix=' '.join(self.mapped('honorific_suffix_ids.shortcut')),
        )
        if self.street2:
            adr = get_vcard_content_element('adr')
            adr.value.extended = self.street2
        if self.lang:
            lang = vcard.add('lang')
            lang.value = self.lang.replace('_', '-')
        if self.tz:
            tz = vcard.add('tz')
            tz.value = self.tz
        if self.gender:
            gender = vcard.add('gender')
            gender.value = self.gender.upper()
        if self.birthdate:
            bday = vcard.add('bday')
            bday.value = self.birthdate.strftime('%Y%m%d')
        if self.nickname:
            nickname = vcard.add('nickname')
            nickname.value = self.nickname
        if self.email2:
            email = vcard.add('email')
            email.value = self.email2
            email.type_param = 'HOME'
        if self.mobile:
            tel = vcard.add('tel')
            tel.value = self.mobile
            tel.type_param = 'CELL'
        if self.phone2:
            tel = vcard.add('tel')
            tel.value = self.phone2
            tel.type_param = 'HOME'
        if self.category_id and self.category_id.has_access('read'):
            categories = vcard.add('categories')
            categories.value = self.mapped('category_id.name')
        if self.commercial_company_name and self.department:
            org = get_vcard_content_element('org')
            org.value = [
                self.commercial_company_name,
                self.department,
            ]
        if self.is_company and 'org' in vcard.contents:
            del vcard.contents['org']
        if self.role:
            role = vcard.add('role')
            role.value = self.role
        if self.comment:
            note = vcard.add('note')
            note.value = html2plaintext(self.comment)
        kind = vcard.add('kind')
        kind.value = 'org' if self.company_type == 'company' else 'individual'
        if self.child_ids:
            type_selection = dict(self._fields['type']._description_selection(self.env))
            extra_addresses = self.child_ids.filtered(
                lambda c: (
                    c.type in ('invoice', 'delivery', 'other')
                    and any(
                        c[f]
                        for f in (
                            'street',
                            'street2',
                            'city',
                            'zip',
                            'country_id',
                        )
                    )
                )
            )
            for idx, child in enumerate(extra_addresses, start=1):
                adr = vcard.add('adr', group=f'item{idx}')
                adr.value = vobject.vcard.Address(
                    street=child.street or '',
                    extended=child.street2 or '',
                    city=child.city or '',
                    region=child.state_id.name if child.state_id else '',
                    code=child.zip or '',
                    country=child.country_id.name if child.country_id else '',
                )
                adr.type_param = 'WORK'
                label = vcard.add('x-ablabel', group=f'item{idx}')
                label.value = (
                    child.name
                    if child.name and child.name != self.name
                    else type_selection.get(child.type, child.type)
                )
        uid = vcard.add('uid')
        uid.value = self._ensure_vcard_uid()
        rev = vcard.add('rev')
        modified = self.vcard_modified or fields.Datetime.now()
        rev.value = modified.strftime('%Y%m%dT%H%M%SZ')
        return vcard

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('firstname', 'middlename', 'lastname')
    def _compute_name(self) -> None:
        """Compose the display name from first, middle, and last name."""
        for record in self:
            record.name = self._build_name(
                record.firstname, record.middlename, record.lastname
            )

    def _inverse_name(self) -> None:
        """Split an edited display name back into first and last name."""
        for record in self.filtered(
            lambda r: r.name != self._build_name(r.firstname, r.middlename, r.lastname)
        ):
            lastname, firstname = self._split_name(
                (record.name or '').strip(), record.is_company
            )
            record.firstname = firstname
            record.middlename = False
            record.lastname = lastname

    @api.depends(
        'type',
        'name',
        'is_company',
        'company_name',
        'parent_id.name',
        'commercial_company_name',
        'honorific_prefix_ids',
        'honorific_suffix_ids',
        'honorific_prefix_ids.name',
        'honorific_suffix_ids.name',
        'honorific_prefix_ids.shortcut',
        'honorific_suffix_ids.shortcut',
    )
    def _compute_formatted_name(self) -> None:
        """Build the formatted name, optionally including honorifics."""
        for record in self:
            record_ctx = (
                record.with_context(
                    {
                        'partner_display_name_hide_company': True,
                        'partner_display_name_show_honorific': True,
                    }
                )
                if record.name and not record.is_company
                else record.with_context({})
            )
            record.formatted_name = record_ctx._get_complete_name()

    @api.depends('birthdate')
    def _compute_birthdate_vals(self) -> None:
        """Derive the birthdate day and month numbers."""
        self.birthdate_day = False
        self.birthdate_month = False
        for record in self.filtered('birthdate'):
            record.birthdate_day = record.birthdate.day
            record.birthdate_month = record.birthdate.month

    def _compute_birthdate_placeholder(self) -> None:
        """Set a localized example date as the birthdate placeholder."""
        self.birthdate_placeholder = format_date(self.env, fields.Date.today())

    @api.depends('birthdate')
    def _compute_birthday(self) -> None:
        """Format the birthdate as a short month-and-day label."""
        self.birthday = False
        for record in self.filtered('birthdate'):
            record.birthday = format_date(
                self.env, record.birthdate, date_format='MMM d'
            )

    @api.depends(
        'birthdate',
        'category_id.name',
        'city',
        'commercial_company_name',
        'comment',
        'country_id.name',
        'email',
        'email2',
        'firstname',
        'function',
        'gender',
        'honorific_prefix_ids',
        'honorific_suffix_ids',
        'honorific_prefix_ids.shortcut',
        'honorific_suffix_ids.shortcut',
        'image_1920',
        'lang',
        'lastname',
        'middlename',
        'name',
        'nickname',
        'parent_id',
        'child_ids',
        'child_ids.name',
        'child_ids.type',
        'child_ids.street',
        'child_ids.street2',
        'child_ids.city',
        'child_ids.zip',
        'child_ids.state_id',
        'child_ids.country_id',
        'phone',
        'phone2',
        'mobile',
        'role',
        'state_id.name',
        'street',
        'tz',
        'website',
        'zip',
    )
    def _compute_vcard_modified(self) -> None:
        """Stamp the vCard modification time whenever exported data changes."""
        self.vcard_modified = fields.Datetime.now()
