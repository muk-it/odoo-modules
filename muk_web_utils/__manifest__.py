{
    'name': 'MuK Web Utils', 
    'summary': 'Adds utility features for the web client',
    'description': '''
        Technical module to provide some utility features and libraries that 
        can be used in other applications.
    ''',
    'version': '18.0.1.0.0', 
    'category': 'Tools/Utils',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'web',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_web_utils/static/src/**/*.*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
