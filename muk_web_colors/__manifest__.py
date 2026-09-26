{
    'name': 'MuK Colors',
    'summary': 'Customize your Odoo colors',
    'description': """
        This module gives you options to customize the theme colors.
    """,
    'version': '20.0.1.0.19',
    'category': 'Tools/UI',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/TmJeE5YjEs4',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'web',
        'base_setup',
    ],
    'data': [
        'templates/webclient.xml',
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'muk_web_colors/static/src/colors/theme/theme.scss'),
            (
                'before',
                'muk_web_colors/static/src/colors/theme/theme.scss',
                'muk_web_colors/static/src/colors/light/light.scss',
            ),
        ],
        'web.assets_web_dark': [
            (
                'before',
                'muk_web_colors/static/src/colors/theme/theme.scss',
                'muk_web_colors/static/src/colors/dark/dark.scss',
            ),
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'uninstall_hook': '_uninstall_cleanup',
}
