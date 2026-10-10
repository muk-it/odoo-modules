{
    'name': 'MuK AI Subagents',
    'summary': 'Delegate work to focused agents that run in parallel',
    'description': """
        Lets an agent hand focused tasks to other agents and wait for their
        reports. Each subagent runs as a chat of its own, in parallel, with
        its own agent configuration and never with more rights than the
        chat that started it. One live card in the conversation shows what
        every subagent is doing, takes an approval or an answer in place,
        and folds into the reports once the run ends.
    """,
    'version': '16.0.1.1.0',
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
        'views/agent.xml',
        'views/session.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_subagents/static/src/**/*',
        ],
        'web.qunit_suite_tests': [
            'muk_ai_subagents/static/tests/*_tests.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
