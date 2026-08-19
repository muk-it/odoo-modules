from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv.expression import AND, normalize_domain
from odoo.tools.safe_eval import safe_eval


class AISpace(models.Model):
    """Group chat sessions under a named space.

    A personal space belongs to a user and collects the chats they file into
    it. A system space has no owner, is visible to everyone, and derives its
    chats from a stored domain instead.
    """

    _name = 'muk_ai.space'
    _description = 'AI Space'
    _order = 'sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    icon = fields.Char(
        string='Icon',
        help='Font Awesome class the sidebar draws next to the space name.',
        required=True,
        default='fa-folder-o',
    )

    agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='Default Agent',
        help='Agent preselected for chats started inside this space.',
        ondelete='set null',
    )

    instructions = fields.Text(
        string='Instructions',
        help=(
            'How the assistant should work in this space: context to keep in '
            'mind, wording to prefer, steps to follow. The text is handed to '
            'every chat the space holds.'
        ),
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Owner',
        help=(
            'Owner of a personal space. Leave empty for a system space, '
            'which every user sees and which collects its chats through '
            'its domain.'
        ),
        default=lambda self: self.env.user,
        index=True,
        ondelete='cascade',
    )

    domain = fields.Char(
        string='Domain',
        help=(
            'Session domain collecting the chats of a system space. Leave '
            'empty for a personal space, whose chats are filed by hand.'
        ),
    )

    retention_mode = fields.Selection(
        selection=[
            ('default', 'Follow the Default'),
            ('days', 'Keep for a While'),
            ('forever', 'Keep Forever'),
        ],
        string='Retention',
        help=(
            'What becomes of the finished chats in this space. They follow '
            'the general setting unless this space says otherwise.'
        ),
        required=True,
        default='default',
    )

    retention_days = fields.Integer(
        string='Retention Days',
        help=(
            'Days a finished chat in this space is kept before the scheduled '
            'cleanup deletes it.'
        ),
    )

    session_count = fields.Integer(
        compute='_compute_session_count',
        string='Chats',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _parsed_domain(self) -> list:
        """Return the stored domain with ``uid`` resolved to the reader.

        A space that collects what was shared with somebody has to name that
        somebody, and the domain is stored once for everyone, so it is read
        per user rather than taken literally.
        """
        return safe_eval(self.domain, {'uid': self.env.uid})

    def _session_domain(self) -> list:
        """Return the domain selecting the sessions of this space.

        Filing a chat by hand overrules the domain that would collect it, but
        only for whoever filed it: a chat somebody shared and then filed into
        a space of their own stays listed for the people they shared it with,
        who cannot see that space at all.
        """
        if not self.domain:
            return [('space_id', '=', self.id)]
        return [*self._parsed_domain(), '!', ('space_id.user_id', '=', self.env.uid)]

    def _sidebar_spaces(self) -> AISpace:
        """Return the spaces of the current user plus the system ones."""
        return self.search(
            ['|', ('user_id', '=', self.env.uid), ('user_id', '=', False)]
        )

    @api.model
    def _unclaimed_session_domain(self) -> list:
        """Return the domain of the chats no space collects.

        A space is a filter rather than a folder, so what one collects is
        listed there instead of a second time among the loose chats.
        """
        domain = [('space_id', '=', False)]
        for space in self.search([('domain', '!=', False)]):
            claimed = normalize_domain(space._parsed_domain())
            domain = AND([domain, ['!', *claimed]])
        return domain

    def _count_by_space(self, session_ids: list[int] | None = None) -> dict[int, int]:
        """Count the sessions each space of this set collects.

        Personal spaces share one grouped query; every system space costs a
        count of its own, as each carries a different domain.

        :param session_ids: restrict the count to these sessions, all of them
            when omitted
        """
        sessions = self.env['muk_ai.session']
        scope = [('id', 'in', session_ids)] if session_ids is not None else []
        personal = self.filtered(lambda space: not space.domain)
        counts = {
            space.id: count
            for space, count in sessions._read_group(
                domain=[*scope, ('space_id', 'in', personal.ids)],
                groupby=['space_id'],
                aggregates=['__count'],
            )
        }
        for space in self - personal:
            if count := sessions.search_count([*scope, *space._session_domain()]):
                counts[space.id] = count
        return counts

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_sessions(self) -> dict:
        """Open the chats this space collects in the session views.

        The menu context is dropped, as its default filter would hide the
        chats of every other user.
        """
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('muk_ai.action_ai_session')
        action['domain'] = self._session_domain()
        action['context'] = {}
        return action

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def count_sessions(self, session_ids: list[int]) -> dict[str, int]:
        """Map each visible space to how many of ``session_ids`` it holds.

        :param session_ids: sessions to sort, already scoped to their owner
        :return: space id as a string, the form the client indexes by
        """
        if not session_ids:
            return {}
        counts = self._sidebar_spaces()._count_by_space(session_ids)
        return {str(space_id): count for space_id, count in counts.items()}

    @api.model
    def fetch_general_domain(self) -> list:
        """Return the domain of the chats the sidebar lists outside any space."""
        return list(self._unclaimed_session_domain())

    @api.model
    def fetch_spaces(self) -> list[dict]:
        """Return the spaces the sidebar shows the current user.

        Unread counts are absent on purpose: they ride with the notification
        badge, which is pushed whenever they change.
        """
        return [
            {
                'id': space.id,
                'name': space.name,
                'icon': space.icon,
                'agent_id': space.agent_id.id,
                'agent_name': space.agent_id.display_name or '',
                'instructions': space.instructions or '',
                'system': bool(space.domain),
                'session_domain': space._session_domain(),
            }
            for space in self._sidebar_spaces()
        ]

    @api.model
    def reorder(self, space_ids: list[int]) -> bool:
        """Store the given order on the spaces, first id first."""
        for index, space in enumerate(self.browse(space_ids).exists(), start=1):
            space.sequence = index * 10
        return True

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_session_count(self) -> None:
        """Count the sessions each space collects."""
        counts = self.filtered('id')._count_by_space()
        for record in self:
            record.session_count = counts.get(record.id, 0)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('user_id', 'domain')
    def _check_owner(self) -> None:
        """Keep a personal space owned by its user and free of a domain.

        Constraints run sudoed, so the acting user is read off ``env.user``
        rather than through ``env.is_admin()``, which would answer yes for
        everybody and wave every write through.
        """
        if self.env.user._is_system():
            return
        for record in self:
            if record.user_id != self.env.user or record.domain:
                raise ValidationError(
                    _(
                        'The space "%s" must belong to you and cannot collect '
                        'chats through a domain.',
                        record.name,
                    )
                )

    @api.constrains('user_id', 'domain')
    def _check_scope(self) -> None:
        """Refuse a space that collects nothing.

        Without an owner to file into it and without a domain to derive from,
        the space is listed for everyone yet takes no chat at all.
        """
        for record in self:
            if not record.user_id and not record.domain:
                raise ValidationError(
                    _(
                        'The space "%s" must either belong to a user or collect '
                        'its chats through a domain.',
                        record.name,
                    )
                )

    @api.constrains('instructions', 'domain')
    def _check_instructions(self) -> None:
        """Keep instructions on personal spaces only.

        A system space derives its chats from a domain, so it holds the chats
        of everybody, filed there by nobody, and instructions stored on one
        would reach chats their owners never handed them to.
        """
        for record in self:
            if record.instructions and record.domain:
                raise ValidationError(
                    _(
                        'The system space "%s" cannot carry instructions.',
                        record.name,
                    )
                )

    @api.constrains('domain')
    def _check_domain(self) -> None:
        """Reject a domain the session model cannot evaluate."""
        sessions = self.env['muk_ai.session']
        for record in self.filtered('domain'):
            try:
                parsed = record._parsed_domain()
                reason = (
                    None if isinstance(parsed, list) else 'not a list of conditions'
                )
                if reason is None:
                    sessions._where_calc(parsed)
            except (SyntaxError, TypeError, ValueError, KeyError, NameError) as error:
                reason = error
            if reason:
                raise ValidationError(
                    _(
                        'The domain of "%(name)s" is not a valid session domain: %(error)s',
                        name=record.name,
                        error=reason,
                    )
                )

    @api.constrains('retention_mode', 'retention_days')
    def _check_retention_days(self) -> None:
        """Require a length from a space that keeps its chats for a while.

        :raise ValidationError: when the mode asks for days and none are given
        """
        for record in self:
            if record.retention_mode == 'days' and record.retention_days <= 0:
                raise ValidationError(
                    _(
                        'Say how many days "%(name)s" keeps its chats for.',
                        name=record.name,
                    )
                )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Release the chats a space can no longer hold after a change."""
        result = super().write(vals)
        if 'user_id' in vals or 'domain' in vals:
            filed = (
                self.env['muk_ai.session'].sudo().search([('space_id', 'in', self.ids)])
            )
            filed.filtered(
                lambda session: (
                    session.space_id.domain
                    or session.space_id.user_id != session.user_id
                )
            ).space_id = False
        return result
