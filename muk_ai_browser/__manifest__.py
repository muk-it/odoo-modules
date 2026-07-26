{
    'name': 'MuK AI Browser',
    'summary': "Let a MuK AI agent act on the user's live web page via a browser extension",
    'description': """
        Bridges the MuK AI agent loop to a Chrome browser extension so an
        agent can read the DOM, click, fill, navigate and call Odoo MCP
        tools in a single plan. The server owns the agent loop and safety
        gates; the extension is a thin actuator. Perception and action run
        in the page, while reasoning, secrets, audit and approvals stay
        server-side.
    """,
    'version': '19.0.1.0.10',
    'category': 'Productivity',
    'license': 'Other proprietary',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
        'muk_mcp',
        'muk_web_utils',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'views/connect.xml',
        'views/device.xml',
        'views/permission.xml',
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
