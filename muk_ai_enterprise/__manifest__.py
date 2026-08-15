{
    'name': 'MuK AI Enterprise',
    'summary': 'Use Enterprise AI tools, RAG sources and record context',
    'description': """
        One-way bridge: MuK AI sessions reach into the Odoo Enterprise
        AI primitives while the Enterprise data/model layer stays
        untouched. The Enterprise systray button is folded into the MuK
        AI dropdown as 'Open Odoo AI' — one icon, not two. Everything
        else keeps its existing behaviour.
    """,
    'version': '19.0.1.1.1',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'ai',
        'muk_ai',
        'muk_ai_chatter',
        'muk_ai_skills',
    ],
    'data': [
        'views/ai_agent.xml',
        'views/mail_compose_message.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_enterprise/static/src/webclient/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_ai_enterprise/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
