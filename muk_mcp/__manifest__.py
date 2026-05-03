{
    'name': 'MuK MCP Server',
    'summary': 'Model Context Protocol server for AI agent integration',
    'description': '''
        Implements a native MCP (Model Context Protocol) server inside
        Odoo, exposing business data and operations to any MCP-compatible
        AI client such as Claude Desktop, Claude Code, Cursor, Windsurf,
        or Codex CLI. The server speaks MCP Streamable HTTP at a single
        endpoint using MCP API keys for authentication.
    ''',
    'version': '17.0.1.5.4',
    'category': 'Tools/API',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/zpBTT46tJZ0',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'web',
        'mail',
        'base_setup',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/tool.xml',
        'views/key.xml',
        'views/generate_key.xml',
        'views/show_key.xml',
        'views/log.xml',
        'views/notification.xml',
        'views/session.xml',
        'views/tool.xml',
        'views/connect.xml',
        'views/res_config_settings.xml',
        'views/res_users.xml',
        'views/playground.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_mcp/static/src/core/message.xml',
            'muk_mcp/static/src/playground/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
