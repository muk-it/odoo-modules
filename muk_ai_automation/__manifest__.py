{
    'name': 'MuK AI Automation',
    'summary': 'Run AI agents as server actions and automation rule steps',
    'description': """
        Extends MuK AI with an ir.actions.server state ``ai_agent`` so admins
        can run an AI agent from any server action, automation rule or
        scheduled action. Starts one chat for all target records or one per
        record, selected by the trigger, a domain or Python code, and lets
        each chat recall the previous run for the same record.
    """,
    'version': '18.0.1.3.6',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/XULLGbxdwtQ',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_automation',
        'muk_ai_chatter',
    ],
    'data': [
        'data/space.xml',
        'views/ir_actions_server.xml',
        'views/ir_cron.xml',
        'views/base_automation.xml',
        'views/ai_session.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/ir_actions_server.xml',
        'demo/base_automation.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
