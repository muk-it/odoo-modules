{
    'name': 'MuK AI Schedule',
    'summary': 'Let agents wait for a time, a record change or a reply, then carry on',
    'description': """
        Gives every MuK AI chat a wait tool. An agent pauses itself until a
        time, until a record reaches a state or until a message is posted on
        a record, and carries on by itself when that happens, with the note
        it left for itself. Conditions are checked without calling the
        model, every wait has a timeout, and the chat shows what it waits
        for with a button to wake it at once.
    """,
    'version': '18.0.2.0.1',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/OhbTXayFli4',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
    ],
    'data': [
        'data/ir_cron.xml',
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_schedule/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_ai_schedule/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
