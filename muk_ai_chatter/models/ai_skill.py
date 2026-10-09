from __future__ import annotations

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Skill(models.Model):
    """Offer skills as the quick actions of a composer's writing helper."""

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
    # Functions
    # ----------------------------------------------------------

    @api.model
    def save_composer_prompt(self, label: str, body: str, category: str) -> dict:
        """Save an instruction as a private composer skill and return its descriptor.

        The name is derived from the label, unique per owner, archived included.

        :raise ValidationError: when the label, body or category is unusable
        """
        label = (label or '').strip()
        body = (body or '').strip()
        if not label or not body:
            raise ValidationError(
                self.env._('A label and a prompt are needed to save a button.')
            )
        if category not in dict(self._fields['category'].selection):
            raise ValidationError(
                self.env._(
                    '%(category)r is not a writing helper category.',
                    category=category,
                )
            )
        base = re.sub(r'[^a-z0-9_]+', '_', label.lower()).strip('_') or 'prompt'
        if not base[0].isalpha():
            base = 'prompt_%s' % base
        taken = set(
            self.with_context(active_test=False)
            .search([('name', '=like', f'{base}%'), ('owner_id', '=', self.env.uid)])
            .mapped('name')
        )
        name, counter = base, 2
        while name in taken:
            name = '%s_%d' % (base, counter)
            counter += 1
        skill = self.create(
            {
                'name': name,
                'label': label,
                'skill_type': 'composer',
                'category': category,
                'icon': 'fa-magic' if category == 'generate' else 'fa-pencil',
                'description': body if len(body) <= 200 else '%s...' % body[:197],
                'body': body,
            }
        )
        return skill._skill_descriptor()

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('skill_type', 'category')
    def _check_category(self) -> None:
        """Require a category on a composer skill, which is offered by group.

        :raise ValidationError: when a composer skill carries no category
        """
        for record in self:
            if record.skill_type == 'composer' and not record.category:
                raise ValidationError(
                    self.env._(
                        'Skill %(name)r needs a category to be offered in a composer.',
                        name=record.name or '',
                    )
                )
