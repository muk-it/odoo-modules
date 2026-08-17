from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_website_cookies_consent.tools.constants import (
    OBSERVATION_BATCH_LIMIT,
    OBSERVATION_STORAGE_TYPES,
    OBSERVATION_TYPES,
    UNCLASSIFIED_CODE,
)


class CookieObservation(models.Model):
    """A cookie, storage key or host seen on the site but never declared.

    Outside the registry mixin on purpose: a capture must not change the
    registry fingerprint, or an editor loading a page would re-ask the whole
    audience for consent.
    """

    _name = 'muk_website_cookies_consent.observation'
    _description = 'Captured Cookie'
    _order = 'state, last_seen desc, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Key',
        help='The cookie name, storage key or host as the browser reported it.',
        required=True,
        index=True,
    )

    storage_type = fields.Selection(
        selection=list(OBSERVATION_TYPES),
        string='Type',
        required=True,
        default='http',
    )

    sample_url = fields.Char(
        string='Seen On',
        help='A page it was found on, to help work out what sets it.',
    )

    hit_count = fields.Integer(
        string='Times Seen',
        required=True,
        default=1,
    )

    last_seen = fields.Datetime(
        string='Last Seen',
        required=True,
        default=fields.Datetime.now,
    )

    state = fields.Selection(
        selection=[
            ('new', 'To Review'),
            ('declared', 'Declared'),
            ('ignored', 'Ignored'),
        ],
        string='Status',
        required=True,
        default='new',
    )

    cookie_id = fields.Many2one(
        comodel_name='muk_website_cookies_consent.cookie',
        string='Declaration',
        readonly=True,
        ondelete='set null',
    )

    service_id = fields.Many2one(
        comodel_name='muk_website_cookies_consent.service',
        string='Service',
        readonly=True,
        ondelete='set null',
    )

    website_id = fields.Many2one(
        comodel_name='website',
        string='Website',
        required=True,
        ondelete='cascade',
    )

    _sql_constraints = [
        (
            'key_uniq',
            'unique (name, storage_type, website_id)',
            'This key has already been captured for this website.',
        ),
    ]

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_unclassified_category(self, website: models.Model) -> models.Model:
        """Return the bucket a capture is declared into."""
        return self.env['muk_website_cookies_consent.category'].search(
            [
                ('code', '=', UNCLASSIFIED_CODE),
                ('website_id', 'in', [website.id, False]),
            ],
            limit=1,
        )

    @api.model
    def _is_declared(self, website: models.Model, name: str, storage_type: str) -> bool:
        """Return whether the registry already covers a key.

        Decided here rather than in the browser: only the registry knows that a
        declaration's pattern already covers the name.
        """
        if storage_type == 'host':
            return bool(website._find_cookie_service(f'https://{name}/'))
        declarations = website._get_cookie_declarations()
        if name in declarations.mapped('name'):
            return True
        return any(
            declaration._matches_name(name)
            for declaration in declarations
            if declaration.pattern
        )

    @api.model
    def _record_keys(self, website: models.Model, keys: list) -> models.Model:
        """File the reported keys the registry does not cover.

        A key that has since been declared drops any capture still waiting for
        it: the row asserts that nothing covers the key, so once something
        does, leaving it would put a false entry on the review list.

        :param keys: dicts of name, type and url, as sent by the browser
        :return: the captures created or touched
        """
        valid_types = dict(OBSERVATION_TYPES)
        found = self.browse()
        for key in keys[:OBSERVATION_BATCH_LIMIT]:
            if not isinstance(key, dict):
                continue
            name = str(key.get('name') or '').strip()[:256]
            storage_type = str(key.get('type') or '')
            if not name or storage_type not in valid_types:
                continue
            if self._is_declared(website, name, storage_type):
                self._drop_settled(website, name, storage_type)
                continue
            found |= self._touch(website, name, storage_type, key.get('url'))
        return found

    @api.model
    def _drop_settled(
        self, website: models.Model, name: str, storage_type: str
    ) -> None:
        """Remove a capture the registry has caught up with.

        Only one still waiting to be reviewed: a capture that was declared or
        ignored records a decision somebody took, which stays.
        """
        self.search(
            [
                ('name', '=', name),
                ('storage_type', '=', storage_type),
                ('website_id', '=', website.id),
                ('state', '=', 'new'),
            ]
        ).unlink()

    @api.model
    def _touch(
        self,
        website: models.Model,
        name: str,
        storage_type: str,
        url: str | None,
    ) -> models.Model:
        """Create a capture, or count another sighting of a known one."""
        existing = self.search(
            [
                ('name', '=', name),
                ('storage_type', '=', storage_type),
                ('website_id', '=', website.id),
            ],
            limit=1,
        )
        if existing:
            existing.write(
                {
                    'hit_count': existing.hit_count + 1,
                    'last_seen': fields.Datetime.now(),
                }
            )
            return existing
        return self.create(
            {
                'name': name,
                'storage_type': storage_type,
                'sample_url': str(url or '')[:256] or False,
                'website_id': website.id,
            }
        )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_declare(self) -> dict:
        """Turn the captures into unclassified registry entries and open them.

        :raise UserError: when there is no unclassified purpose to file into
        """
        cookies = self.env['muk_website_cookies_consent.cookie'].browse()
        services = self.env['muk_website_cookies_consent.service'].browse()
        for observation in self.filtered(lambda o: o.state == 'new'):
            category = self._get_unclassified_category(observation.website_id)
            if not category:
                raise UserError(
                    _(
                        'There is no "Unclassified" purpose to file "%(name)s" '
                        'into. Recreate it, or classify the key by hand.',
                        name=observation.name,
                    )
                )
            if observation.storage_type == 'host':
                service = observation._create_service(category)
                services |= service
                observation.write({'service_id': service.id, 'state': 'declared'})
            else:
                cookie = observation._create_declaration(category)
                cookies |= cookie
                observation.write({'cookie_id': cookie.id, 'state': 'declared'})
        if services and not cookies:
            return self._get_record_action(
                'muk_website_cookies_consent.action_cookie_service', services
            )
        return self._get_record_action(
            'muk_website_cookies_consent.action_cookie', cookies
        )

    def action_ignore(self) -> None:
        """Mark the captures as reviewed and not worth declaring."""
        self.write({'state': 'ignored'})

    def action_reopen(self) -> None:
        """Put the captures back on the review list."""
        self.filtered(lambda o: not o.cookie_id and not o.service_id).write(
            {'state': 'new'}
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _create_declaration(self, category: models.Model) -> models.Model:
        """Return a new cookie declaration for this capture."""
        return self.env['muk_website_cookies_consent.cookie'].create(
            {
                'name': self.name,
                'category_id': category.id,
                'storage_type': (
                    self.storage_type
                    if self.storage_type in OBSERVATION_STORAGE_TYPES
                    else 'http'
                ),
                'description': _('Captured automatically. Not yet reviewed.'),
            }
        )

    def _create_service(self, category: models.Model) -> models.Model:
        """Return a new service claiming the host of this capture."""
        return self.env['muk_website_cookies_consent.service'].create(
            {
                'name': self.name,
                'technical_name': self._get_technical_name(),
                'category_id': category.id,
                'domains': self.name,
            }
        )

    def _get_technical_name(self) -> str:
        """Return a free identifier derived from the captured host."""
        base = ''.join(
            char if char.isalnum() else '_' for char in (self.name or '').lower()
        ).strip('_')
        base = base or 'service'
        service = self.env['muk_website_cookies_consent.service']
        candidate, suffix = base, 1
        while service.search_count([('technical_name', '=', candidate)]):
            suffix += 1
            candidate = f'{base}_{suffix}'
        return candidate

    @api.model
    def _get_record_action(self, xml_id: str, records: models.Model) -> dict:
        """Return the action of ``xml_id`` narrowed to the given records."""
        action = self.env['ir.actions.act_window']._for_xml_id(xml_id)
        action['domain'] = [('id', 'in', records.ids)]
        return action
