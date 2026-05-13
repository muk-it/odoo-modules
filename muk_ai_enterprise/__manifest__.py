{
    'name': 'MuK AI Enterprise Bridge',
    'summary': 'Borrow Enterprise AI tools, RAG sources and record context in MuK AI sessions',
    'description': '''
        One-way bridge: MuK AI sessions consume Odoo Enterprise AI
        building blocks while the Enterprise side stays untouched.
        Discuss ai_chat channels, systray and chatter buttons, ai.agent
        replies, LLMApiService and the ai_fields cron all keep their
        existing behaviour — both chats coexist side by side.
    ''',
    'version': '19.0.1.0.3',
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
    ],
    'data': [
        'views/ai_agent.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
