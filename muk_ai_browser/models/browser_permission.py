from __future__ import annotations

from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class BrowserPermission(models.Model):
    """What the assistant may do on a site in the user's browser."""

    _name = 'muk_ai_browser.permission'
    _description = 'Browser Site Permission'
    _order = 'user_id, site'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        help='Leave empty to apply the rule to everyone.',
        default=lambda self: self.env.user,
        index=True,
        ondelete='cascade',
    )

    site = fields.Char(
        string='Site',
        help='An origin like https://shop.example.com or a pattern like *.example.com.',
        required=True,
    )

    mode = fields.Selection(
        selection=[
            ('allow', 'Allow'),
            ('ask', 'Ask'),
            ('block', 'Block'),
        ],
        string='Mode',
        required=True,
        default='ask',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _normalized(self, vals: dict) -> dict:
        """Return the values with the site in lower case and without a final slash."""
        if vals.get('site'):
            return {**vals, 'site': vals['site'].strip().lower().rstrip('/')}
        return vals

    def _matches(self, origin: str) -> bool:
        """Return whether the rule's site covers ``origin``."""
        if self.site == origin:
            return True
        host = urlsplit(origin).hostname or ''
        suffix = self.site.removeprefix('*.')
        return self.site.startswith('*.') and (
            host == suffix or host.endswith(f'.{suffix}')
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mode_for(self, user: models.BaseModel, origin: str) -> str:
        """Return the mode of the most specific rule for a user on an origin.

        A block for everyone always wins; otherwise the user's own rules win over
        the rules for everyone, an exact origin over a pattern, and without a rule
        the configured default applies.
        """
        rules = self.sudo().search([('user_id', 'in', [False, user.id])])
        matching = rules.filtered(lambda rule: origin and rule._matches(origin))
        if any(not rule.user_id and rule.mode == 'block' for rule in matching):
            return 'block'
        if matching:
            return min(
                matching,
                key=lambda rule: (not rule.user_id, rule.site != origin),
            ).mode
        return (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_ai_browser.default_mode', 'ask')
        )

    @api.model
    def _grant(self, user: models.BaseModel, origin: str) -> None:
        """Allow the assistant on ``origin`` for ``user``."""
        rule = self.sudo().search(
            [('user_id', '=', user.id), ('site', '=', origin)],
            limit=1,
        )
        if rule:
            rule.mode = 'allow'
        else:
            self.sudo().create({'user_id': user.id, 'site': origin, 'mode': 'allow'})

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('site')
    def _check_site(self) -> None:
        """Accept only an origin or a ``*.domain`` pattern.

        :raise ValidationError: when the site is neither
        """
        session = self.env['muk_ai.session']
        for rule in self:
            if rule.site.startswith('*.') and '/' not in rule.site:
                continue
            if session._browser_origin_of(rule.site) != rule.site:
                raise ValidationError(
                    self.env._(
                        '%s is not a site: write https://example.com or *.example.com.',
                        rule.site,
                    )
                )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> BrowserPermission:
        """Store sites in lower case."""
        return super().create([self._normalized(vals) for vals in vals_list])

    def write(self, vals: dict) -> bool:
        """Store sites in lower case."""
        return super().write(self._normalized(vals))
