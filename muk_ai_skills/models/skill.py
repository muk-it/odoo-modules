from __future__ import annotations

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Skill(models.Model):
    """Store a reusable AI skill with a body, description and resources."""

    _name = 'muk_ai.skill'
    _description = 'AI Skill'
    _inherit = ['muk_ai.revision.mixin', 'muk_ai.prompt.mixin']
    _order = 'sequence, name, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    display_name = fields.Char(
        compute='_compute_display_name',
        store=False,
    )

    name = fields.Char(
        string='Technical Name',
        help=(
            'Lowercase technical identifier used in the slash command '
            'and in the LLM-facing discovery list. Must match '
            '[a-z][a-z0-9_]*.'
        ),
        required=True,
        index=True,
        copy=False,
    )

    label = fields.Char(
        string='Label',
        help='Human-readable label shown in lists and the chat menu.',
        translate=True,
    )

    icon = fields.Char(
        string='Icon',
        help=(
            'Font Awesome class shown next to the skill in the chat '
            'skills panel, e.g. "fa-calendar-plus-o".'
        ),
        default='fa-bolt',
    )

    skill_type = fields.Selection(
        selection=[
            ('chat', 'Chat'),
        ],
        string='Type',
        help=(
            'Where the skill is offered. Only chat skills are listed to the '
            'language model and invoked by name; every other surface adds its '
            'own type and offers them for the user to pick.'
        ),
        required=True,
        default='chat',
        index=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        copy=False,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    owner_id = fields.Many2one(
        comodel_name='res.users',
        string='Owner',
        help=(
            'User who owns the skill. Only the owner or an '
            'administrator can edit or delete it.'
        ),
        required=True,
        default=lambda self: self.env.user,
        index=True,
        copy=False,
    )

    user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='muk_ai_skill_res_users_rel',
        column1='skill_id',
        column2='user_id',
        string='Shared With',
        help=(
            'Users the skill is shared with. If empty, the skill is '
            'shared with all users. New skills default to being '
            'private to their owner. Scheduled and automated agent '
            'sessions run as their configured user and only see the '
            'skills visible to that user.'
        ),
        default=lambda self: self._default_user_ids(),
    )

    description = fields.Text(
        string='Description',
        help=(
            'One-line description shown to the LLM in the system '
            'prompt addendum so it can decide when to invoke the skill.'
        ),
        required=True,
        translate=True,
    )

    body = fields.Text(
        string='Body',
        help=(
            'Markdown body returned when the skill is invoked. '
            'Optional: a manifest-only skill may rely solely on its '
            'attached resources.'
        ),
        translate=True,
    )

    agent_ids = fields.Many2many(
        comodel_name='muk_ai.agent',
        relation='muk_ai_skill_agent_rel',
        column1='skill_id',
        column2='agent_id',
        string='Agents',
        help=(
            'Agents that can see this skill. Leave empty to make the '
            'skill visible to every agent.'
        ),
    )

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='muk_ai_skill_ir_attachment_rel',
        column1='skill_id',
        column2='attachment_id',
        string='Resources',
        help=(
            'Attachments listed in the skill manifest. The agent can '
            'fetch any of them via read_resource using the '
            'uri from the manifest.'
        ),
    )

    agent_count = fields.Integer(
        string='Agent Count',
        compute='_compute_agent_count',
    )

    attachment_count = fields.Integer(
        string='Attachment Count',
        compute='_compute_attachment_count',
    )

    user_count = fields.Integer(
        compute='_compute_user_count',
        string='User Count',
    )

    visibility = fields.Selection(
        compute='_compute_visibility',
        inverse='_inverse_visibility',
        selection=[
            ('owner', 'Only Me'),
            ('users', 'Selected Users'),
            ('everyone', 'Everyone'),
        ],
        string='Visibility',
        help=(
            'Who can pick the skill in chat. The share list stays empty '
            'when the skill is visible to everyone.'
        ),
    )

    is_editable = fields.Boolean(
        compute='_compute_is_editable',
        string='Editable',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _default_user_ids(self) -> models.BaseModel:
        """Seed the share list with the author, unless the author is archived.

        Shipped and demo records are authored by OdooBot, an archived
        account, and a share row on it makes the skill private to a login
        nobody uses.
        """
        return self.env.user if self.env.user.active else self.env['res.users']

    def _unfiltered(self) -> models.BaseModel:
        """Return the same records with archived share rows still readable.

        Reading a many2many drops archived ids while the row stays in the
        table, so the share list reads back empty while the visibility domain
        still searches -- and finds -- the surviving row. Kept as a recordset
        rather than a share list so a compute can walk it alongside ``self``
        and read ``user_ids`` for the whole batch in one query.
        """
        return self.sudo().with_context(active_test=False)

    def _shared_users(self) -> models.BaseModel:
        """Return the share list of a single record, archived users included."""
        self.ensure_one()
        return self._unfiltered().user_ids

    @api.model
    def _user_visibility_domain(self, user: models.BaseModel) -> list:
        """Return the domain of skills visible to the given user.

        A skill is visible when the user owns it, when it is shared
        with everyone (empty share list) or when the user is in the
        share list.
        """
        return [
            '|',
            '|',
            ('owner_id', '=', user.id),
            ('user_ids', '=', False),
            ('user_ids', 'in', user.ids),
        ]

    @api.model
    def _get_prompt_fields(self) -> list[str]:
        """Return the field names rendered as prompt templates."""
        return ['body']

    def _build_body(self, session: models.BaseModel | None = None) -> str:
        """Return the skill body verbatim without evaluating it as a template.

        Skill bodies are user-authored and can be shared across users, so
        rendering them through the inline template engine would let a
        ``{{ ... }}`` fragment run ORM writes under the invoking user's
        rights (``.sudo()`` inside the expression escalates even under a
        non-superuser environment). The body is returned as inert text,
        matching the MCP ``invoke_skill`` path, so it never executes.
        """
        return self.body or ''

    def _resource_manifest(self) -> list[dict]:
        """Return the manifest of attached resources with their uris."""
        return [
            {
                'name': attachment.name or '',
                'uri': 'odoo://attachment/%d' % attachment.id,
                'mimetype': attachment.mimetype or '',
            }
            for attachment in self.attachment_ids
        ]

    def _relink_attachments(self) -> None:
        """Bind resources uploaded before the skill was saved to the skill.

        The web ``FileInput`` creates ``ir.attachment`` rows with ``res_id=0``
        while the skill is still unsaved. Without relinking, shared users
        cannot read those resources through ``read_resource`` because
        attachment access resolves through the owning skill record. Mirrors
        ``muk_ai.session._resolve_attachments``.
        """
        for record in self:
            pending = record.attachment_ids.filtered(
                lambda attachment: (
                    attachment.res_model == 'muk_ai.skill' and not attachment.res_id
                )
            )
            if pending:
                pending.sudo().write({'res_id': record.id})

    def _skill_descriptor(self) -> dict:
        """Return what a surface needs to offer this skill.

        The seam a surface extends to carry what only it understands: the
        writing helper adds the group it arranges its offers by, and nothing
        here has to know that such a grouping exists.
        """
        return {
            'name': self.name,
            'label': self.label or self.display_name or self.name,
            'description': (self.description or '').strip(),
            'icon': self.icon or 'fa-bolt',
            'body': self.body or '',
        }

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_share_everyone(self) -> None:
        """Clear the share list so the skill is visible to all users.

        Unlinked row by row rather than with ``(5, 0, 0)``: the ORM diffs a
        many2many write against the value it can read, so clearing everything
        clears nothing when the only sharee is archived.
        """
        for record, unfiltered in zip(self, self._unfiltered()):
            shared = unfiltered.user_ids
            if shared:
                unfiltered.write({'user_ids': [(3, user.id) for user in shared]})

    def action_make_private(self) -> None:
        """Reset the share list so only the owner can see the skill."""
        for record, unfiltered in zip(self, self._unfiltered()):
            shared = unfiltered.user_ids
            commands = [(3, user.id) for user in shared - record.owner_id]
            if record.owner_id and record.owner_id not in shared:
                commands.append((4, record.owner_id.id))
            if commands:
                unfiltered.write({'user_ids': commands})

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def fetch_skills(self, skill_type: str) -> list[dict]:
        """Return the skills a surface offers, in the order they appear.

        Scoped to the user rather than to a session: a surface asks for its
        offers before it has one, and what it offers is picked by the user
        rather than discovered by an agent.

        :param skill_type: the surface asking, see the ``skill_type`` field
        :return: descriptors carrying what a surface needs to offer a skill
        """
        domain = [('active', '=', True), ('skill_type', '=', skill_type)]
        domain += self._user_visibility_domain(self.env.user)
        skills = self.env['muk_ai.session']._dedupe_visible_skills(
            self.sudo().search(domain), self.env.user
        )
        return [skill._skill_descriptor() for skill in skills]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('label', 'name')
    @api.depends_context('lang')
    def _compute_display_name(self) -> None:
        for record in self:
            record.display_name = record.label or (
                record.name.replace('_', ' ').title() if record.name else ''
            )

    @api.depends('attachment_ids')
    def _compute_attachment_count(self) -> None:
        for record in self:
            record.attachment_count = len(record.attachment_ids)

    @api.depends('agent_ids')
    def _compute_agent_count(self) -> None:
        for record in self:
            record.agent_count = len(record.agent_ids)

    @api.depends('user_ids', 'owner_id')
    def _compute_user_count(self) -> None:
        for record, unfiltered in zip(self, self._unfiltered()):
            record.user_count = len(unfiltered.user_ids - record.owner_id)

    @api.depends('user_ids', 'owner_id')
    def _compute_visibility(self) -> None:
        for record, unfiltered in zip(self, self._unfiltered()):
            shared = unfiltered.user_ids
            if not shared:
                record.visibility = 'everyone'
            elif shared <= record.owner_id:
                record.visibility = 'owner'
            else:
                record.visibility = 'users'

    def _inverse_visibility(self) -> None:
        """Rewrite the share list to match the picked visibility.

        Picking ``users`` keeps whoever is already listed and seeds the
        owner, so the skill never falls back to being visible to everyone
        while the list is still being filled in.
        """
        for record in self:
            if record.visibility == 'everyone':
                record.action_share_everyone()
            elif record.visibility == 'owner' or not record._shared_users():
                record.action_make_private()

    @api.depends('owner_id')
    @api.depends_context('uid')
    def _compute_is_editable(self) -> None:
        is_admin = self.env.user.has_group('base.group_system')
        for record in self:
            record.is_editable = is_admin or record.owner_id == self.env.user

    @api.onchange('owner_id')
    def _onchange_owner_id(self) -> None:
        """Move the stale creator default of the share list to the new owner."""
        for record in self:
            if (
                record.user_ids._origin == self.env.user
                and record.owner_id._origin != self.env.user
            ):
                record.user_ids = record.owner_id

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _unique_name_owner = models.Constraint(
        'unique(name, owner_id)',
        'You already own a skill with this technical name.',
    )

    @api.constrains('name')
    def _check_name_format(self) -> None:
        """Validate the technical name against the lowercase identifier rule.

        :raise ValidationError: when the name does not match [a-z][a-z0-9_]*
        """
        name_check = re.compile(r'^[a-z][a-z0-9_]*$')
        for record in self:
            if not record.name or not name_check.match(record.name):
                raise ValidationError(
                    _(
                        'Skill name %(name)r must match [a-z][a-z0-9_]*.',
                        name=record.name or '',
                    )
                )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> models.BaseModel:
        """Create skills, defaulting the share list to an active skill owner.

        An archived owner is left to the field default, which falls back to
        the creator: a share row on a login nobody uses would make the skill
        private to nobody, unreachable for every human.
        """
        for vals in vals_list:
            if 'user_ids' not in vals:
                owner_id = vals.get('owner_id') or self.env.uid
                owner = self.env['res.users'].sudo().browse(owner_id).exists()
                if owner and owner.active:
                    vals['user_ids'] = [(6, 0, [owner_id])]
        records = super().create(vals_list)
        records._relink_attachments()
        return records

    def write(self, vals: dict) -> bool:
        """Write skills and relink resources uploaded before the skill existed."""
        result = super().write(vals)
        if 'attachment_ids' in vals:
            self._relink_attachments()
        return result
