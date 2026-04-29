import json

from odoo import _, api, fields, models


class Connect(models.TransientModel):

    _name = 'muk_mcp.connect'
    _description = "Connect AI Wizard"

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_url = fields.Char(
        compute='_compute_mcp_url',
        string="MCP URL",
    )

    claude_code_cmd = fields.Text(
        compute='_compute_snippets',
        string="Claude Code Command",
    )

    claude_desktop_json = fields.Text(
        compute='_compute_snippets',
        string="Claude Desktop JSON",
    )

    codex_toml = fields.Text(
        compute='_compute_snippets',
        string="Codex CLI TOML",
    )

    cursor_json = fields.Text(
        compute='_compute_snippets',
        string="Cursor JSON",
    )

    opencode_json = fields.Text(
        compute='_compute_snippets',
        string="OpenCode JSON",
    )

    bearer_key = fields.Char(
        string="Bearer Key",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_generate_key(self):
        self.ensure_one()
        result = self.env['muk_mcp.key'].generate_playground_key(
            name=_('Connect AI'), scope='write',
        )
        self.bearer_key = result['plaintext']
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends_context('uid')
    def _compute_mcp_url(self):
        for record in self:
            record.mcp_url = (record.get_base_url() or '').rstrip('/') + '/mcp'

    @api.depends('mcp_url', 'bearer_key')
    def _compute_snippets(self):
        for record in self:
            key = record.bearer_key or '<paste-bearer-key-here>'
            record.claude_code_cmd = (
                f'claude mcp add --transport http odoo { record.mcp_url} '
                f'--header "Authorization: Bearer {key}"'
            )
            record.claude_desktop_json = json.dumps(
                {
                    'mcpServers': {'odoo': {
                        'command': 'npx',
                        'args': [
                            '-y',
                            'mcp-remote',
                            record.mcp_url,
                            '--header',
                            f'Authorization: Bearer {key}'
                        ],
                    }},
                },
                indent=2
            )
            record.codex_toml = (
                "[mcp_servers.odoo]\n"
                f'url = "{ record.mcp_url}"\n'
                f'headers.Authorization = "Bearer {key}"\n'
            )
            record.cursor_json = json.dumps(
                {
                    'mcpServers': {'odoo': {
                        'url':  record.mcp_url,
                        'headers': {'Authorization': f'Bearer {key}'},
                    }},
                },
                indent=2
            )
            record.opencode_json = json.dumps(
                {
                    'mcp': {'odoo': {
                        'type': 'remote',
                        'url': record.mcp_url,
                        'enabled': True,
                        'headers': {'Authorization': f'Bearer {key}'},
                    }},
                },
                indent=2
            )
