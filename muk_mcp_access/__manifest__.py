{
    'name': 'MuK MCP Access',
    'summary': 'Model-level access control for the MCP server',
    'description': """
        Controls which Odoo models AI agents can reach through the MuK MCP
        Server, independent of the user's normal access rights.
        Administrators build an allowlist of models and choose read-only or
        read and write access per model, optionally limited to the records
        matching a domain. While the list is empty every model stays
        reachable; once it holds an entry, only the listed models are
        exposed and the agent cannot discover or query anything else.
    """,
    'version': '20.0.1.1.14',
    'category': 'Tools/API',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/_0uXgZ270eA',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_mcp',
    ],
    'data': [
        'security/ir.access.csv',
        'views/model_selection.xml',
        'views/mcp_access.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_mcp_access/static/src/views/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_mcp_access/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
