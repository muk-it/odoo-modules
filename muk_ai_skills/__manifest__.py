{
    'name': 'MuK AI Skills',
    'summary': 'Pre-built agent skills the user or LLM can switch into',
    'description': '''
        Adds DB-backed skill records that bundle a name, a one-line
        description for LLM discovery, a markdown body and supporting
        attachments. Visible skills are listed in a system-prompt
        addendum so the agent can pick one autonomously, and users
        can invoke them directly with a /<name> slash command in chat.
    ''',
    'version': '19.0.1.0.9',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
        'muk_mcp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/skill.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/skill.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_skills/static/src/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
