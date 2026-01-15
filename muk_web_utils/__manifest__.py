{
    'name': 'MuK Web Utils', 
    'summary': 'Adds utility features for the web client',
    'description': '''
        Technical module to provide some utility features and libraries that 
        can be used in other applications.
    ''',
    'version': '19.0.1.1.2',
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
        'base_setup',
    ],
    'data': [
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_web_utils/static/src/core/block_progress/*',
            (
                'after',
                'web/static/src/views/list/list_arch_parser.js',
                'muk_web_utils/static/src/views/list/list_arch_parser.js',
            ),
            (
                'after',
                'web/static/src/views/list/list_renderer.xml',
                'muk_web_utils/static/src/views/list/list_renderer.xml',
            ),
            (
                'after', 
                'web/static/src/views/fields/many2one/many2one_field.js',
                'muk_web_utils/static/src/views/fields/many2one/many2one.js',
            ),
            (
                'after', 
                'web/static/src/views/fields/x2many/x2many_field.js',
                'muk_web_utils/static/src/views/fields/x2many/x2many.js',
            ),
            'muk_web_utils/static/src/webclient/**/*',
            'muk_web_utils/static/src/views/fields/json/*',
            'muk_web_utils/static/src/views/fields/text_icons/*',
            'muk_web_utils/static/src/views/fields/selection_icons/*',
        ],
        'web.assets_unit_tests': [
            'muk_web_utils/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
