{
    'name': 'MuK AI Chatter',
    'summary': 'Mention AI agents in Discuss and write chatter messages with AI',
    'description': """
        Lets users mention an agent of MuK AI Assistant with the regular @
        syntax in a Discuss channel or a direct chat, and posts its answer in
        that conversation, without the agent ever joining it or being mailed.
        In the chatter of any record, a writing helper fixes, rewrites or
        drafts the message being written. Chats linked to a record are listed
        in its chatter and collected in a Records space.
    """,
    'version': '18.0.1.1.3',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/TYV-3Cmt2no',
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
