{
    'name': 'MuK Backend Theme',
    'summary': 'Odoo Community Backend Theme',
    'description': """
        This module offers a mobile compatible design for Odoo Community. Furthermore it
        allows the user to define some design preferences. Each user can choose the size
        of the sidebar. In addition, the background image of the app menu can be set
        for each company.
    """,
    'version': '20.0.1.4.14',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/p7ueZ9xCxRs',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_web_group',
        'muk_web_chatter',
        'muk_web_dialog',
        'muk_web_appsbar',
        'muk_web_colors',
        'muk_web_refresh',
    ],
    'excludes': [
        'web_enterprise',
    ],
    'data': [
        'templates/web_layout.xml',
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'web/static/src/scss/primary_variables.scss',
                'muk_web_theme/static/src/colors/theme/theme.scss',
            ),
            (
                'after',
                'web/static/src/scss/primary_variables.scss',
                'muk_web_theme/static/src/webclient/navbar/variables.scss',
            ),
        ],
        'web.assets_backend': [
            'muk_web_theme/static/src/webclient/**/*.xml',
            'muk_web_theme/static/src/webclient/**/*.scss',
            'muk_web_theme/static/src/webclient/**/*.js',
            'muk_web_theme/static/src/views/**/*.scss',
        ],
        'web.assets_unit_tests': [
            'muk_web_theme/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
        'static/description/theme_screenshot.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': '_setup_module',
    'uninstall_hook': '_uninstall_cleanup',
}
