{
    'name': 'MuK Mail Routing',
    'summary': 'Collects lost, unrouted and failed emails',
    'description': """
        This module collects mails that could not be routed
        and allows them to be assigned subsequently.
    """,
    'version': '20.0.1.1.14',
    'category': 'Productivity/Mail',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/dqVdA5xrNFE',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'mail',
        'muk_mail_utils',
    ],
    'data': [
        'security/ir.access.csv',
        'views/mail_mail.xml',
        'views/mail_message.xml',
        'views/configuration.xml',
        'views/container.xml',
        'views/router.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_mail_route/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_mail_route/static/tests/**/*.test.js',
        ],
    },
    'demo': [
        'demo/configuration.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
