{
    'name': 'MuK AI',
    'summary': 'AI Base Module',
    'description': '''
        Base module for MuK AI features. Provides the shared foundation
        used by MuK AI addons on top of Odoo Community: pluggable
        provider layer (OpenAI Responses, Anthropic Messages, Google
        Gemini), per-provider configuration with connection test,
        prebuilt model catalog with pricing, agent session runtime with
        tool dispatch through muk_mcp, bus-based streaming, OWL chat
        client action, session-scoped approval gate for risky writes,
        and agents with per-user access rules.
    ''',
    'version': '19.0.1.3.4',
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
        'muk_mcp',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/provider.xml',
        'data/model.xml',
        'data/agent.xml',
        'data/ir_model.xml',
        'data/ir_cron.xml',
        'views/ir_model.xml',
        'views/provider.xml',
        'views/model.xml',
        'views/agent.xml',
        'views/agent_revision.xml',
        'views/approval.xml',
        'views/mcp_tool_log.xml',
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
            'muk_ai/static/lib/markdown-it/markdown-it.js',
            'muk_ai/static/src/chat/**/*',
            'muk_ai/static/src/components/**/*',
            'muk_ai/static/src/core/**/*',
            'muk_ai/static/src/views/context.js',
            'muk_ai/static/src/views/fields/**/*',
            'muk_ai/static/src/views/form/**/*',
            'muk_ai/static/src/views/kanban/**/*',
            'muk_ai/static/src/views/list/**/*',
            'muk_ai/static/src/webclient/**/*',
        ],
        'web.assets_backend_lazy': [
            'muk_ai/static/src/views/graph/**/*',
            'muk_ai/static/src/views/pivot/**/*',
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
