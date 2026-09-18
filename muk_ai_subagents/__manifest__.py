{
    'name': 'MuK AI Subagents',
    'summary': 'Delegate work to focused child agents that run in parallel',
    'description': """
        Lets an agent hand a focused task to another agent and carry on.
        Children run as sessions of their own, in parallel, each with its
        own context and its own agent configuration — so the permission
        model is the one you already know. A child that needs an approval
        or an answer asks in the conversation you are actually looking at.
        One quiet line above the composer says what the subagents are
        doing, every child is openable and keeps a permanent link, and a
        child that starts repeating itself says so before it ends.
    """,
    'version': '19.0.1.0.6',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
    ],
    'data': [
        'security/security.xml',
        'data/space.xml',
        'data/ir_cron.xml',
        'views/agent.xml',
        'views/session.xml',
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_subagents/static/src/chat/**/*',
            ('remove', 'muk_ai_subagents/static/src/**/*.dark.scss'),
        ],
        'web.assets_web_dark': [
            'muk_ai_subagents/static/src/**/*.dark.scss',
        ],
        'web.assets_tests': [
            'muk_ai_subagents/static/tests/tours/subagents_tour.js',
        ],
        'web.assets_unit_tests': [
            'muk_ai_subagents/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
