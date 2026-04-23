{
    'name': 'MuK AI',
    'summary': 'AI Base Module',
    'description': '''
        Base module for MuK AI features. Provides the shared foundation
        used by MuK AI addons on top of Odoo Community: configurable
        provider layer (OpenAI Responses API), settings page with
        connection test, agent session model with tool dispatch through
        muk_mcp, bus-based streaming, OWL chat client action, agents
        with per-user access rules and a daily usage cron.
    ''',
    'version': '19.0.1.0.0',
    'category': 'Extra Tools',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
        'Kerrim Abd E-Hamed <kerrim.adbelhamed@mukit.at>',
    ],
    'depends': [
        'bus',
        'mail',
        'base_setup',
        'html_editor',
        'muk_mcp',
    ],
    'data': [
        'data/provider.xml',
        'data/model.xml',
        'data/agent.xml',
        'data/ir_model.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/ir_model.xml',
        'views/provider.xml',
        'views/model.xml',
        'views/agent.xml',
        'views/agent_revision.xml',
        'views/approval.xml',
        'views/session.xml',
        'views/chat.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/agent.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai/static/src/**/*',
        ],
        'web.assets_tests': [
            'muk_ai/static/tests/tours/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_ai/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_hook',
}
