{
    'name': 'MuK Preview',
    'summary': 'Extends the file viewer with additional preview types',
    'description': '''
        Extends the built-in file viewer with additional preview support
        for file types such as email messages and CSV files. The module
        also adds common text-based mimetypes to the viewer so they can
        be previewed directly without downloading.
    ''',
    'version': '19.0.1.0.0',
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
        'muk_web_utils',
    ],
    'data': [],
    'assets': {
        'web.assets_backend': [
            (
                'after',
                'web/static/src/core/file_viewer/file_model.js',
                'muk_web_preview/static/src/core/file_viewer/file_model.js',
            ),
            (
                'after',
                'web/static/src/core/file_viewer/file_viewer.scss',
                'muk_web_preview/static/src/core/file_viewer/file_viewer.scss',
            ),
            (
                'after',
                'web/static/src/core/file_viewer/file_viewer.xml',
                'muk_web_preview/static/src/core/file_viewer/file_viewer.xml',
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
