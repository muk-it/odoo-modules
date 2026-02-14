{
    'name': 'MuK Mail Utils', 
    'summary': 'Adds utility features for the web client',
    'description': '''
        Technical module to provide some utility features and libraries that 
        can be used in other applications.
    ''',
    'version': '19.0.1.1.0',
    'category': 'Tools/Utils',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'mail',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_mail_utils/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_mail_utils/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
