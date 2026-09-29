{
    'name': 'MuK List Columns',
    'summary': 'Save the list column width',
    'description': """
        When a list column is resized by hand, its new width is saved in the browser
        for the current user. The next time any list of that model is opened, the
        column keeps the saved width. Double-clicking a column's resize handle restores
        the automatic widths and forgets the saved ones.
    """,
    'version': '20.0.1.0.9',
    'category': 'Tools/UI',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/XUk9MhHPZ4I',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'web',
    ],
    'assets': {
        'web.assets_backend': [
            (
                'after',
                'web/static/src/views/list/list_renderer.xml',
                'muk_web_list_column/static/src/views/list/list_renderer.xml',
            ),
            'muk_web_list_column/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_web_list_column/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
