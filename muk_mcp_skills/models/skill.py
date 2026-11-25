from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import quote

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_mcp_skills.tools.constants import SKILL_FILE, SKILL_SCHEME
from odoo.addons.muk_mcp_skills.tools.content import is_text


class Skill(models.Model):
    """A procedure served to MCP clients as an Agent Skill."""

    _name = 'muk_mcp_skills.skill'
    _description = 'MCP Skill'
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def MAX_SIZE(self) -> int:
        """Return the bytes of a skill every client has to accept."""
        return 16 * 1024 * 1024

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        help=(
            'Identifier clients list and call the skill by: lowercase letters, '
            'digits and single hyphens, 64 characters at most.'
        ),
        required=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    description = fields.Text(
        string='Description',
        help=(
            'What the skill does and when to use it. A client decides by this '
            'text alone whether a request needs the skill.'
        ),
        required=True,
    )

    body = fields.Text(
        string='Instructions',
        help='Markdown the client follows once it has loaded the skill.',
        required=True,
    )

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Files',
        help=(
            'Files next to the instructions. Mention one by its name and the '
            'client reads it when it needs it.'
        ),
    )

    group_ids = fields.Many2many(
        comodel_name='res.groups',
        string='Groups',
        help='Groups the skill is served to. Leave empty to serve it to everyone.',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _find(self, uri: str) -> Skill:
        """Return the skill a ``skill://`` URI lies in, if the user may read it."""
        name = uri.removeprefix(SKILL_SCHEME).partition('/')[0]
        return self.search([('name', '=', name)])

    def _uri(self, filename: str = SKILL_FILE) -> str:
        """Return the URI of a file of the skill."""
        return f'{SKILL_SCHEME}{self.name}/{quote(filename)}'

    def _frontmatter(self) -> dict[str, str]:
        """Return the fields a client lists the skill with."""
        return {'name': self.name, 'description': self.description}

    def _files(self) -> dict[str, tuple[str, bytes, str]]:
        """Return the MIME type, content and name of every file by its URI.

        The frontmatter values are JSON strings, which YAML reads unchanged.
        """
        files = {}
        for skill in self:
            frontmatter = ''.join(
                f'{key}: {json.dumps(value, ensure_ascii=False)}\n'
                for key, value in skill._frontmatter().items()
            )
            text = f'---\n{frontmatter}---\n\n{skill.body}\n'
            files[skill._uri()] = ('text/markdown', text.encode(), SKILL_FILE)
            for attachment in skill.sudo().attachment_ids:
                raw = attachment.raw or b''
                files[skill._uri(attachment.name)] = (
                    'text/plain' if is_text(raw) else attachment.mimetype,
                    raw,
                    attachment.name,
                )
        return files

    def _entry(self) -> dict[str, Any]:
        """Describe the skill and all of its files the way clients list it."""
        return {
            'uri': self._uri(),
            'frontmatter': self._frontmatter(),
            'resources': [
                {
                    'uri': uri,
                    'digest': f'sha256:{hashlib.sha256(raw).hexdigest()}',
                    'size': len(raw),
                }
                for uri, (_mimetype, raw, _name) in self._files().items()
            ],
        }

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'name_unique',
            'UNIQUE(name)',
            'A skill with this name already exists.',
        ),
    ]

    @api.constrains('name', 'description')
    def _check_frontmatter(self) -> None:
        """Require a name and a description the Agent Skills format allows.

        :raise ValidationError: when one is too long or the name malformed.
        """
        for record in self:
            if len(record.name) > 64 or not re.fullmatch(
                r'[a-z0-9]+(-[a-z0-9]+)*', record.name
            ):
                raise ValidationError(
                    self.env._(
                        'The name may hold lowercase letters, digits and single '
                        'hyphens between them, 64 characters at most.'
                    )
                )
            if len(record.description) > 1024:
                raise ValidationError(
                    self.env._('The description may hold 1024 characters at most.')
                )

    @api.constrains('body', 'attachment_ids')
    def _check_files(self) -> None:
        """Require distinct file names and a size every client accepts.

        :raise ValidationError: when two files share a name or all are too large.
        """
        for record in self:
            names = [SKILL_FILE, *record.attachment_ids.mapped('name')]
            if len(names) != len(set(names)):
                raise ValidationError(
                    self.env._(
                        'Every file needs a name of its own, other than %s.',
                        SKILL_FILE,
                    )
                )
            if sum(len(raw) for _, raw, _ in record._files().values()) > (
                record.MAX_SIZE
            ):
                raise ValidationError(
                    self.env._('The files of a skill may hold 16 MB at most.')
                )
