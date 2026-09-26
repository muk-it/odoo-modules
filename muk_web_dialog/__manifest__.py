{
    'name': 'MuK Dialog',
    'summary': 'Adds options for the dialogs',
    'description': """
        This module adds an option to dialogs to expand it to full screen mode.
        Each user can set the initial state of the dialogs in their preferences.
    """,
    'version': '20.0.1.0.16',
    'category': 'Tools/UI',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/ZGW6hBjcces',
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
                'muk_web_dialog/static/src/views/form/variables.scss',
            ),
        ],
        'web.assets_backend': [
            (
                'after',
                'web/static/src/core/dialog/dialog.js',
                'muk_web_dialog/static/src/core/dialog/dialog.js',
            ),
            (
                'after',
                'web/static/src/core/dialog/dialog.xml',
                'muk_web_dialog/static/src/core/dialog/dialog.xml',
            ),
            (
                'after',
                'mail/static/src/core/web/action_dialog_patch.js',
                'muk_web_dialog/static/src/webclient/actions/action_dialog.js',
            ),
        ],
        'web.assets_unit_tests': [
            'muk_web_dialog/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
