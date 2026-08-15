{
    'name': 'MuK AI Automation',
    'summary': 'Run AI agents as server actions and automation rule steps',
    'description': """
        Extends MuK AI with an ir.actions.server state ``ai_agent`` so admins
        can fire an AI agent from any server action or base.automation
        rule. Supports single dispatch as well as per-record dispatch
        across a domain or a Python-evaluated recordset, chains sessions
        per record so the agent can recall the previous run, and exposes
        per-action caps for resumes, lifetime, tokens, and cost.
    """,
    'version': '19.0.1.1.1',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_automation',
        'muk_ai_chatter',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_actions.xml',
        'views/ir_actions_server.xml',
        'views/base_automation.xml',
        'views/res_config_settings.xml',
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
