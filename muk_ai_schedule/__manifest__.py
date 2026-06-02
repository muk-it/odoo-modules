{
    'name': 'MuK AI Schedule',
    'summary': 'Run AI agents on a schedule, let them pause and resume themselves',
    'description': '''
        Extends MuK AI with scheduled, autonomous agent sessions. Lets
        admins define muk_ai.schedule records that fire on a cron
        cadence, each one launching a fresh MuK AI session under a
        chosen agent and prompt with no user in the loop. Per-record
        dispatch fans a single schedule into one session per record
        matching a domain; chained sessions expose previous_session_id
        so an agent can recall last run's summary cheaply.
    ''',
    'version': '18.0.1.0.35',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
    ],
    'external_dependencies': {
        'python': ['croniter'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/schedule.xml',
        'views/session.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/schedule.xml',
        'demo/session.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_schedule/static/src/views/fields/**/*',
            'muk_ai_schedule/static/src/chat/**/*',
            'muk_ai_schedule/static/src/chatter/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
