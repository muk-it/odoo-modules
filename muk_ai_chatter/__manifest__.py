{
    'name': 'MuK AI Chatter',
    'summary': 'Link AI sessions to records and mention agents in a thread',
    'description': """
        Ties AI sessions to the business record they run for, listing them
        in the chatter of any threaded model and collecting them in a
        Records space. Lets users mention an AI agent with the regular @
        syntax in a Discuss channel or in a direct chat, and receive its
        answer in that same conversation, without the agent ever joining
        it, being mailed or answering on its own again. A mentioned agent
        never stops to ask, so a conversation always ends up with an
        answer. On a record, the writing helper in the composer is the
        surface instead.
    """,
    'version': '19.0.1.0.3',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'html_editor',
        'mail',
        'muk_ai',
        'muk_ai_skills',
    ],
    'post_init_hook': '_post_init_hook',
    'data': [
        'data/space.xml',
        'data/skill.xml',
        'views/ai_agent.xml',
        'views/skill.xml',
        'views/mail_compose_message.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_chatter/static/src/**/*',
        ],
        'web.assets_tests': [
            'muk_ai_chatter/static/tests/tours/chatter_tour.js',
        ],
        'web.assets_unit_tests': [
            'muk_ai_chatter/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
