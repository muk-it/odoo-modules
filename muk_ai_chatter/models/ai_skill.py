from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Skill(models.Model):
    """Offer skills as the writing helper of a composer."""

    _inherit = 'muk_ai.skill'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    skill_type = fields.Selection(
        selection_add=[('composer', 'Composer')],
        ondelete={'composer': 'cascade'},
    )

    category = fields.Selection(
        selection=[
            ('fix', 'Fix'),
            ('rewrite', 'Rewrite'),
            ('transform', 'Transform'),
            ('generate', 'Generate'),
        ],
        string='Category',
        help=(
            'How the writing helper groups the skill in a composer. Fix, '
            'rewrite and transform act on what is already written; generate '
            'writes something new. Left empty for every other kind of skill.'
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _skill_descriptor(self) -> dict:
        """Tell the composer which group this skill is offered under."""
        return {**super()._skill_descriptor(), 'category': self.category or ''}

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('skill_type', 'category')
    def _check_category(self) -> None:
        """Require a category on a skill the writing helper has to group.

        The helper offers what it has one group at a time, so a composer skill
        belonging to no group would be offered nowhere at all. Every other
        kind is found by its description and needs none.

        :raise ValidationError: when a composer skill carries no category
        """
        for record in self:
            if record.skill_type == 'composer' and not record.category:
                raise ValidationError(
                    _(
                        'Skill %(name)r needs a category to be offered in a composer.',
                        name=record.name or '',
                    )
                )
