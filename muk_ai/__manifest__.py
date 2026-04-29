{
    'name': 'MuK AI Assistant',
    'summary': 'Native agentic AI chat and agent runtime for Odoo',
    'description': '''
        A complete agentic AI assistant inside Odoo. Ships a native OWL
        chat client (with floating window and systray), a session-based
        agent runtime, and three first-class LLM providers (OpenAI
        Responses, Anthropic Messages, Google Gemini) with live token
        and reasoning streaming. Talks to your data through the same
        muk_mcp tool registry your external AI clients use — one source
        of truth, one permission model, one audit trail.

        Includes human-in-the-loop ask_user, a session-scoped approval
        gate for risky writes, per-agent tool filters and read-only
        scopes, multimodal attachments (images, PDFs, text files),
        agent suggestion prompts, prompt revision history, and a
        prebuilt catalog of current GPT-5.x / Claude 4.x / Gemini 3.x 
        models with input, output and cache pricing.

        Also acts as the foundation for the rest of the MuK AI suite —
        adding a new provider is a single-file drop-in via the
        providers REGISTRY, and downstream add-ons plug in extra tools,
        agents and UI extensions on top of the same runtime.
    ''',
    'version': '19.0.1.3.27',
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
