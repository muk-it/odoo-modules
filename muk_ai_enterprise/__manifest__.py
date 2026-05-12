{
    'name': 'MuK AI Enterprise Bridge',
    'summary': 'Borrow Enterprise AI tools, RAG sources and record context in MuK AI sessions',
    'description': '''
        One-way bridge: MuK AI sessions consume Odoo Enterprise AI
        building blocks while the Enterprise side stays untouched.
        Discuss ai_chat channels, systray and chatter buttons, ai.agent
        replies, LLMApiService and the ai_fields cron all keep their
        existing behaviour — both chats coexist side by side.

        Per muk_ai.agent, admins pick ee_topic_ids (M2M to ai.topic) to
        borrow server-action tools as ee_action_* in MuK AI sessions,
        and ee_source_ids (M2M to ai.agent.source) to inject the top-N
        similar ai.embedding chunks into the system prompt. Per-record
        context from Model._ai_initialise_context is wired automatically
        whenever a MuK AI chat opens with a record in view context.

        Coexists with every optional ai_* satellite (ai_documents,
        ai_livechat, ai_fields, ai_server_actions, ai_knowledge,
        ai_website, ai_crm, ...) — no hard dependency, no breakage.
    ''',
    'version': '19.0.1.0.2',
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
        'security/ir.model.access.csv',
        'views/muk_ai_agent.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
