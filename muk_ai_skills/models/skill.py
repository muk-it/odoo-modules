from __future__ import annotations

import re

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError

NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


class Skill(models.Model):
    """Store a reusable AI skill with a body, description and resources."""

    _name = 'muk_ai.skill'
    _description = 'AI Skill'
    _explanation = (
        'A named procedure an AI agent can follow: a one-line description the '
        'agent reads to decide when it applies, a markdown body of instructions '
        'and attached resource files. A skill is private to its owner, shared '
        'with selected users or with everyone, can be limited to some agents, '
        'and can require a record, a list or a chatter to be open. Users run '
        'one with a /<name> command or from the skills menu of the chat.'
    )
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
        help='Material Symbol shown next to the skill in the chat skills menu.',
        default='flash_on',
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

    scope = fields.Selection(
        selection=[
            ('any', 'Anywhere'),
            ('context', 'On a Record or a List'),
            ('record', 'On a Single Record'),
            ('chatter', 'On a Record with a Chatter'),
        ],
        string='Available',
        help=(
            'What the user must have open for the skill to apply. A skill '
            'that acts on what is on screen is offered only there, and is '
            'refused when it is invoked against nothing.'
        ),
        required=True,
        default='any',
        index=True,
    )

    model_ids = fields.Many2many(
        comodel_name='ir.model',
        relation='muk_ai_skill_ir_model_rel',
        column1='skill_id',
        column2='model_id',
        string='Models',
        help=(
            'Models the skill applies to. Leave empty to offer it on every '
            'model the scope allows.'
        ),
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
        default=lambda self: self.env.user if self.env.user.active else None,
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

    user_count = fields.Integer(
        compute='_compute_visibility',
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

    def _unfiltered(self) -> models.BaseModel:
        """Return the same records with archived share rows still readable.

        Reading a many2many drops archived ids while the row stays in the
        table, so the share list would read back empty while the visibility
        domain still finds the surviving row.
        """
        return self.sudo().with_context(active_test=False)

    @api.model
    def _user_visibility_domain(self, user: models.BaseModel) -> list:
        """Return the domain of skills the user owns or that are shared with them."""
        return [
            '|',
            '|',
            ('owner_id', '=', user.id),
            ('user_ids', '=', False),
            ('user_ids', 'in', user.ids),
        ]

    @api.model
    def _search_visible(
        self, user: models.BaseModel, skill_type: str, domain: list | None = None
    ) -> models.BaseModel:
        """Return the active skills of a type visible to the user, one per name.

        Of several skills sharing a name the one the user owns wins, then the
        first in search order.
        """
        skills = self.sudo().search(
            [
                ('skill_type', '=', skill_type),
                *self._user_visibility_domain(user),
                *(domain or []),
            ]
        )
        chosen: dict[str, models.BaseModel] = {}
        for skill in skills:
            current = chosen.get(skill.name)
            if current is None or (skill.owner_id == user != current.owner_id):
                chosen[skill.name] = skill
        return skills.filtered(lambda skill: chosen[skill.name] == skill)

    @api.model
    def _get_prompt_fields(self) -> list[str]:
        """Return the field names rendered as prompt templates."""
        return ['body']

    def _scope_satisfied_by(self, view_context: dict | None) -> bool:
        """Tell whether what the user has open satisfies this skill's scope.

        A pinned list, pivot or graph names a model but no record, so only
        ``kind == 'record'`` counts as one. A model restriction needs a model
        on screen, whatever the scope.
        """
        context = view_context or {}
        model = context.get('model') or ''
        if self.scope != 'any':
            if not model:
                return False
            if self.scope in ('record', 'chatter') and context.get('kind') != 'record':
                return False
            if (
                self.scope == 'chatter'
                and not self.env['ir.model'].sudo()._get(model).is_mail_thread
            ):
                return False
        return not self.model_ids or model in self.model_ids.mapped('model')

    def _scope_requirement(self) -> str:
        """Return the one line stating what this skill needs to be open."""
        requirement = {
            'context': self.env._('needs a record or a list open'),
            'record': self.env._('needs a record open'),
            'chatter': self.env._('needs a record with a chatter open'),
        }.get(self.scope, '')
        if self.model_ids:
            names = ', '.join(sorted(self.model_ids.mapped('name')))
            restriction = self.env._('only on %(models)s', models=names)
            return f'{requirement}, {restriction}' if requirement else restriction
        return requirement

    def _skill_descriptor(self) -> dict:
        """Return what a surface needs to offer this skill.

        A surface extends it with what only it understands, such as the group
        it arranges its offers by.
        """
        return {
            'name': self.name,
            'label': self.display_name,
            'description': (self.description or '').strip(),
            'icon': self.icon or 'flash_on',
            'scope': self.scope,
            'models': sorted(self.model_ids.mapped('model')),
            'requirement': self._scope_requirement(),
            'body': self.body or '',
        }

    def _invocation_payload(self) -> dict:
        """Return the body and the resource manifest an invocation hands the agent.

        The body is returned as inert text, never rendered as a template: a
        shared skill must not run code under the invoking user's rights.
        """
        return {
            'name': self.name,
            'label': self.display_name,
            'body': self.body or '',
            'resources': [
                {
                    'name': attachment.name or '',
                    'uri': f'odoo://attachment/{attachment.id}',
                    'mimetype': attachment.mimetype or '',
                }
                for attachment in self.attachment_ids
            ],
        }

    def _relink_attachments(self) -> None:
        """Bind resources uploaded before the skill was saved to the skill.

        An upload on an unsaved form creates the attachment with ``res_id=0``,
        and shared users read a resource through the skill that owns it.
        """
        for record in self:
            pending = record.attachment_ids.filtered(
                lambda attachment: (
                    attachment.res_model == self._name and not attachment.res_id
                )
            )
            pending.sudo().write({'res_id': record.id})

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def fetch_skills(self, skill_type: str) -> list[dict]:
        """Return the descriptors of the skills a surface offers the user.

        :param skill_type: the surface asking, see the ``skill_type`` field
        """
        skills = self._search_visible(self.env.user, skill_type)
        return [skill._skill_descriptor() for skill in skills]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('label', 'name')
    @api.depends_context('lang')
    def _compute_display_name(self) -> None:
        """Show the label, or the technical name in title case."""
        for record in self:
            record.display_name = record.label or (
                record.name.replace('_', ' ').title() if record.name else ''
            )

    @api.depends('user_ids', 'owner_id')
    def _compute_visibility(self) -> None:
        """Derive who sees the skill and how many users it is shared with."""
        for record, unfiltered in zip(self, self._unfiltered()):
            shared = unfiltered.user_ids
            record.user_count = len(shared - record.owner_id)
            if not shared:
                record.visibility = 'everyone'
            elif shared <= record.owner_id:
                record.visibility = 'owner'
            else:
                record.visibility = 'users'

    def _inverse_visibility(self) -> None:
        """Rewrite the share list to match the picked visibility.

        ``users`` keeps the list and seeds the owner into an empty one. Rows are
        unlinked one by one, as the ORM cannot read archived sharees to diff.
        """
        for record, unfiltered in zip(self, self._unfiltered()):
            shared = unfiltered.user_ids
            if record.visibility == 'everyone':
                keep = shared.browse()
            elif record.visibility == 'owner' or not shared:
                keep = record.owner_id
            else:
                continue
            commands = [Command.unlink(user.id) for user in shared - keep]
            commands += [Command.link(user.id) for user in keep - shared]
            unfiltered.write({'user_ids': commands})

    @api.depends('owner_id')
    @api.depends_context('uid')
    def _compute_is_editable(self) -> None:
        """Let the owner and administrators edit the skill."""
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

    @api.constrains('scope', 'model_ids')
    def _check_scope_models(self) -> None:
        """Refuse a chatter scope on a model that has none.

        :raise ValidationError: when a selected model is not a thread
        """
        for record in self.filtered(lambda skill: skill.scope == 'chatter'):
            without = record.model_ids.filtered(lambda model: not model.is_mail_thread)
            if without:
                raise ValidationError(
                    self.env._(
                        'Skill %(name)s asks for a chatter, which %(models)s '
                        'does not have.',
                        name=record.name or '',
                        models=', '.join(sorted(without.mapped('model'))),
                    )
                )

    @api.constrains('name')
    def _check_name_format(self) -> None:
        """Validate the technical name against the lowercase identifier rule.

        :raise ValidationError: when the name does not match [a-z][a-z0-9_]*
        """
        for record in self:
            if not NAME_PATTERN.match(record.name or ''):
                raise ValidationError(
                    self.env._(
                        'Skill name %(name)r must match [a-z][a-z0-9_]*.',
                        name=record.name or '',
                    )
                )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict]) -> models.BaseModel:
        """Create skills shared with their owner, unless that owner is archived.

        Shipped and demo records are owned by OdooBot, an archived account: a
        share row on it would make the skill private to a login nobody uses,
        so such a skill keeps the default of the field.
        """
        for vals in vals_list:
            if 'user_ids' not in vals and (owner_id := vals.get('owner_id')):
                owner = self.env['res.users'].sudo().browse(owner_id)
                if owner.active:
                    vals['user_ids'] = [Command.set(owner.ids)]
        records = super().create(vals_list)
        records._relink_attachments()
        return records

    def write(self, vals: dict) -> bool:
        """Write skills and relink resources uploaded before the skill existed."""
        result = super().write(vals)
        if 'attachment_ids' in vals:
            self._relink_attachments()
        return result
