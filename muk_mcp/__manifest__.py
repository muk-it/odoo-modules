{
    'name': 'MuK MCP Server',
    'summary': 'Model Context Protocol server for AI agent integration',
    'description': """
        Implements an MCP (Model Context Protocol) server inside Odoo. AI
        clients such as Claude Code, Claude Desktop, Codex, Cursor and
        OpenCode connect to the /api/mcp endpoint with an MCP key and work
        with the database through tools, prompts and resources, with the
        access rights of the user the key belongs to. Every call is
        recorded in an audit log.
    """,
    'version': '20.0.4.1.0',
    'category': 'Tools/API',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/05wTnenU-LU',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'web',
        'mail',
        'base_setup',
        'attachment_indexation',
        'muk_web_utils',
    ],
    'data': [
        'security/ir.access.csv',
        'data/prompt.xml',
        'views/key.xml',
        'views/generate_key.xml',
        'views/show_key.xml',
        'views/log.xml',
        'views/transfer.xml',
        'views/tool.xml',
        'views/prompt.xml',
        'views/connect.xml',
        'views/res_config_settings.xml',
        'views/res_users.xml',
        'views/playground.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_mcp/static/src/core/message/message.xml',
            'muk_mcp/static/src/playground/**/*',
        ],
        'web.assets_tests': [
            'muk_mcp/static/tests/tours/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_mcp/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
