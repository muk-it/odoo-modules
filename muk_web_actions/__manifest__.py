{
    'name': 'MuK Web Actions', 
    'summary': 'Allows to execute actions in batch',
    'description': '''
        Technical module to provide the possibility to execute 
        server actions and reports in batches on a client side.
    ''',
    'version': '19.0.1.0.1',
    'category': 'Tools/Utils',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_web_utils',
    ],
    'data': [
        'views/ir_actions_server.xml',
        'views/ir_actions_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_web_actions/static/src/**/*.*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
