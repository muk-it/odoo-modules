{
    'name': 'MuK MCP Access',
    'summary': 'Model-level access control for the MCP server',
    'description': """
        Defence-in-depth add-on for MuK MCP Server. Controls which Odoo
        models are reachable through MCP, independent of the user's normal
        access rights. Administrators build a whitelist of models and choose
        read-only or full access per model. When the whitelist is empty
        every model is accessible (backwards-compatible). As soon as the
        first model is added only whitelisted models are exposed — the AI
        agent cannot discover or query anything else.
    """,
    'version': '19.0.1.1.9',
    'category': 'Tools/API',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_mcp',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/model_selection.xml',
        'views/mcp_access.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_mcp_access/static/src/views/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
