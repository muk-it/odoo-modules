{
    'name': 'MuK AI Assistant',
    'summary': 'Native agentic AI agent and chat runtime for Odoo',
    'description': '''
        A complete agentic AI assistant inside Odoo. Ships a native OWL
        chat client (with floating window and systray), a session-based
        agent runtime, and three first-class LLM providers (OpenAI
        Responses, Anthropic Messages, Google Gemini) with live token
        and reasoning streaming. Talks to your data through the same
        muk_mcp tool registry your external AI clients use — one source
        of truth, one permission model, one audit trail.
    ''',
    'version': '18.0.1.6.11',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
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
        'views/approval.xml',
        'views/mcp_tool_log.xml',
        'views/session.xml',
        'views/chat.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/agent.xml',
        'demo/session.xml',
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
