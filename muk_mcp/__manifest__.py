{
    'name': 'MuK MCP Server',
    'summary': 'Model Context Protocol server for AI agent integration',
    'description': '''
        Implements a native MCP (Model Context Protocol) server inside
        Odoo, exposing business data and operations to any MCP-compatible
        AI client such as Claude Desktop, Claude Code, Cursor, Windsurf,
        or Codex CLI. The server speaks MCP Streamable HTTP at a single
        endpoint using Odoo API keys for authentication.
    ''',
    'version': '19.0.1.0.0',
    'category': 'Tools/API',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mcp_tool.xml',
        'views/mcp_key.xml',
        'views/mcp_log.xml',
        'views/mcp_tool.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
