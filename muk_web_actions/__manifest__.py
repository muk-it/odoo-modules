{
    'name': 'MuK Batch Actions',
    'summary': 'Run server actions and reports in batches with a progress bar',
    'description': """
        Runs server actions and reports from the Actions and Print menus in batches
        instead of in one request. A server action set to Execute in Batch processes the
        selected records in slices of a configurable size, and a report set to Execute in
        Batch downloads one file per record, both behind a progress bar. Each batch is its
        own transaction, so large selections stay below the server timeout and a failing
        batch keeps the batches before it saved.
    """,
    'version': '20.0.1.1.8',
    'category': 'Tools/Utils',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/zWmmPZskd5g',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_web_utils',
    ],
    'data': [
        'views/ir_actions_server_views.xml',
        'views/ir_actions_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_web_actions/static/src/**/*.*',
        ],
        'web.assets_unit_tests': [
            'muk_web_actions/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
