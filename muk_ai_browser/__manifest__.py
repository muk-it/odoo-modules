{
    'name': 'MuK AI Browser',
    'summary': 'Let the MuK AI assistant read and act on web pages in your browser',
    'description': """
        Pairs the MuK AI browser extension with Odoo so the assistant reads
        the page open in the user's browser, clicks, types, fills forms and
        navigates, and combines that with its Odoo tools in one chat. The
        agent loop, approvals and audit stay in Odoo: every site is allowed,
        asked about or blocked per user, sensitive actions always ask, and a
        plan the user approved limits the sites the assistant acts on.
    """,
    'version': '20.0.1.1.1',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/ZcIvjovoFtg',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
        'muk_mcp',
    ],
    'data': [
        'security/ir.access.csv',
        'views/permission.xml',
        'views/mcp_key.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
        'templates/connect.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_browser/static/src/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
