{
    'name': 'MuK Refresh',
    'summary': 'Refresh views manually, automatically, or from the backend',
    'description': """
        Adds a refresh button next to the pager so the current view can be reloaded
        without leaving it. A double-click on the button turns on auto refresh, which
        reloads a list or kanban view at a fixed interval and pauses while the browser
        tab is in the background. A Reload Views server action lets an automation rule
        push a refresh to every open view of a model from the backend.
    """,
    'version': '20.0.1.1.15',
    'category': 'Tools/UI',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/dGeMQaWkBbs',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'web',
        'bus',
        'base_automation',
    ],
    'data': [
        'views/ir_actions_server_views.xml',
    ],
    'demo': [
        'demo/base_automation.xml',
        'demo/ir_actions_server.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_web_refresh/static/src/core/utils/refresh.js',
            'muk_web_refresh/static/src/search/control_panel/control_panel.scss',
            (
                'after',
                'web/static/src/search/control_panel/control_panel.js',
                'muk_web_refresh/static/src/search/control_panel/control_panel.js',
            ),
            (
                'after',
                'web/static/src/search/control_panel/control_panel.xml',
                'muk_web_refresh/static/src/search/control_panel/control_panel.xml',
            ),
            'muk_web_refresh/static/src/services/refresh/refresh_plugin.js',
        ],
        'web.assets_unit_tests': [
            'muk_web_refresh/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
