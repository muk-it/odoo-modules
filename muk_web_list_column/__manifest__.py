{
    'name': 'MuK List Columns', 
    'summary': 'Save the list column width',
    'description': '''
        When manually changing the column width, the changed width is saved in 
        local storage. When loading the view, the saved values are used to define
        the column width.
    ''',
    'version': '19.0.1.0.1',
    'category': 'Tools/UI',
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
            '/muk_web_list_column/static/src/views/list/list_view_storage.js',
            (
                'after',
                '/web/static/src/views/list/list_arch_parser.js',
                '/muk_web_list_column/static/src/views/list/list_arch_parser.js',
            ),
            (
                'after',
                '/web/static/src/views/list/list_renderer.js',
                '/muk_web_list_column/static/src/views/list/list_renderer.js',
            ),
            (
                'after',
                '/web/static/src/views/list/list_renderer.xml',
                '/muk_web_list_column/static/src/views/list/list_renderer.xml',
            ),
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
