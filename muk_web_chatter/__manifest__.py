{
    'name': 'MuK Chatter',
    'summary': 'Adds options for the chatter',
    'description': """
        This module improves the design of the chatter and adds a user
        preference to set the position of the chatter in the form view.
    """,
    'version': '20.0.1.5.0',
    'category': 'Tools/UI',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/6oiPpkwfvdA',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'mail',
    ],
    'data': [
        'views/res_users.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'web/static/src/scss/primary_variables.scss',
                'muk_web_chatter/static/src/views/form/variables.scss',
            ),
        ],
        'web.assets_backend': [
            'muk_web_chatter/static/src/chatter/**/*',
            'muk_web_chatter/static/src/core/**/*',
            'muk_web_chatter/static/src/views/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_web_chatter/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
