import logging
import secrets

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.muk_ai.providers import REGISTRY

_logger = logging.getLogger(__name__)


class AgentidooOnboarding(models.TransientModel):

    _name = 'muk_ai_agentidoo.onboarding'
    _description = "Agentidoo Onboarding"

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    @api.model
    def _default_api_url(self):
        impl_cls = REGISTRY.get('agentidoo')
        return impl_cls.default_url if impl_cls else 'https://api.agentidoo.com'

    @api.model
    def _default_odoo_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '',
        )

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection=[
            ('intro', "Welcome"),
            ('api_key', "API Key"),
            ('acting_user', "Acting User"),
            ('register', "Register Odoo"),
            ('done', "Done"),
        ],
        required=True,
        default='intro',
    )

    api_url = fields.Char(
        string="API URL",
        required=True,
        default=lambda self: self._default_api_url(),
    )

    api_key = fields.Char(
        string="API Key",
    )

    acting_user_mode = fields.Selection(
        selection=[
            ('self', "Use my own account"),
            ('existing', "Pick another internal user"),
            ('create', "Create a dedicated agentidoo-bot user (+1 paid seat)"),
        ],
        string="Acting User Mode",
        required=True,
        default='self',
    )

    acting_user_id = fields.Many2one(
        comodel_name='res.users',
        string="Acting User",
        domain=[('share', '=', False), ('active', '=', True)],
    )

    new_user_login = fields.Char(
        string="New User Login",
        default='agentidoo-bot',
    )

    new_user_name = fields.Char(
        string="New User Name",
        default="Agentidoo Bot",
    )

    acting_user_password = fields.Char(
        string="Acting User Password",
        help="Sent once to Agentidoo (encrypted in LCP Secrets). Never persisted in Odoo.",
    )

    odoo_url = fields.Char(
        string="Public Odoo URL",
        required=True,
        default=lambda self: self._default_odoo_url(),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _agentidoo_provider(self):
        return self.env.ref(
            'muk_ai_agentidoo.provider_agentidoo',
            raise_if_not_found=False,
        )

    def _verify_api_key(self):
        if not self.api_key:
            raise ValidationError(_("API key is required."))
        try:
            response = requests.get(
                f'{self.api_url.rstrip("/")}/api/v1/me',
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=15,
            )
        except requests.RequestException as error:
            raise UserError(_(
                "Could not reach Agentidoo at %(url)s: %(error)s",
                url=self.api_url, error=error,
            )) from error
        if response.status_code == 401:
            raise UserError(_("Agentidoo rejected the API key (401)."))
        if not response.ok:
            raise UserError(_(
                "Agentidoo health-check failed: HTTP %(code)s — %(body)s",
                code=response.status_code, body=response.text[:200],
            ))

    def _resolve_acting_user(self):
        if self.acting_user_mode == 'self':
            return self.env.user
        if self.acting_user_mode == 'existing':
            if not self.acting_user_id:
                raise ValidationError(_(
                    "Select the user Aimee should act as.",
                ))
            return self.acting_user_id
        return self._create_bot_user()

    def _create_bot_user(self):
        login = (self.new_user_login or 'agentidoo-bot').strip()
        if not login:
            raise ValidationError(_("New user login is required."))
        existing = self.env['res.users'].sudo().search(
            [('login', '=', login)], limit=1,
        )
        if existing:
            raise ValidationError(_(
                "User %(login)s already exists. Pick a different login or reuse it.",
                login=login,
            ))
        password = secrets.token_urlsafe(24)
        user = self.env['res.users'].sudo().create({
            'login': login,
            'name': (self.new_user_name or 'Agentidoo Bot').strip(),
            'password': password,
            'groups_id': [(4, self.env.ref('base.group_user').id)],
        })
        self.acting_user_password = password
        return user

    def _register_odoo_instance(self, user, password):
        api_url = self.api_url.rstrip('/')
        provider = self._agentidoo_provider()
        api_key = provider.sudo().api_key if provider else ''
        payload = {
            'display_name': self.env.company.name,
            'url': self.odoo_url,
            'db': self.env.cr.dbname,
            'username': user.login,
            'password': password,
        }
        try:
            response = requests.post(
                f'{api_url}/api/v1/odoo',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=30,
            )
        except requests.RequestException as error:
            raise UserError(_(
                "Agentidoo registration failed: %(error)s", error=error,
            )) from error
        if response.status_code == 401:
            raise UserError(_(
                "Agentidoo rejected the API key (401) during registration.",
            ))
        if response.status_code == 402:
            raise UserError(_(
                "Agentidoo account is out of credits (402). Visit %(url)s/dashboard/billing.",
                url=api_url,
            ))
        if not response.ok:
            raise UserError(_(
                "Agentidoo registration failed: HTTP %(code)s — %(body)s",
                code=response.status_code, body=response.text[:200],
            ))

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_signup(self):
        return {
            'type': 'ir.actions.act_url',
            'url': f'{self.api_url.rstrip("/")}/signup',
            'target': 'new',
        }

    def action_next(self):
        handlers = {
            'intro': self._advance_to_api_key,
            'api_key': self._advance_to_acting_user,
            'acting_user': self._advance_to_register,
            'register': self._advance_to_done,
        }
        handler = handlers.get(self.state)
        if handler is None:
            return self._reopen()
        handler()
        return self._reopen()

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    def action_skip_register(self):
        if self.state != 'acting_user':
            return self._reopen()
        user = self._resolve_acting_user()
        self.acting_user_id = user.id
        provider = self._agentidoo_provider().sudo()
        if provider:
            provider.write({
                'agentidoo_acting_user_id': user.id,
                'agentidoo_session_registered': False,
            })
            self.env.company.sudo().default_ai_provider_id = provider
        self.state = 'done'
        return self._reopen()

    def action_open_chat(self):
        return self.env.ref('muk_ai.action_ai_chat').read()[0]

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _advance_to_api_key(self):
        self.state = 'api_key'

    def _advance_to_acting_user(self):
        self._verify_api_key()
        provider = self._agentidoo_provider().sudo()
        if provider:
            provider.write({'api_key': self.api_key})
        self.state = 'acting_user'

    def _advance_to_register(self):
        user = self._resolve_acting_user()
        self.acting_user_id = user.id
        self.state = 'register'

    def _advance_to_done(self):
        if not self.acting_user_id:
            raise ValidationError(_("Acting user is not set."))
        if not self.acting_user_password:
            raise ValidationError(_(
                "Acting user password is required to register the Odoo instance.",
            ))
        self._register_odoo_instance(
            self.acting_user_id, self.acting_user_password,
        )
        provider = self._agentidoo_provider().sudo()
        if provider:
            provider.write({
                'agentidoo_acting_user_id': self.acting_user_id.id,
                'agentidoo_session_registered': True,
            })
            self.env.company.sudo().default_ai_provider_id = provider
        self.acting_user_password = False
        self.state = 'done'
