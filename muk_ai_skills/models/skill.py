import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Skill(models.Model):

    _name = 'muk_ai.skill'
    _description = "AI Skill"
    _inherit = ['muk_ai.revision.mixin', 'muk_ai.prompt.mixin']
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    display_name = fields.Char(
        compute='_compute_display_name',
        store=False,
    )

    name = fields.Char(
        string="Technical Name",
        help=(
            "Lowercase technical identifier used in the slash command "
            "and in the LLM-facing discovery list. Must match "
            "[a-z][a-z0-9_]*."
        ),
        required=True,
        index=True,
        copy=False,
    )

    label = fields.Char(
        string="Label",
        help="Human-readable label shown in lists and the chat menu.",
        translate=True,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        copy=False,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    description = fields.Text(
        string="Description",
        help=(
            "One-line description shown to the LLM in the system "
            "prompt addendum so it can decide when to invoke the skill."
        ),
        required=True,
        translate=True,
    )

    body = fields.Text(
        string="Body",
        help=(
            "Markdown body returned when the skill is invoked. "
            "Optional: a manifest-only skill may rely solely on its "
            "attached resources."
        ),
        translate=True,
    )

    agent_ids = fields.Many2many(
        comodel_name='muk_ai.agent',
        relation='muk_ai_skill_agent_rel',
        column1='skill_id',
        column2='agent_id',
        string="Agents",
        help=(
            "Agents that can see this skill. Leave empty to make the "
            "skill visible to every agent."
        ),
    )

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='muk_ai_skill_ir_attachment_rel',
        column1='skill_id',
        column2='attachment_id',
        string="Resources",
        help=(
            "Attachments listed in the skill manifest. The agent can "
            "fetch any of them via read_resource using the "
            "uri from the manifest."
        ),
    )

    agent_count = fields.Integer(
        string="Agent Count",
        compute='_compute_agent_count',
    )

    attachment_count = fields.Integer(
        string="Attachment Count",
        compute='_compute_attachment_count',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_prompt_fields(self):
        return ['body']

    def _build_body(self, session=None):
        extras = session._session_prompt_extras() if session else {}
        return self._render_prompt(self.body or '', **extras)

    def _resource_manifest(self):
        return [
            {
                'name': attachment.name or '',
                'uri': 'odoo://attachment/%d' % attachment.id,
                'mimetype': attachment.mimetype or '',
            }
            for attachment in self.attachment_ids
        ]

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('label', 'name')
    @api.depends_context('lang')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.label or (
                record.name.replace('_', ' ').title()
                if record.name else ''
            )

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for record in self:
            record.attachment_count = len(record.attachment_ids)

    @api.depends('agent_ids')
    def _compute_agent_count(self):
        for record in self:
            record.agent_count = len(record.agent_ids)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'unique_name',
            'unique(name)',
            "A skill with this technical name already exists.",
        ),
    ]

    @api.constrains('name')
    def _check_name_format(self):
        name_check = re.compile(r'^[a-z][a-z0-9_]*$')
        for record in self:
            if not record.name or not name_check.match(record.name):
                raise ValidationError(_(
                    "Skill name %(name)r must match [a-z][a-z0-9_]*.",
                    name=record.name or '',
                ))
