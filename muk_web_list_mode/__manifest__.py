{
    'name': 'MuK List Mode', 
    'summary': 'Switch the mode of your list views',
    'description': '''
        Enables you to switch between read and editable list views as
        long as the user has the needed access rights and the list view 
        does not  explicitly disable edit mode by being set to readonly.
    ''',
    'version': '19.0.1.0.1',
    'category': 'Tools/UI',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/efOsEbxZv9Q',
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
                '/web/static/src/search/control_panel/control_panel.xml',
                '/muk_web_list_mode/static/src/search/control_panel.xml',
            ),
            (
                'after',
                '/web/static/src/views/list/list_controller.js',
                '/muk_web_list_mode/static/src/views/list/list_controller.js',
            ),
        ],
        'web.assets_unit_tests': [
            'muk_web_list_mode/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
