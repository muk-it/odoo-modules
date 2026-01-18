import uuid

from odoo import models, fields, api, _
from odoo.tools import format_date, html2plaintext
from odoo.exceptions import UserError

try:
    import vobject
except ImportError:
    vobject = None


class Partner(models.Model):

    _inherit = 'res.partner'
    _rec_names_search = [
        'complete_name',
        'email',
        'ref',
        'vat',
        'company_registry',
        'contact_number'
    ]
    
    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------
    
    name = fields.Char(
        compute='_compute_name',
        inverse='_inverse_name',
        readonly=False,
        store=True,
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
        string="Formatted Name",
        store=True, 
        readonly=True,
        index=True
    )

    department = fields.Char(
        string="Department",
    )

    role = fields.Char(
        string="Job Role",
    )

    gender = fields.Selection(
        selection=[
            ('m', 'Male'),
            ('f', 'Female'),
            ('o', 'Other')
        ],
        string="Gender",
    )

    honorific_prefix_ids = fields.Many2many(
        comodel_name='muk_contacts_vcard.honorific',
        relation='partner_honorific_rel',
        column1='partner_id',
        column2='honorific_id',
        string='Honorific Prefixes',
        domain=[('position', '=', 'preceding')],
    )
    
    honorific_suffix_ids = fields.Many2many(
        comodel_name='muk_contacts_vcard.honorific',
        relation='partner_honorific_rel',
        column1='partner_id',
        column2='honorific_id',
        string='Honorific Suffixes',
        domain=[('position', '=', 'following')],
    )

    birthdate = fields.Date(
        string="Birthdate"
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
        string="Birthdate Placeholder"
    )

    birthday = fields.Char(
        compute='_compute_birthday',
        string="Birthday"
    )

    nickname = fields.Char(
        string="Nickname"
    )

    email2 = fields.Char(
        string="Email (Private)"
    )

    phone2 = fields.Char(
        string="Phone (Private)"
    )

    vcard_uid = fields.Char(
        string="vCard UID",
        readonly=True,
        copy=False,
    )

    vcard_modified = fields.Datetime(
        compute='_compute_vcard_modified',
        string="vCard Modified",
        readonly=True,
        store=True,
        copy=False,
    )

    #----------------------------------------------------------
    # Helper
    #----------------------------------------------------------

    @api.model
    def _build_name(self, firstname, middlename, lastname):
        return ' '.join(
            value for value in (firstname, middlename, lastname)
            if value
        )

    @api.model
    def _split_name(self, name, is_company=False):
        for record in self:
            if is_company or not name:
                return name or False, False
            parts = name.split(' ')
            if len(parts) > 1:
                return ' '.join(parts[1:]), parts[0]
            return name, False

    def _get_complete_name(self):
        complete_name = super()._get_complete_name()
        if self.name and self.env.context.get('partner_display_name_show_honorific'):
            prefix = ' '.join(self.mapped('honorific_prefix_ids.shortcut'))
            suffix = ' '.join(self.mapped('honorific_suffix_ids.shortcut'))
            decorated = ' '.join(filter(None, [prefix, self.name, suffix]))
            complete_name = complete_name.replace(self.name, decorated, 1)
        return complete_name.strip()
        
    def _ensure_vcard_uid(self):
        if not self.vcard_uid:
            self.vcard_uid = str(uuid.uuid4())
        return self.vcard_uid

    def _build_vcard(self):
        vcard = super()._build_vcard()

        def get_vcard_content_element(name):
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
        if self.phone2:
            tel = vcard.add('tel')
            tel.value = self.phone2
            tel.type_param = 'HOME'
        if self.category_id:
            categories = vcard.add('categories')
            categories.value = self.mapped('category_id.name')
        if self.commercial_company_name and self.department:
            org = get_vcard_content_element('org')
            org.value = [
                self.commercial_company_name, 
                self.department
            ]
        if self.role:
            role = vcard.add('role')
            role.value = self.role
        if self.comment:
            note = vcard.add('note')
            note.value = html2plaintext(self.comment)
        kind = vcard.add('kind')
        kind.value = (
            'org' 
            if self.company_type == 'company' 
            else 'individual'
        )
        uid = vcard.add('uid')
        uid.value = self._ensure_vcard_uid()
        rev = vcard.add('rev')
        rev.value = self.vcard_modified.strftime('%Y%m%dT%H%M%SZ')
        return vcard

    #----------------------------------------------------------
    # Compute
    #----------------------------------------------------------

    @api.depends('firstname', 'middlename', 'lastname')
    def _compute_name(self):
        for record in self:
            record.name = self._build_name(
                record.firstname, record.middlename, record.lastname
            )

    def _inverse_name(self):
        for record in self.filtered(
            lambda r: r.name != self._build_name(
                r.firstname, r.middlename, r.lastname
            )
        ):
            lastname, firstname = self._split_name(
                (record.name or '').strip(), record.is_company
            )
            record.write({
                'firstname': firstname,
                'middlename': False,
                'lastname': lastname,
            })

    @api.depends(
        'type',
        'name',
        'is_company', 
        'honorific_prefix_ids', 
        'honorific_suffix_ids', 
        'honorific_prefix_ids.name',
        'honorific_suffix_ids.name',
    )
    def _compute_formatted_name(self):
        for record in self:
            record_ctx = (
                record.with_context({
                    'partner_display_name_hide_company': True,
                    'partner_display_name_show_honorific': True,
                })
                if record.name and not record.is_company
                else record.with_context({})
            )
            record.formatted_name = record_ctx._get_complete_name()

    @api.depends('birthdate')
    def _compute_birthdate_vals(self):
        self.birthdate_day = False
        self.birthdate_month = False
        for record in self.filtered('birthdate'):
            record.birthdate_day = record.birthdate.day
            record.birthdate_month = record.birthdate.month

    def _compute_birthdate_placeholder(self):
        self.birthdate_placeholder = format_date(
            self.env, fields.Date.today()
        )

    @api.depends('birthdate')
    def _compute_birthday(self):
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
        'image_1920',
        'lang',
        'lastname',
        'middlename',
        'name',
        'nickname',
        'parent_id',
        'phone',
        'phone2',
        'role',
        'state_id.name',
        'street',
        'tz',
        'website',
        'zip',
    )
    def _compute_vcard_modified(self):
        self.vcard_modified = fields.Datetime.now()
