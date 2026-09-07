from __future__ import annotations

import re

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
    # Functions
    # ----------------------------------------------------------

    @api.model
    def save_composer_prompt(self, label: str, body: str, category: str) -> dict:
        """Keep a prompt typed into the writing helper as a button of its own.

        The helper's free-text field runs a one-off instruction; this saves
        that instruction as a private composer skill so the panel offers it as
        a chip from then on. The technical name is derived from the label here
        because the person saving a button never chose one, and it is unique
        per owner — an archived skill still holds its name, so those count too.

        :param label: wording shown on the chip
        :param body: the instruction the chip will carry
        :param category: where the panel offers it, see the ``category`` field
        :return: the descriptor the panel lists the new chip from
        :raise ValidationError: when the label, body or category is unusable
        """
        label = (label or '').strip()
        body = (body or '').strip()
        if not label or not body:
            raise ValidationError(
                _('A label and a prompt are needed to save a button.')
            )
        if category not in dict(self._fields['category'].selection):
            raise ValidationError(
                _('%(category)r is not a writing helper category.', category=category)
            )
        base = re.sub(r'[^a-z0-9_]+', '_', label.lower()).strip('_') or 'prompt'
        if not re.match(r'^[a-z]', base):
            base = 'prompt_%s' % base
        taken = self.with_context(active_test=False)
        name, counter = base, 2
        while taken.search_count(
            [('name', '=', name), ('owner_id', '=', self.env.uid)]
        ):
            name = '%s_%d' % (base, counter)
            counter += 1
        skill = self.create(
            {
                'name': name,
                'label': label,
                'skill_type': 'composer',
                'category': category,
                'icon': 'fa-magic' if category == 'generate' else 'fa-pencil',
                'description': body if len(body) <= 200 else '%s…' % body[:199],
                'body': body,
            }
        )
        return skill._skill_descriptor()

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
